"""评审报告附件契约测试：锁定 review-jira-songlizhi 的引入方式与附件命名规则。"""
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = BACKEND_DIR.parent
SKILLS_ROOT = PROJECT_ROOT / "skills"
GATE_SKILL_DIR = SKILLS_ROOT / "jira-gate-1"
REVIEW_SKILL_DIR = SKILLS_ROOT / "review-jira-songlizhi"


class ReviewSkillVendoringTests(unittest.TestCase):
    def test_review_skill_files_are_shipped_with_the_repo(self):
        """新技能需随仓库分发：入口、提示词与零依赖脚本都要在。"""
        expected = [
            REVIEW_SKILL_DIR / "SKILL.md",
            REVIEW_SKILL_DIR / "prompts" / "normalize.md",
            REVIEW_SKILL_DIR / "prompts" / "semantic.md",
            REVIEW_SKILL_DIR / "bin" / "jira-fetch.mjs",
            REVIEW_SKILL_DIR / "bin" / "rulecheck.mjs",
            REVIEW_SKILL_DIR / "bin" / "report.mjs",
            REVIEW_SKILL_DIR / "bin" / "verify-semantic-quotes.mjs",
        ]
        for path in expected:
            self.assertTrue(path.is_file(), f"缺少技能文件：{path}")

    def test_review_skill_is_registered_as_usable_skill(self):
        """技能目录需满足注册表约定：front matter 的 name 等于目录名。"""
        from app.skillrun.registry import load_skill

        skill = load_skill(REVIEW_SKILL_DIR, "review-jira-songlizhi")

        self.assertEqual(skill.skill_id, "review-jira-songlizhi")
        self.assertTrue(skill.description)

    def test_review_skill_documents_container_adaptation(self):
        """新技能需声明容器内的技能目录、凭据桥接与只读边界。"""
        text = (REVIEW_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("/data/skills/review-jira-songlizhi", text)
        self.assertIn('export JIRA_PAT="$JIRA_TOKEN"', text)
        self.assertIn("只读边界不变", text)

    def test_review_skill_scripts_stay_read_only(self):
        """脚本层不得出现写请求，保持“拉取只读”的硬约束。"""
        fetch_source = (REVIEW_SKILL_DIR / "bin" / "jira-fetch.mjs").read_text(encoding="utf-8")

        for method in ("POST", "PUT", "DELETE"):
            self.assertNotIn(f"'{method}'", fetch_source)
            self.assertNotIn(f'"{method}"', fetch_source)


class ReportAttachmentContractTests(unittest.TestCase):
    def test_gate_skill_uploads_report_as_attachment(self):
        """jira-gate-1 需写明调用新技能、上传附件，且文件名以“宋立志”结尾。"""
        text = (GATE_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("### 11. 评审报告（review-jira-songlizhi）与附件上传", text)
        self.assertIn("/data/skills/review-jira-songlizhi", text)
        self.assertIn("<KEY>-需求评审报告-宋立志.md", text)
        self.assertIn("必须以「宋立志」结尾", text)
        self.assertIn("jira-cli.mjs attach", text)
        # 旧的“唯一交付物是评论”口径必须已让位于“评论 + 附件”。
        self.assertNotIn("唯一合规交付物是 Jira 评论", text)

    def test_upload_attachment_supports_custom_filename(self):
        """附件上传需支持 --name 改名，并让 fetch 自行生成 multipart 边界。"""
        source = (GATE_SKILL_DIR / "scripts" / "jira.mjs").read_text(encoding="utf-8")
        cli_source = (GATE_SKILL_DIR / "scripts" / "jira-cli.mjs").read_text(encoding="utf-8")

        self.assertIn("export async function uploadAttachment", source)
        self.assertIn("/attachments`", source)
        self.assertIn("options.body instanceof FormData", source)
        self.assertIn('case "attach"', cli_source)
        self.assertIn("--name <附件名>", cli_source)

    def test_attachment_api_and_permission_are_documented(self):
        """接口文档需覆盖附件上传接口与 CREATE_ATTACHMENTS 权限。"""
        text = (GATE_SKILL_DIR / "references" / "jira-api.md").read_text(encoding="utf-8")

        self.assertIn("/rest/api/2/issue/{KEY}/attachments", text)
        self.assertIn("CREATE_ATTACHMENTS", text)
        self.assertIn("## 10. 评审报告附件上传", text)

    def test_attach_failure_is_visible_via_exit_code(self):
        """上传失败必须置退出码 1 并在 stderr 告警，避免只看 exit code 就当成成功。"""
        cli_source = (GATE_SKILL_DIR / "scripts" / "jira-cli.mjs").read_text(encoding="utf-8")

        self.assertIn("process.exitCode = 1", cli_source)
        self.assertIn("[附件上传失败]", cli_source)
        self.assertIn('case "attach-list"', cli_source)

    def test_skill_requires_readback_after_upload(self):
        """SKILL.md 必须要求上传后读回确认，成功判定不看退出码。"""
        text = (GATE_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("上传后必须读回确认", text)
        self.assertIn("attach-list", text)
        self.assertIn("不要把失败说成成功", text)

    def test_execution_order_puts_transition_last(self):
        """执行顺序固定为 评论 → 门禁字段 → 附件 → 流转，流转必须是最后一个动作。"""
        skill_text = (GATE_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        doc_text = (GATE_SKILL_DIR / "references" / "jira-api.md").read_text(encoding="utf-8")

        skill_order = "写评论（含 @）→ 回写门禁字段 → 上传附件 → 流转状态"
        doc_order = "评论（含 @）→ 门禁字段 → 附件 → 流转"
        self.assertIn(skill_order, skill_text)
        self.assertIn(doc_order, doc_text)
        # 旧顺序（附件在流转之后）不得残留。
        self.assertNotIn("流转状态（仅不达标）→ 上传附件", skill_text)
        self.assertNotIn("流转状态（仅不达标）→ 上传附件", doc_text)

    def test_comment_template_ends_with_attachment_line(self):
        """评论末尾必须固定带一行「报告附件」，达标与不达标都要有。"""
        skill_text = (GATE_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        doc_text = (GATE_SKILL_DIR / "references" / "jira-api.md").read_text(encoding="utf-8")

        self.assertIn("* 报告附件：{{<KEY>-需求评审报告-宋立志.md}}", skill_text)
        self.assertIn("评论末尾固定的一行，达标与不达标都要有", skill_text)
        self.assertIn("报告附件：<KEY>-需求评审报告-宋立志.md（已上传）", doc_text)


if __name__ == "__main__":
    unittest.main()
