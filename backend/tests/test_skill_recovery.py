"""技能任务回收测试：覆盖 worker 重启后孤儿任务的识别、跳过与信号注册。"""
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
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


class SkillRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """创建类级应用与内存表，供各用例复用。"""
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
        """清空任务表并建立一条执行中的记录。"""
        from app.skillrun import store
        from app.skillrun.models.model import SkillRunRecord
        from extensions import db

        db.session.query(SkillRunRecord).delete()
        db.session.commit()
        self.record = store.create_record(
            skill_id="jira-gate-1",
            jira_url="https://jira.in.wezhuiyi.com/browse/CALL-1446",
        )
        store.mark_running(self.record, workspace_dir=tempfile.gettempdir())

    def test_running_record_without_active_task_is_recovered(self):
        """没有对应活跃任务的执行中记录被标记为失败，不再停留在 running。"""
        from app.skillrun import store
        from app.skillrun.recovery import ORPHAN_STAGE, recover_orphan_tasks

        recovered = recover_orphan_tasks(active_record_ids=set())

        record = store.find_record(self.record.task_id)
        self.assertEqual(recovered, [self.record.task_id])
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.stage, ORPHAN_STAGE)
        self.assertIsNotNone(record.finished_at)
        self.assertIn("worker 重启", record.error_message)

    def test_record_with_active_task_is_kept_running(self):
        """仍有活跃 Celery 任务时保持原状，避免误杀其它 worker 正在执行的任务。"""
        from app.skillrun import store
        from app.skillrun.recovery import recover_orphan_tasks

        recovered = recover_orphan_tasks(active_record_ids={self.record.id})

        record = store.find_record(self.record.task_id)
        self.assertEqual(recovered, [])
        self.assertEqual(record.status, "running")
        self.assertIsNone(record.finished_at)

    def test_recovery_is_skipped_when_active_state_unknown(self):
        """无法确认活跃任务时保持原状，避免误判。"""
        from app.skillrun import store
        from app.skillrun.recovery import recover_orphan_tasks

        recovered = recover_orphan_tasks(active_record_ids=None, celery_app=None)

        record = store.find_record(self.record.task_id)
        self.assertEqual(recovered, [])
        self.assertEqual(record.status, "running")

    def test_recovery_returns_empty_without_running_records(self):
        """没有执行中的记录时不产生任何改动。"""
        from app.skillrun import store
        from app.skillrun.recovery import recover_orphan_tasks

        store.mark_finished(self.record, "succeeded", stage="finished")

        self.assertEqual(recover_orphan_tasks(active_record_ids=set()), [])

    def test_collect_active_record_ids_reads_task_args(self):
        """从 Celery 活跃任务里按任务名与参数解析出记录标识。"""
        from app.skillrun.recovery import collect_active_record_ids

        inspector = SimpleNamespace(
            active=lambda: {
                "celery@host": [
                    {"name": "skillrun.run_skill", "args": [self.record.id]},
                    {"name": "analysis.analyze_log_task", "args": [99]},
                    {"name": "skillrun.run_skill", "args": ["bad"]},
                ]
            }
        )
        celery_app = SimpleNamespace(control=SimpleNamespace(inspect=lambda timeout: inspector))

        self.assertEqual(collect_active_record_ids(celery_app), {self.record.id})

    def test_collect_active_record_ids_returns_none_without_workers(self):
        """没有任何 worker 应答时返回 None，表示结果不可信。"""
        from app.skillrun.recovery import collect_active_record_ids

        celery_app = SimpleNamespace(control=SimpleNamespace(inspect=lambda timeout: SimpleNamespace(active=lambda: None)))

        self.assertIsNone(collect_active_record_ids(celery_app))

    def test_collect_active_record_ids_survives_broker_error(self):
        """查询 Celery 失败时返回 None 而不是抛异常，保证 worker 能正常启动。"""
        from app.skillrun.recovery import collect_active_record_ids

        def boom(timeout):
            """模拟 broker 不可用。"""
            raise OSError("broker down")

        celery_app = SimpleNamespace(control=SimpleNamespace(inspect=boom))

        self.assertIsNone(collect_active_record_ids(celery_app))

    def test_install_worker_recovery_registers_signal_once(self):
        """重复安装只注册一次 worker_ready 回调。"""
        from celery.signals import worker_ready

        from app.skillrun.recovery import install_worker_recovery

        celery_app = SimpleNamespace()
        before = len(worker_ready.receivers)

        self.assertTrue(install_worker_recovery(self.app, celery_app))
        self.assertFalse(install_worker_recovery(self.app, celery_app))
        self.assertEqual(len(worker_ready.receivers), before + 1)

    def test_record_started_after_query_is_kept_running(self):
        """查询开始之后才启动的任务视为正在执行，不参与回收。"""
        from app.skillrun.recovery import recover_orphan_tasks

        started_before = self.record.started_at - timedelta(seconds=1)

        self.assertEqual(recover_orphan_tasks(active_record_ids=set(), started_before=started_before), [])

    def test_retry_recovery_recovers_after_active_state_becomes_known(self):
        """首次查询不到活跃任务时按间隔重试，后续能确认则完成回收。"""
        from app.skillrun import store
        from app.skillrun.recovery import recover_orphan_tasks_with_retry

        states = [None, set()]
        sleeps = []

        def fake_collect(celery_app, timeout=None):
            """依次返回“不可确认”与“确认为空”，模拟 worker 逐步就绪。"""
            return states.pop(0)

        with patch("app.skillrun.recovery.collect_active_record_ids", side_effect=fake_collect):
            recovered = recover_orphan_tasks_with_retry(
                self.app,
                SimpleNamespace(),
                delay_seconds=0,
                attempts=2,
                interval_seconds=0,
                sleep=sleeps.append,
            )

        self.assertEqual(recovered, [self.record.task_id])
        self.assertEqual(store.find_record(self.record.task_id).status, "failed")

    def test_retry_recovery_keeps_records_when_state_stays_unknown(self):
        """始终无法确认活跃任务时保持执行中状态，并提示人工确认。"""
        from app.skillrun import store
        from app.skillrun.recovery import recover_orphan_tasks_with_retry

        with patch("app.skillrun.recovery.collect_active_record_ids", return_value=None):
            recovered = recover_orphan_tasks_with_retry(
                self.app,
                SimpleNamespace(),
                delay_seconds=0,
                attempts=2,
                interval_seconds=0,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(recovered, [])
        self.assertEqual(store.find_record(self.record.task_id).status, "running")

    def test_worker_ready_handler_starts_recovery_thread(self):
        """worker_ready 回调在后台线程里触发回收，不阻塞 worker 启动。"""
        from app.skillrun import recovery

        installed = {}
        started = []

        class FakeThread:
            """记录线程目标，便于断言回调行为而不真正起线程。"""

            def __init__(self, target=None, name=None, daemon=None):
                """保存线程目标供测试触发。"""
                self.target = target
                self.name = name
                self.daemon = daemon

            def start(self):
                """记录已启动并立即执行目标。"""
                started.append(self.name)
                self.target()

        def fake_connect(receiver, weak=True):
            """捕获信号回调，便于在测试中直接触发。"""
            installed["receiver"] = receiver

        celery_app = SimpleNamespace()
        calls = []
        with patch("celery.signals.worker_ready.connect", side_effect=fake_connect), patch.object(
            recovery, "recover_orphan_tasks_with_retry", side_effect=lambda app, celery: calls.append(app)
        ), patch.object(recovery, "threading", SimpleNamespace(Thread=FakeThread)):
            self.assertTrue(recovery.install_worker_recovery(self.app, celery_app))
            installed["receiver"]()

        self.assertEqual(started, ["skill-orphan-recovery"])
        self.assertEqual(calls, [self.app])
