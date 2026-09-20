"""技能流转契约测试：锁定「仅不达标时流转到『评审中』并 @ 流转人」的脚本与文档约定。"""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PROJECT_ROOT / "skills" / "jira-gate-1"
SKILL_PATH = SKILL_DIR / "SKILL.md"
JIRA_SCRIPT_PATH = SKILL_DIR / "scripts" / "jira.mjs"
CLI_PATH = SKILL_DIR / "scripts" / "jira-cli.mjs"
API_DOC_PATH = SKILL_DIR / "references" / "jira-api.md"


class SkillJiraGateFlowTests(unittest.TestCase):
    def test_skill_documents_fail_only_transition(self):
        """SKILL.md 必须写明只在结论不达标时流转，达标不做任何状态变更。"""
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("### 9. 交付顺序与「不达标时流转状态并 @ 流转人」", text)
        self.assertIn("不做任何状态变更", text)
        self.assertIn("评审中", text)
        # 旧口径「一律不流转状态」必须已被替换，否则与本次需求冲突。
        self.assertNotIn("不流转状态、不指派经办人", text)

    def test_comment_template_mentions_flow_owner(self):
        """不达标评论模板必须带 @ 流转人的「待处理人」行，且注明达标时省略。"""
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("待处理人：{{[~登录名]}}", text)
        self.assertIn("只在不达标时出现", text)

    def test_script_transition_matches_status_name_and_degrades(self):
        """流转脚本按目标状态名匹配，找不到流转时返回可读原因而不是抛错。"""
        source = JIRA_SCRIPT_PATH.read_text(encoding="utf-8")

        for name in ("listTransitions", "resolveFlowOwner", "transitionToStatus"):
            self.assertIn("export async function {0}".format(name), source)
        self.assertIn("already-in-target", source)
        self.assertIn('reason: "no-transition"', source)
        self.assertIn("flowOwnerField", source)
        # 回退顺序：优先配置字段，其次 assignee → reporter → creator。
        order = ['String(config.flowOwnerField || "assignee")', '"assignee"', '"reporter"', '"creator"']
        positions = [source.index(item) for item in order]
        self.assertEqual(positions, sorted(positions), "流转人回退顺序与预期不一致")

    def test_cli_exposes_flow_commands(self):
        """命令行入口必须提供 transitions / flow-owner / transition 三个子命令。"""
        source = CLI_PATH.read_text(encoding="utf-8")

        for token in ('case "transitions"', 'case "flow-owner"', 'case "transition"', "--to <目标状态>"):
            self.assertIn(token, source)

    def test_api_doc_covers_transition_permission_and_fallback(self):
        """接口文档需覆盖流转接口、TRANSITION_ISSUES 权限与找不到流转的降级说明。"""
        text = API_DOC_PATH.read_text(encoding="utf-8")

        self.assertIn("/rest/api/2/issue/{KEY}/transitions", text)
        self.assertIn("TRANSITION_ISSUES", text)
        self.assertIn("no-transition", text)
        self.assertIn("available", text)

    def test_flow_owner_defaults_to_assignee(self):
        """流转人默认口径为经办人，文档与脚本必须一致地声明这一点。"""
        skill_text = SKILL_PATH.read_text(encoding="utf-8")
        doc_text = API_DOC_PATH.read_text(encoding="utf-8")

        self.assertIn("口径就是经办人", skill_text)
        self.assertIn("取经办人 `assignee`", doc_text)


if __name__ == "__main__":
    unittest.main()
