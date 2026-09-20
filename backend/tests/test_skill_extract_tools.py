"""技能附件解压契约测试：确认解压工具随镜像发布，且技能优先使用容器内命令、不自行安装。"""
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTRACT_PATH = PROJECT_ROOT / "skills" / "jira-gate-1" / "scripts" / "extract.py"
PROMPT_PATH = PROJECT_ROOT / "backend" / "app" / "skillrun" / "codex_runner.py"


class SkillExtractToolTests(unittest.TestCase):
    def test_extract_prefers_container_commands_before_windows_fallback(self):
        """rar 必须先尝试容器内已装的 bsdtar，再降级到 7z 与 Windows 自带的 tar。"""
        source = EXTRACT_PATH.read_text(encoding="utf-8")

        # 按首次出现位置比较，确保顺序为「容器内命令 → 桌面端兜底」。
        rar_order = ["bsdtar", "7z", "7zz", "7za", "unar", "unrar", "tar"]
        positions = [source.index('("{}",'.format(name)) for name in rar_order]
        self.assertEqual(positions, sorted(positions), "rar 解压命令顺序与预期不一致")

    def test_extract_failure_message_forbids_installing_software(self):
        """解压失败提示必须阻止 agent 在任务中安装软件。"""
        source = EXTRACT_PATH.read_text(encoding="utf-8")

        self.assertIn("请勿在任务中安装软件", source)

    def test_codex_prompt_forbids_runtime_package_installation(self):
        """执行提示词必须声明工具已预装，禁止 apt/pip/npm 安装。"""
        source = PROMPT_PATH.read_text(encoding="utf-8")

        self.assertIn("bsdtar", source)
        self.assertIn("不要执行 apt-get、yum、apk、pip、npm 等安装命令", source)


if __name__ == "__main__":
    unittest.main()