#!/usr/bin/env bash
# 在 macOS 上构建故障分析工具客户端，默认生成 Intel 与 Apple Silicon 通用应用。
set -euo pipefail

cd "$(dirname "$0")"

TARGET_ARCH="${1:-universal2}"
MACOS_PYTHON_VERSION="${MACOS_PYTHON_VERSION:-3.11.9}"
MACOS_CODESIGN_IDENTITY="${MACOS_CODESIGN_IDENTITY:--}"
# macOS 客户端固定连接生产故障分析服务，打包时不需要手动 export。
WINDOWS_CLIENT_BACKEND_URL="http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi"
export WINDOWS_CLIENT_BACKEND_URL
PYTHON_MINOR_VERSION="${MACOS_PYTHON_VERSION%.*}"
VENV_DIR="${VENV_DIR:-.venv-macos-${TARGET_ARCH}}"
TEMP_DIR=""
BUILD_INFO_BACKUP=""

case "$TARGET_ARCH" in
  universal2|arm64|x86_64) ;;
  *)
    echo "不支持的目标架构：${TARGET_ARCH}。可用值：universal2、arm64、x86_64。" >&2
    exit 2
    ;;
esac

cleanup() {
  local exit_code=$?

  if [[ -n "${BUILD_INFO_BACKUP:-}" && -f "$BUILD_INFO_BACKUP" ]]; then
    cp "$BUILD_INFO_BACKUP" client_build_info.py
  fi

  if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi

  exit "$exit_code"
}
trap cleanup EXIT

fail() {
  echo "错误：$*" >&2
  exit 1
}

require_macos_tools() {
  [[ "$(uname -s)" == "Darwin" ]] || fail "macOS 客户端只能在 macOS 系统上构建。"

  local missing_tools=()
  local tool
  for tool in curl lipo ditto codesign; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing_tools+=("$tool")
    fi
  done

  if (( ${#missing_tools[@]} > 0 )); then
    echo "缺少 macOS 构建工具：${missing_tools[*]}。" >&2
    echo "请先执行 xcode-select --install，完成安装后重新运行本脚本。" >&2
    exit 1
  fi
}

binary_arches() {
  lipo -archs "$1" 2>/dev/null || true
}

python_supports_target() {
  local python_path="$1"
  [[ -x "$python_path" ]] || return 1

  local arches
  arches="$(binary_arches "$python_path")"
  [[ -n "$arches" ]] || return 1

  case "$TARGET_ARCH" in
    universal2)
      [[ " $arches " == *" arm64 "* && " $arches " == *" x86_64 "* ]]
      ;;
    arm64)
      [[ " $arches " == *" arm64 "* ]]
      ;;
    x86_64)
      [[ " $arches " == *" x86_64 "* ]]
      ;;
  esac
}

find_compatible_python() {
  local candidates=()
  local command_python=""

  if [[ -n "${MACOS_PYTHON:-}" ]]; then
    candidates+=("$MACOS_PYTHON")
  fi

  candidates+=(
    "/Library/Frameworks/Python.framework/Versions/${PYTHON_MINOR_VERSION}/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/${PYTHON_MINOR_VERSION}/bin/python${PYTHON_MINOR_VERSION}"
  )

  command_python="$(command -v python3 2>/dev/null || true)"
  if [[ -n "$command_python" ]]; then
    candidates+=("$command_python")
  fi

  local candidate
  for candidate in "${candidates[@]}"; do
    if python_supports_target "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

install_official_python() {
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fault-analyzer-python.XXXXXX")"
  local python_pkg="${TEMP_DIR}/python-${MACOS_PYTHON_VERSION}-macos11.pkg"
  local python_pkg_url="https://www.python.org/ftp/python/${MACOS_PYTHON_VERSION}/python-${MACOS_PYTHON_VERSION}-macos11.pkg"

  echo "未找到支持 ${TARGET_ARCH} 的 Python，开始下载官方 Universal 2 Python ${MACOS_PYTHON_VERSION}。"
  echo "下载地址：${python_pkg_url}"
  curl --fail --location --retry 3 --retry-delay 2 --output "$python_pkg" "$python_pkg_url"

  echo "开始安装 Python。macOS 可能要求输入管理员密码。"
  sudo installer -pkg "$python_pkg" -target /
}

verify_output_architecture() {
  local executable_path="$1"
  local arches
  arches="$(binary_arches "$executable_path")"
  [[ -n "$arches" ]] || fail "无法读取应用主程序架构：${executable_path}"

  case "$TARGET_ARCH" in
    universal2)
      [[ " $arches " == *" arm64 "* ]] || fail "构建产物缺少 arm64 架构，实际架构：${arches}"
      [[ " $arches " == *" x86_64 "* ]] || fail "构建产物缺少 x86_64 架构，实际架构：${arches}"
      ;;
    arm64)
      [[ " $arches " == *" arm64 "* ]] || fail "构建产物不是 arm64，实际架构：${arches}"
      ;;
    x86_64)
      [[ " $arches " == *" x86_64 "* ]] || fail "构建产物不是 x86_64，实际架构：${arches}"
      ;;
  esac

  echo "应用主程序架构验证通过：${arches}"
}

sign_application() {
  local app_path="$1"

  if [[ "$MACOS_CODESIGN_IDENTITY" == "-" ]]; then
    echo "未配置 Apple Developer ID，使用临时签名。"
    codesign --force --deep --sign - "$app_path"
  else
    echo "使用签名身份：${MACOS_CODESIGN_IDENTITY}"
    codesign --force --deep --options runtime --timestamp --sign "$MACOS_CODESIGN_IDENTITY" "$app_path"
  fi

  codesign --verify --deep --strict --verbose=2 "$app_path"
}

require_macos_tools

BUILD_PYTHON="$(find_compatible_python || true)"
if [[ -z "$BUILD_PYTHON" ]]; then
  install_official_python
  BUILD_PYTHON="$(find_compatible_python || true)"
fi

[[ -n "$BUILD_PYTHON" ]] || fail "Python 安装完成后仍未找到支持 ${TARGET_ARCH} 的解释器。"
python_supports_target "$BUILD_PYTHON" || fail "Python 架构验证失败：${BUILD_PYTHON}"

echo "目标架构：${TARGET_ARCH}"
echo "构建 Python：${BUILD_PYTHON}"
echo "Python 架构：$(binary_arches "$BUILD_PYTHON")"
"$BUILD_PYTHON" --version

if [[ -x "$VENV_DIR/bin/python" ]] && ! python_supports_target "$VENV_DIR/bin/python"; then
  echo "现有虚拟环境架构不匹配，重新创建：${VENV_DIR}"
  rm -rf "$VENV_DIR"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$BUILD_PYTHON" -m venv "$VENV_DIR"
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
python_supports_target "$VENV_PYTHON" || fail "虚拟环境 Python 不支持目标架构：${TARGET_ARCH}"

echo "正在安装或更新客户端打包依赖。"
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -r requirements.txt
"$VENV_PYTHON" -m pip install "pyinstaller>=6,<7"

if [[ -z "$TEMP_DIR" ]]; then
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/fault-analyzer-build.XXXXXX")"
fi
BUILD_INFO_BACKUP="${TEMP_DIR}/client_build_info.py"
cp client_build_info.py "$BUILD_INFO_BACKUP"

"$VENV_PYTHON" update_build_info.py

APP_PATH="dist/FaultAnalyzerClient.app"
APP_EXECUTABLE="${APP_PATH}/Contents/MacOS/FaultAnalyzerClient"
ZIP_PATH="dist/FaultAnalyzerClient-macos-${TARGET_ARCH}.zip"

rm -rf "build/LogAnalyzerClient-macos" "$APP_PATH"
rm -f "$ZIP_PATH"

echo "开始执行 PyInstaller 构建。"
MACOS_TARGET_ARCH="$TARGET_ARCH" "$VENV_PYTHON" -m PyInstaller --clean --noconfirm LogAnalyzerClient-macos.spec

[[ -d "$APP_PATH" ]] || fail "未生成应用目录：${APP_PATH}"
[[ -f "$APP_EXECUTABLE" ]] || fail "未生成应用主程序：${APP_EXECUTABLE}"

verify_output_architecture "$APP_EXECUTABLE"
sign_application "$APP_PATH"

ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
[[ -f "$ZIP_PATH" ]] || fail "ZIP 安装包生成失败：${ZIP_PATH}"

echo
echo "macOS 客户端构建完成："
echo "$(pwd)/${APP_PATH}"
echo "$(pwd)/${ZIP_PATH}"
