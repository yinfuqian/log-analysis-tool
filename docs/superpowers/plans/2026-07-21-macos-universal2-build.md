# macOS Universal 2 Client Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide one macOS build script that automatically installs an official Universal 2 Python when needed, installs project dependencies, and produces a verified Intel/Apple Silicon client package.

**Architecture:** Keep orchestration in `windows-client/build-macos.sh`, pass the selected architecture to the existing PyInstaller spec through an environment variable, and verify the Mach-O output before packaging. Static contract tests run on Windows/Linux, while the script performs native build, signing, and architecture verification only on macOS.

**Tech Stack:** Bash, Python 3.11 Universal 2, PyInstaller, macOS `lipo`, `codesign`, `ditto`, Python `unittest`.

---

### Task 1: Add failing macOS build contract tests

**Files:**
- Create: `windows-client/tests/test_macos_build_contract.py`
- Test: `windows-client/tests/test_macos_build_contract.py`

- [ ] **Step 1: Write the failing contract tests**

Create tests that read `build-macos.sh` and `LogAnalyzerClient-macos.spec` as text and assert the following concrete contract:

```python
import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1]


class MacOSBuildContractTests(unittest.TestCase):
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
        self.assertIn('pip install -r requirements.txt', self.script)
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
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m unittest windows-client.tests.test_macos_build_contract -v
```

Expected: failures for the missing architecture parameter, Python auto-install, exit cleanup, output verification, and spec environment configuration.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add windows-client/tests/test_macos_build_contract.py
git commit -m "test: define macos universal2 build contract"
```

### Task 2: Implement architecture-aware macOS packaging

**Files:**
- Modify: `windows-client/build-macos.sh`
- Modify: `windows-client/LogAnalyzerClient-macos.spec`
- Test: `windows-client/tests/test_macos_build_contract.py`

- [ ] **Step 1: Add target selection and tool checks**

Make `universal2` the default and reject unsupported values:

```bash
TARGET_ARCH="${1:-universal2}"
case "$TARGET_ARCH" in
  universal2|arm64|x86_64) ;;
  *) echo "不支持的目标架构: $TARGET_ARCH" >&2; exit 2 ;;
esac
```

Require macOS and the system-provided `curl`, `lipo`, `ditto`, and `codesign`; missing developer tools must produce a Chinese `xcode-select --install` instruction.

- [ ] **Step 2: Add official Python discovery and installation**

Use `MACOS_PYTHON_VERSION` with a pinned Python 3.11 default. Search `/Library/Frameworks/Python.framework/Versions/<major.minor>/bin/python3`, then `python3`. Validate the executable with `lipo -archs`. If no executable satisfies the target, download:

```bash
PYTHON_PKG_URL="https://www.python.org/ftp/python/${MACOS_PYTHON_VERSION}/python-${MACOS_PYTHON_VERSION}-macos11.pkg"
curl --fail --location --retry 3 --output "$PYTHON_PKG" "$PYTHON_PKG_URL"
sudo installer -pkg "$PYTHON_PKG" -target /
```

After installation, locate and validate Python again; exit non-zero if it is still unavailable or has the wrong architecture.

- [ ] **Step 3: Add isolated dependency installation and safe cleanup**

Use `.venv-macos-${TARGET_ARCH}`, install build tools and client dependencies automatically, and register an EXIT trap before modifying build information:

```bash
cleanup() {
  if [[ -n "${BUILD_INFO_BACKUP:-}" && -f "$BUILD_INFO_BACKUP" ]]; then
    cp "$BUILD_INFO_BACKUP" client_build_info.py
  fi
  [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]] && rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -r requirements.txt
"$VENV_PYTHON" -m pip install "pyinstaller>=6,<7"
```

- [ ] **Step 4: Pass architecture into PyInstaller and verify the app**

In the spec, import `os`, read `MACOS_TARGET_ARCH`, and use the value for `EXE.target_arch`:

```python
import os

target_arch = os.getenv("MACOS_TARGET_ARCH", "universal2")
# ...
target_arch=target_arch,
```

Build with `MACOS_TARGET_ARCH="$TARGET_ARCH"`, inspect `dist/FaultAnalyzerClient.app/Contents/MacOS/FaultAnalyzerClient` using `lipo -archs`, and ensure both architectures exist for Universal 2.

- [ ] **Step 5: Sign and package the verified app**

Use `${MACOS_CODESIGN_IDENTITY:--}` as the signing identity, verify the signature, and generate an architecture-specific ZIP filename with `ditto`.

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run:

```powershell
python -m unittest windows-client.tests.test_macos_build_contract -v
```

Expected: all macOS build contract tests pass.

- [ ] **Step 7: Commit the implementation**

```powershell
git add windows-client/build-macos.sh windows-client/LogAnalyzerClient-macos.spec
git commit -m "feat: build universal macos client"
```

### Task 3: Document and verify the release workflow

**Files:**
- Modify: `windows-client/README.md`
- Modify: `windows-client/MACOS_BUILD.md`
- Test: `windows-client/tests/test_macos_build_contract.py`

- [ ] **Step 1: Update macOS build instructions**

Document the default Universal 2 command, optional `arm64` and `x86_64` commands, `MACOS_PYTHON_VERSION`, the built-in production backend address, `MACOS_CODESIGN_IDENTITY`, administrator-password requirement, LF line-ending requirement, output paths, and the limitation that real Mach-O verification must run on macOS.

- [ ] **Step 2: Run client tests**

Run:

```powershell
python -m unittest discover -s windows-client/tests -v
```

Expected: all desktop client tests pass.

- [ ] **Step 3: Run repository safety checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended implementation files and the user's pre-existing `windows-client/client_build_info.py` modification remain.

- [ ] **Step 4: Commit documentation**

```powershell
git add windows-client/README.md windows-client/MACOS_BUILD.md
git commit -m "docs: explain universal macos packaging"
```
