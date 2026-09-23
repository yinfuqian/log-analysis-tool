"""技能注册表测试：覆盖 front matter 解析、技能发现与技能路径安全。"""
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.skillrun.registry import (
    SkillDefinitionError,
    SkillNotFoundError,
    list_skills,
    load_skill,
    parse_front_matter,
    resolve_skill,
)


SAMPLE_SKILL = """---
name: demo-skill
description: 用于测试的技能描述
---

# 测试技能
"""


class SkillRegistryTests(unittest.TestCase):
    def make_skills_root(self, layout=None):
        """构造临时技能目录，返回技能根目录路径。"""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        for name, content in (layout or {}).items():
            skill_dir = root / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        return root

    def test_parse_front_matter_reads_name_and_multiline_description(self):
        """front matter 需解析 name、description 并兼容缩进续行。"""
        text = "---\nname: demo\ndescription: 第一行\n  第二行\n---\n\n正文\n"

        metadata = parse_front_matter(text)

        self.assertEqual(metadata["name"], "demo")
        self.assertIn("第一行", metadata["description"])
        self.assertIn("第二行", metadata["description"])

    def test_parse_front_matter_returns_empty_without_header(self):
        """没有 front matter 的文档返回空元数据而不是报错。"""
        self.assertEqual(parse_front_matter("# 只有正文\n"), {})

    def test_parse_front_matter_strips_yaml_block_indicator(self):
        """折叠块描述（description: >）不能把指示符当成描述内容，否则会原样显示到 /skill/list。"""
        text = "---\nname: demo\ndescription: >\n  第一行\n  第二行\n---\n\n正文\n"

        metadata = parse_front_matter(text)

        self.assertEqual(metadata["description"], "第一行 第二行")

    def test_load_skill_reads_runtime_overrides(self):
        """runtime.json 可覆盖提示词模板、超时时间与必填输入。"""
        root = self.make_skills_root({"demo-skill": SAMPLE_SKILL})
        (root / "demo-skill" / "runtime.json").write_text(
            '{"prompt_template": "自定义 {jira_url}", "timeout_seconds": 60, "required_inputs": ["jira_url"]}',
            encoding="utf-8",
        )

        skill = load_skill(root / "demo-skill", "demo-skill")

        self.assertEqual(skill.skill_id, "demo-skill")
        self.assertEqual(skill.timeout_seconds, 60)
        self.assertEqual(skill.prompt_template, "自定义 {jira_url}")
        self.assertEqual(skill.required_inputs, ("jira_url",))

    def test_load_skill_rejects_invalid_runtime_json(self):
        """runtime.json 不是合法 JSON 时抛出技能定义异常。"""
        root = self.make_skills_root({"demo-skill": SAMPLE_SKILL})
        (root / "demo-skill" / "runtime.json").write_text("{不是 JSON", encoding="utf-8")

        with self.assertRaises(SkillDefinitionError):
            load_skill(root / "demo-skill", "demo-skill")

    def test_list_skills_skips_broken_and_hidden_directories(self):
        """技能列表跳过隐藏目录与损坏技能，不影响其余技能。"""
        root = self.make_skills_root({"demo-skill": SAMPLE_SKILL, "_wip": SAMPLE_SKILL})
        broken = root / "broken"
        broken.mkdir()
        (broken / "SKILL.md").write_text(SAMPLE_SKILL, encoding="utf-8")
        (broken / "runtime.json").write_text("{不是 JSON", encoding="utf-8")

        skills = list_skills(root)

        self.assertEqual([item.skill_id for item in skills], ["demo-skill"])

    def test_list_skills_returns_empty_when_directory_missing(self):
        """技能根目录不存在时返回空列表而不是抛错。"""
        self.assertEqual(list_skills(Path(tempfile.gettempdir()) / "missing-skills-dir"), [])

    def test_resolve_skill_rejects_path_traversal(self):
        """skill_id 必须匹配白名单字符集，禁止通过路径穿越读取目录外内容。"""
        root = self.make_skills_root({"demo-skill": SAMPLE_SKILL})

        for candidate in ("..", "../demo-skill", "/etc", "Demo skill"):
            with self.assertRaises(SkillDefinitionError):
                resolve_skill(root, candidate)

    def test_resolve_skill_reports_missing_skill(self):
        """技能目录不存在时抛出未找到异常。"""
        root = self.make_skills_root({"demo-skill": SAMPLE_SKILL})

        with self.assertRaises(SkillNotFoundError):
            resolve_skill(root, "not-installed")
