import importlib.util
import tempfile
import unittest
from pathlib import Path


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
            version_text = module.write_build_info(version, "2026-06-27")

            self.assertEqual(version_text, "v1.2.4")
            content = build_info_path.read_text(encoding="utf-8")
            self.assertIn('APP_VERSION = "v1.2.4"', content)
            self.assertIn('APP_RELEASE_DATE = "2026-06-27"', content)


if __name__ == "__main__":
    unittest.main()
