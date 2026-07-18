import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ReadmeContractTests(unittest.TestCase):
    def test_root_readme_documents_complete_release_workflow(self):
        """根文档必须覆盖部署、配置、验证、客户端和排障入口。"""
        readme_path = PROJECT_ROOT / "README.md"
        self.assertTrue(readme_path.is_file())
        content = readme_path.read_text(encoding="utf-8")

        for required in (
            "故障分析工具",
            "docker compose build",
            "gpt-5.6-sol",
            "OPENAI_REASONING_EFFORT=high",
            "PaddleOCR",
            "users.csv",
            "flask db upgrade",
            "/health/live",
            "/health/ready",
            "FaultAnalyzerClient.exe",
            "WINDOWS_CLIENT_BACKEND_URL",
            "故障排查",
        ):
            self.assertIn(required, content)
        self.assertFalse((PROJECT_ROOT / "README").exists())

    def test_client_docs_use_current_fault_analyzer_artifact_names(self):
        """桌面客户端文档不能继续展示旧的 LogAnalyzerClient 产物名。"""
        windows_doc = (PROJECT_ROOT / "windows-client" / "README.md").read_text(encoding="utf-8")
        macos_doc = (PROJECT_ROOT / "windows-client" / "MACOS_BUILD.md").read_text(encoding="utf-8")

        self.assertIn("FaultAnalyzerClient.exe", windows_doc)
        self.assertIn("FaultAnalyzerClient.app", windows_doc)
        self.assertIn("FaultAnalyzerClient.app", macos_doc)
        self.assertNotIn("LogAnalyzerClient.exe", windows_doc)
        self.assertNotIn("LogAnalyzerClient.app", macos_doc)


if __name__ == "__main__":
    unittest.main()
