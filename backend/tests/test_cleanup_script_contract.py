import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLEANUP_SCRIPT = PROJECT_ROOT / "scripts" / "clean_generated.ps1"


class CleanupScriptContractTests(unittest.TestCase):
    def test_cleanup_preserves_configuration_source_helper_and_release_artifact(self):
        """保留发布包模式只能删除明确允许的生成内容。"""
        self.assertTrue(CLEANUP_SCRIPT.is_file())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protected_files = (
                root / ".env",
                root / "users.csv",
                root / "backend" / "app.py",
                root / "frontend" / "app" / "log-analyze" / "build" / "chunkName.js",
                root / "windows-client" / "dist" / "FaultAnalyzerClient.exe",
            )
            generated_files = (
                root / "backend" / "__pycache__" / "app.pyc",
                root / "frontend" / "app" / "log-analyze" / "node_modules" / "package.json",
                root / "frontend" / "app" / "log-analyze" / "dist" / "index.html",
                root / "windows-client" / "build" / "temporary.txt",
                root / "backend" / "app" / "logs" / "runtime.log",
            )
            for path in protected_files + generated_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("data", encoding="utf-8")

            dry_run = self._run_cleanup(root, "-DryRun", "-KeepReleaseArtifacts")
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
            self.assertTrue(all(path.exists() for path in protected_files + generated_files))

            actual = self._run_cleanup(root, "-KeepReleaseArtifacts")
            self.assertEqual(actual.returncode, 0, actual.stderr)

            self.assertTrue(all(path.exists() for path in protected_files))
            self.assertTrue(all(not path.exists() for path in generated_files))

    def test_cleanup_script_avoids_git_clean_and_protects_workspace_boundary(self):
        """脚本必须通过受控路径删除，不能委托 git clean 扩大范围。"""
        source = CLEANUP_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("git clean", source.lower())
        self.assertIn("Resolve-Path", source)
        self.assertIn("Test-PathInsideWorkspace", source)
        self.assertIn("DryRun", source)
        self.assertIn("KeepReleaseArtifacts", source)

    @staticmethod
    def _run_cleanup(root: Path, *arguments: str):
        """在隔离临时目录中执行 PowerShell 清理脚本。"""
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(CLEANUP_SCRIPT),
                "-WorkspaceRoot",
                str(root),
                *arguments,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
