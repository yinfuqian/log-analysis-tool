"""update build info 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import argparse
import json
import os
import re
from datetime import date
from pathlib import Path


BUILD_INFO_PATH = Path(__file__).with_name("client_build_info.py")
PROJECT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
VERSION_PATTERN = re.compile(r'APP_VERSION\s*=\s*"v(\d+)\.(\d+)\.(\d+)"')


def read_current_version():
    """读取并返回 read_current_version 对应的业务数据，保持现有调用约定。"""
    if not BUILD_INFO_PATH.exists():
        return (1, 0, 0)
    match = VERSION_PATTERN.search(BUILD_INFO_PATH.read_text(encoding="utf-8"))
    if not match:
        return (1, 0, 0)
    return tuple(int(part) for part in match.groups())


def bump_patch(version):
    """处理 bump_patch 对应的业务步骤，并向调用方返回所需结果。"""
    major, minor, patch = version
    return major, minor, patch + 1


def read_backend_url(env_path=PROJECT_ENV_PATH):
    """读取并返回 read_backend_url 对应的业务数据，保持现有调用约定。"""
    environment_value = str(os.getenv("WINDOWS_CLIENT_BACKEND_URL") or "").strip()
    if environment_value:
        return environment_value.rstrip("/")
    path = Path(env_path)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "WINDOWS_CLIENT_BACKEND_URL":
                return value.strip().strip('"').strip("'").rstrip("/")
    return "http://127.0.0.1:5000"


def write_build_info(version, release_date, backend_url):
    """保存 write_build_info 对应的业务数据，保持现有调用约定。"""
    version_text = f"v{version[0]}.{version[1]}.{version[2]}"
    BUILD_INFO_PATH.write_text(
        "\n".join([
            '"""Windows 客户端构建信息，由 update_build_info.py 在打包前统一生成。"""',
            "",
            f'APP_VERSION = "{version_text}"',
            f'APP_RELEASE_DATE = "{release_date}"',
            f"DEFAULT_BACKEND_URL = {json.dumps(backend_url, ensure_ascii=False)}",
            "",
        ]),
        encoding="utf-8",
    )
    return version_text


def main():
    """执行 main 对应的业务数据，保持现有调用约定。"""
    parser = argparse.ArgumentParser(description="Update client version and build date before packaging.")
    parser.add_argument("--no-bump", action="store_true", help="Only refresh build date, do not increment patch version.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Build date, default is today.")
    args = parser.parse_args()

    version = read_current_version()
    if not args.no_bump:
        version = bump_patch(version)

    backend_url = read_backend_url()
    version_text = write_build_info(version, args.date, backend_url)
    print(f"client build info updated: {version_text} fix on {args.date}, backend: {backend_url}")


if __name__ == "__main__":
    main()
