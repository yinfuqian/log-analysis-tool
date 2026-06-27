import argparse
import re
from datetime import date
from pathlib import Path


BUILD_INFO_PATH = Path(__file__).with_name("client_build_info.py")
VERSION_PATTERN = re.compile(r'APP_VERSION\s*=\s*"v(\d+)\.(\d+)\.(\d+)"')


def read_current_version():
    if not BUILD_INFO_PATH.exists():
        return (1, 0, 0)
    match = VERSION_PATTERN.search(BUILD_INFO_PATH.read_text(encoding="utf-8"))
    if not match:
        return (1, 0, 0)
    return tuple(int(part) for part in match.groups())


def bump_patch(version):
    major, minor, patch = version
    return major, minor, patch + 1


def write_build_info(version, release_date):
    version_text = f"v{version[0]}.{version[1]}.{version[2]}"
    BUILD_INFO_PATH.write_text(
        "\n".join([
            f'APP_VERSION = "{version_text}"',
            f'APP_RELEASE_DATE = "{release_date}"',
            "",
        ]),
        encoding="utf-8",
    )
    return version_text


def main():
    parser = argparse.ArgumentParser(description="Update client version and build date before packaging.")
    parser.add_argument("--no-bump", action="store_true", help="Only refresh build date, do not increment patch version.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Build date, default is today.")
    args = parser.parse_args()

    version = read_current_version()
    if not args.no_bump:
        version = bump_patch(version)

    version_text = write_build_info(version, args.date)
    print(f"client build info updated: {version_text} fix on {args.date}")


if __name__ == "__main__":
    main()
