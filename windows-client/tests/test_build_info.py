import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "update_build_info.py"


def load_build_info_script():
    spec = importlib.util.spec_from_file_location("update_build_info_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildInfoTests(unittest.TestCase):
    def test_bumps_patch_version_and_writes_release_date(self):
        module = load_build_info_script()

        with tempfile.TemporaryDirectory() as temp_dir:
            build_info_path = Path(temp_dir) / "client_build_info.py"
            build_info_path.write_text(
                'APP_VERSION = "v1.2.3"\nAPP_RELEASE_DATE = "2026-06-01"\n',
                encoding="utf-8",
            )
            module.BUILD_INFO_PATH = build_info_path

            version = module.bump_patch(module.read_current_version())
            version_text = module.write_build_info(version, "2026-06-27", "https://api.example.com/logapi")

            self.assertEqual(version_text, "v1.2.4")
            content = build_info_path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith('"""Windows 客户端构建信息'))
            self.assertIn('APP_VERSION = "v1.2.4"', content)
            self.assertIn('APP_RELEASE_DATE = "2026-06-27"', content)
            self.assertIn('DEFAULT_BACKEND_URL = "https://api.example.com/logapi"', content)

    def test_backend_url_uses_environment_before_project_env_file(self):
        module = load_build_info_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("WINDOWS_CLIENT_BACKEND_URL=https://file.example.com/api\n", encoding="utf-8")
            with patch.dict(os.environ, {"WINDOWS_CLIENT_BACKEND_URL": "https://env.example.com/api"}, clear=False):
                backend_url = module.read_backend_url(env_path)

        self.assertEqual(backend_url, "https://env.example.com/api")

    def test_backend_url_falls_back_to_project_env_file(self):
        module = load_build_info_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("WINDOWS_CLIENT_BACKEND_URL=http://127.0.0.1:5000\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("WINDOWS_CLIENT_BACKEND_URL", None)
                backend_url = module.read_backend_url(env_path)

        self.assertEqual(backend_url, "http://127.0.0.1:5000")

    def test_backend_url_defaults_to_localhost_when_not_configured(self):
        module = load_build_info_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_env_path = Path(temp_dir) / ".env"
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("WINDOWS_CLIENT_BACKEND_URL", None)
                backend_url = module.read_backend_url(missing_env_path)

        self.assertEqual(backend_url, "http://127.0.0.1:5000")


if __name__ == "__main__":
    unittest.main()
