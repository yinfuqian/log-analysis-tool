"""技能任务测试：覆盖 Codex 成功、超时、失败、技能缺失与提示词内容。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = BACKEND_DIR.parent
SKILLS_DIR = PROJECT_ROOT / "skills"


def create_test_app(**overrides):
    """构造使用内存数据库的测试应用。"""
    from app import create_app

    config = {
        "TESTING": True,
        "AUTH_TEST_BYPASS": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SKILLS_DIR": str(SKILLS_DIR),
        "SKILL_WORKSPACE_DIR": tempfile.gettempdir(),
    }
    config.update(overrides)
    return create_app(config_overrides=config)


class SkillTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """创建类级应用与内存表，保证 Celery 任务与测试共用同一应用上下文。"""
        from extensions import db

        cls.app = create_test_app()
        cls.context = cls.app.app_context()
        cls.context.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        """清理会话与内存数据库连接。"""
        from extensions import db

        db.session.remove()
        db.engine.dispose()
        cls.context.pop()

    def setUp(self):
        """清空任务表并准备一条排队记录。"""
        from app.skillrun import store
        from app.skillrun.models.model import SkillRunRecord
        from extensions import db

        db.session.query(SkillRunRecord).delete()
        db.session.commit()
        self.record = store.create_record(
            skill_id="jira-gate-1",
            jira_url="https://jira.in.wezhuiyi.com/browse/CALL-1446",
            inputs={"review_round": 2},
            requested_by="tester",
        )
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.app.config["SKILL_WORKSPACE_DIR"] = self.workspace.name

    def run_task(self, run_result=None, side_effect=None):
        """在 mock 掉 Codex 子进程的前提下同步执行技能任务。"""
        from app.skillrun.tasks import run_skill_task

        with patch("app.skillrun.tasks.codex_runner.run_codex_skill") as runner:
            if side_effect is not None:
                runner.side_effect = side_effect
            else:
                runner.return_value = run_result
            result = run_skill_task.apply(args=[self.record.id])
            payload = result.get()
            # 任务在独立的应用上下文中写库，这里刷新本地会话以读取最新状态。
            from extensions import db

            db.session.expire_all()
            return payload, runner

    def test_successful_run_persists_result_and_session(self):
        """Codex 正常结束时记录状态为成功并保存结论与统计信息。"""
        from app.skillrun import store
        from app.skillrun.codex_runner import CodexRunResult

        payload, _ = self.run_task(
            CodexRunResult(
                exit_code=0,
                last_message="结论：达标，难度中",
                session_id="session-1",
                duration_ms=1500,
                events=[{"kind": "message", "text": "结论", "at": 1.0}],
                usage={"input_tokens": 100},
            )
        )

        record = store.find_record(self.record.task_id)
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(record.status, "succeeded")
        self.assertEqual(record.result_text, "结论：达标，难度中")
        self.assertEqual(record.codex_session_id, "session-1")
        self.assertEqual(record.duration_ms, 1500)
        self.assertIsNone(record.error_message)
        self.assertIsNotNone(record.finished_at)

    def test_timeout_marks_record_as_timeout(self):
        """Codex 执行超时时记录状态为超时并保留错误说明。"""
        from app.skillrun import store
        from app.skillrun.codex_runner import CodexRunResult

        payload, _ = self.run_task(
            CodexRunResult(exit_code=None, timed_out=True, error="技能执行超过 1800 秒，已强制终止", duration_ms=1800000)
        )

        record = store.find_record(self.record.task_id)
        self.assertEqual(payload["status"], "timeout")
        self.assertEqual(record.status, "timeout")
        self.assertIn("已强制终止", record.error_message)

    def test_non_zero_exit_marks_record_as_failed(self):
        """Codex 非零退出时记录状态为失败。"""
        from app.skillrun import store
        from app.skillrun.codex_runner import CodexRunResult

        payload, _ = self.run_task(CodexRunResult(exit_code=2, error="Codex 退出码为 2", duration_ms=800))

        record = store.find_record(self.record.task_id)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.exit_code, 2)

    def test_success_without_final_message_is_failed(self):
        """流程成功但没有最终结论时视为失败，避免误报达标。"""
        from app.skillrun import store
        from app.skillrun.codex_runner import CodexRunResult

        payload, _ = self.run_task(CodexRunResult(exit_code=0, last_message="", duration_ms=100))

        record = store.find_record(self.record.task_id)
        self.assertEqual(payload["status"], "failed")
        self.assertIn("未返回最终结论", record.error_message)

    def test_missing_skill_marks_record_failed_without_calling_codex(self):
        """技能不存在时不调用 Codex，直接记录失败原因。"""
        from app.skillrun import store

        self.record.skill_id = "not-installed"
        from extensions import db

        db.session.add(self.record)
        db.session.commit()

        payload, runner = self.run_task()

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(store.find_record(self.record.task_id).status, "failed")
        runner.assert_not_called()

    def test_prompt_and_command_include_skill_jira_url_and_workspace(self):
        """任务把技能目录、Jira 链接与独立工作目录传给 Codex。"""
        from app.skillrun.codex_runner import CodexRunResult

        _, runner = self.run_task(CodexRunResult(exit_code=0, last_message="结论", duration_ms=10))

        call_kwargs = runner.call_args.kwargs
        command = runner.call_args.args[0]
        self.assertIn("jira.in.wezhuiyi.com/browse/CALL-1446", command[-1])
        self.assertIn("jira-gate-1", command[-1])
        self.assertIn(self.record.task_id, call_kwargs["cwd"])
        self.assertIn("--add-dir", command)
        self.assertIn(str(SKILLS_DIR / "jira-gate-1"), command)

    def test_unexpected_exception_is_recorded_as_failure(self):
        """Codex 调用抛出异常时记录失败，不让任务静默丢失。"""
        from app.skillrun import store

        payload, _ = self.run_task(side_effect=RuntimeError("codex 未安装"))

        record = store.find_record(self.record.task_id)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(record.status, "failed")
        self.assertIn("codex 未安装", record.error_message)

    def test_network_failure_uses_dedicated_stage(self):
        """网络不可达时单独标记阶段，便于与业务失败区分并快速定位。"""
        from app.skillrun import store
        from app.skillrun.codex_runner import CodexRunResult

        payload, _ = self.run_task(
            CodexRunResult(
                exit_code=1,
                network_failed=True,
                error="Codex 连续 3 次网络错误，无法访问模型中转或 Jira，已提前终止本次任务",
                duration_ms=25000,
            )
        )

        record = store.find_record(self.record.task_id)
        self.assertEqual(payload["status"], "failed")
        self.assertTrue(payload["network_failed"])
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.stage, "network_unreachable")
        self.assertIn("网络错误", record.error_message)

    def test_network_retry_limit_is_passed_from_config(self):
        """网络错误阈值从配置传入 Codex 执行器，便于按环境调整。"""
        from app.skillrun.codex_runner import CodexRunResult

        self.app.config["CODEX_NETWORK_RETRY_LIMIT"] = 5
        _, runner = self.run_task(CodexRunResult(exit_code=0, last_message="结论", duration_ms=10))

        self.assertEqual(runner.call_args.kwargs["network_retry_limit"], 5)
