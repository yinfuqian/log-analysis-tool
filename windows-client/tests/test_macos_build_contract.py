import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1]


class MacOSBuildContractTests(unittest.TestCase):
    """验证 macOS 打包脚本具备跨架构构建所需的静态合同。"""

    @classmethod
    def setUpClass(cls):
        cls.script = (CLIENT_DIR / "build-macos.sh").read_text(encoding="utf-8")
        cls.spec = (CLIENT_DIR / "LogAnalyzerClient-macos.spec").read_text(encoding="utf-8")

    def test_universal2_is_default_and_single_architectures_are_supported(self):
        self.assertIn('TARGET_ARCH="${1:-universal2}"', self.script)
        self.assertIn("universal2|arm64|x86_64", self.script)

    def test_missing_python_is_downloaded_from_official_https_origin(self):
        self.assertIn("MACOS_PYTHON_VERSION", self.script)
        self.assertIn("https://www.python.org/ftp/python/", self.script)
        self.assertIn("sudo installer", self.script)

    def test_dependencies_and_pyinstaller_are_installed_automatically(self):
        self.assertIn("pip install -r requirements.txt", self.script)
        self.assertIn('pip install "pyinstaller', self.script)

    def test_build_info_is_restored_on_every_exit(self):
        self.assertIn("trap cleanup EXIT", self.script)

    def test_output_is_verified_signed_and_zipped(self):
        self.assertIn("lipo -archs", self.script)
        self.assertIn("codesign", self.script)
        self.assertIn("ditto -c -k --keepParent", self.script)

    def test_spec_uses_requested_target_architecture(self):
        self.assertIn('os.getenv("MACOS_TARGET_ARCH", "universal2")', self.spec)
        self.assertIn("target_arch=target_arch", self.spec)


if __name__ == "__main__":
    unittest.main()
