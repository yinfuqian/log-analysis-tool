#!/usr/bin/env bash
# build-macos 脚本负责后端或客户端的启动、构建与运行环境准备。
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR="${VENV_DIR:-.venv-macos}"

echo "macOS architecture: $(uname -m)"
echo "System python: $(python3 --version 2>&1)"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -c 'import platform, sys; print("Build python:", sys.version.split()[0], platform.machine())'
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip --version
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

cp client_build_info.py client_build_info.py.bak
restore_build_info() {
  if [ -f client_build_info.py.bak ]; then
    mv client_build_info.py.bak client_build_info.py
  fi
}
trap restore_build_info ERR

"$VENV_DIR/bin/python" update_build_info.py
"$VENV_DIR/bin/python" -m PyInstaller --clean --noconfirm LogAnalyzerClient-macos.spec

rm -f client_build_info.py.bak
trap - ERR

if command -v ditto >/dev/null 2>&1; then
  ditto -c -k --keepParent "dist/FaultAnalyzerClient.app" "dist/FaultAnalyzerClient-macos.zip"
fi

echo
echo "Build complete:"
echo "$(pwd)/dist/FaultAnalyzerClient.app"
if [ -f "dist/FaultAnalyzerClient-macos.zip" ]; then
  echo "$(pwd)/dist/FaultAnalyzerClient-macos.zip"
fi
