#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

cp client_build_info.py client_build_info.py.bak
restore_build_info() {
  if [ -f client_build_info.py.bak ]; then
    mv client_build_info.py.bak client_build_info.py
  fi
}
trap restore_build_info ERR

python3 update_build_info.py
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --clean --noconfirm LogAnalyzerClient-macos.spec

rm -f client_build_info.py.bak
trap - ERR

if command -v ditto >/dev/null 2>&1; then
  ditto -c -k --keepParent "dist/LogAnalyzerClient.app" "dist/LogAnalyzerClient-macos.zip"
fi

echo
echo "Build complete:"
echo "$(pwd)/dist/LogAnalyzerClient.app"
if [ -f "dist/LogAnalyzerClient-macos.zip" ]; then
  echo "$(pwd)/dist/LogAnalyzerClient-macos.zip"
fi
