"""缺陷单门禁技能（jira-gate-bug）测试：覆盖技能发现、交付物契约与脚本行为（HTML 报告、自查结果判定）。"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SKILLS_DIR = BACKEND_DIR.parent / "skills"
SKILL_DIR = SKILLS_DIR / "jira-gate-bug"
NODE_BIN = shutil.which("node")


STUBBED_TOP_LEVEL_MODULES = ("app", "flask", "openai", "celery", "extensions")


def purge_stubbed_modules():
    """剔除其他测试模块遗留在 sys.modules 中的桩模块，保证导入真实实现。

    仓库里部分用例用 types.ModuleType 顶替 app/flask 等模块且不做还原，
    unittest discover 到本模块时 sys.modules 已被污染，因此导入前先清理。
    """
    for name in list(sys.modules):
        if name.split(".")[0] not in STUBBED_TOP_LEVEL_MODULES:
            continue
        module = sys.modules.get(name)
        if module is None:
            continue
        if getattr(module, "__file__", None):
            continue
        sys.modules.pop(name, None)



class DefectGateSkillDefinitionTests(unittest.TestCase):
    def test_skill_is_discoverable_with_runtime_contract(self):
        """技能目录可被发现，runtime.json 声明了提示词与必填输入。"""
        purge_stubbed_modules()

        from app.skillrun.registry import list_skills

        skills = {skill.skill_id: skill for skill in list_skills(SKILLS_DIR)}

        self.assertIn("jira-gate-bug", skills)
        skill = skills["jira-gate-bug"]
        self.assertTrue(skill.description)
        self.assertEqual(skill.required_inputs, ("jira_url",))
        self.assertEqual(skill.timeout_seconds, 3600)
        self.assertIn("analysis-cli.mjs", skill.prompt_template)
        self.assertIn("jira-cli.mjs", skill.prompt_template)

    def test_skill_documents_the_whole_flow(self):
        """SKILL.md 必须覆盖完整流程，避免遗漏任一判定分支。"""
        content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        for required in (
            "完整性检查",
            "打回",
            "自查结果检查",
            "自动故障分析",
            "analysis-cli.mjs",
            "jira-cli.mjs",
            "HTML",
            "gate-set",
            "attach",
            "ANALYSIS_API_TOKEN",
            "rejectTransitionName",
        ):
            self.assertIn(required, content)

    def test_references_define_judgement_rules(self):
        """判定依据必须落在参考资料里，而不是让模型自行发挥。"""
        checklist = (SKILL_DIR / "references" / "checklist.md").read_text(encoding="utf-8")
        self_check = (SKILL_DIR / "references" / "self-check.md").read_text(encoding="utf-8")
        jira_api = (SKILL_DIR / "references" / "jira-api.md").read_text(encoding="utf-8")

        for required in ("MUST", "REDLINE", "复现步骤", "时间信息", "日志"):
            self.assertIn(required, checklist)
        for required in ("自查", "结论", "证据", "selfCheckKeywords"):
            self.assertIn(required, self_check)
        for required in ("/rest/api/2/issue/{KEY}/comment", "/attachments", "transitions"):
            self.assertIn(required, jira_api)

    def test_cli_entrypoints_expose_required_commands(self):
        """两个命令行入口必须暴露流程需要的子命令与参数。"""
        jira_cli = (SKILL_DIR / "scripts" / "jira-cli.mjs").read_text(encoding="utf-8")
        analysis_cli = (SKILL_DIR / "scripts" / "analysis-cli.mjs").read_text(encoding="utf-8")

        for command in ("selfcheck", "attachments", "comment", "attach", "gate-set", "transitions"):
            self.assertIn('"' + command + '"', jira_cli)
        for option in ("--dir", "--out", "--product", "--module", "--json-summary"):
            self.assertIn(option, analysis_cli)

    @unittest.skipIf(NODE_BIN is None, "需要 node 运行时才能校验技能脚本")
    def test_scripts_are_valid_node_modules(self):
        """技能脚本必须是可解析的 ES 模块，避免部署后才暴露语法错误。"""
        for name in ("jira.mjs", "jira-cli.mjs", "analysis.mjs", "analysis-cli.mjs", "report.mjs"):
            result = subprocess.run(
                [NODE_BIN, "--check", str(SKILL_DIR / "scripts" / name)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, f"{name} 语法校验失败：{result.stderr}")


class DefectGateScriptBehaviourTests(unittest.TestCase):
    """直接执行技能脚本，验证报告渲染与自查结果判定的真实行为。"""

    SAMPLE_PAYLOAD = {
        "issueKey": "KEY-1234",
        "jiraUrl": "https://jira.in.wezhuiyi.com/browse/KEY-1234",
        "scope": {"productName": "客户服务", "moduleName": "工单管理", "tagVersion": "v3.2.1"},
        "files": [{"filename": "server.log", "kind": "日志", "size": 2048}],
        "tasks": [
            {
                "label": "日志分析",
                "taskId": "task-1",
                "result": {
                    "analysis_evidence": {"code_snippet_count": 1, "grouped_log_errors": [{"signature": "timeout", "count": 3}]},
                    "issue_conclusion": {
                        "issue_category_label": "代码问题",
                        "conclusion_summary": "回调超时 <script>alert(1)</script>",
                        "confidence": 0.62,
                        "issue_count": 1,
                        "issues": [{"title": "回调超时", "root_cause": "未设置超时", "confidence": 0.6}],
                    },
                },
            }
        ],
    }

    def run_node(self, driver):
        """在仓库目录内执行一段 ESM 驱动代码并返回 stdout。"""
        result = subprocess.run(
            [NODE_BIN, "--input-type=module", "-e", driver],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(BACKEND_DIR.parent),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    @unittest.skipIf(NODE_BIN is None, "需要 node 运行时才能执行技能脚本")
    def test_report_renders_styled_html_and_escapes_model_output(self):
        """报告必须包含关键章节，且对模型输出做 HTML 转义。"""
        report_url = (SKILL_DIR / "scripts" / "report.mjs").as_uri()
        driver = """
const { renderAnalysisHtml } = await import("__REPORT__");
const fs = await import("node:fs/promises");
const payload = JSON.parse(await fs.readFile(process.argv[1], "utf8"));
const html = renderAnalysisHtml(payload);
const checks = {
  escaped: html.includes("&lt;script&gt;") && !html.includes("<script>"),
  hasStyle: html.includes("<style>") ,
  hasConclusion: html.includes("回调超时"),
  hasEvidence: html.includes("分析输入") && html.includes("证据概览"),
  hasTask: html.includes("task-1"),
};
console.log(JSON.stringify(checks));
""".replace("__REPORT__", report_url)

        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "payload.json"
            payload_path.write_text(json.dumps(self.SAMPLE_PAYLOAD, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [NODE_BIN, "-e", driver, str(payload_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=str(BACKEND_DIR.parent),
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        checks = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(checks["escaped"], "模型输出必须做 HTML 转义")
        self.assertTrue(checks["hasStyle"], "报告必须自带样式")
        self.assertTrue(checks["hasConclusion"])
        self.assertTrue(checks["hasEvidence"])
        self.assertTrue(checks["hasTask"])

    @unittest.skipIf(NODE_BIN is None, "需要 node 运行时才能执行技能脚本")
    def test_self_check_detection_requires_conclusion_and_evidence(self):
        """只有同时包含自查动作、结论与证据的评论才算有效自查结果。"""
        jira_url = (SKILL_DIR / "scripts" / "jira.mjs").as_uri()
        driver = """
const { findSelfCheckComments, normalizeIssue } = await import("__JIRA__");
const issue = normalizeIssue({
  key: "KEY-1",
  id: "1",
  self: "https://jira.in.wezhuiyi.com/rest/api/2/issue/1",
  fields: {
    summary: "工单回调报错",
    description: "实际：报错",
    comment: { total: 2, comments: [
      { id: "1", author: { displayName: "张三", name: "zhangsan" }, created: "2026-09-20T09:40:00Z",
        body: "【自查结果】结论：回调超时。证据：server.log 21:10 callback timeout，已复现。" },
      { id: "2", author: { displayName: "李四", name: "lisi" }, created: "2026-09-20T09:50:00Z", body: "已自查" },
    ] },
  },
});
console.log(JSON.stringify(findSelfCheckComments(issue)));
""".replace("__JIRA__", jira_url)

        output = self.run_node(driver)
        payload = json.loads(output.strip().splitlines()[-1])

        self.assertTrue(payload["found"])
        self.assertEqual([item["commentId"] for item in payload["matches"]], ["1"])
        self.assertIn("回调超时", payload["reason"])


if __name__ == "__main__":
    unittest.main()
