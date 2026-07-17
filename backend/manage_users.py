import argparse

from app.auth.users import UserStore


def validate_users_file(path):
    store = UserStore(path)
    return store.user_count()


def main(argv=None):
    parser = argparse.ArgumentParser(description="日志分析系统 CSV 用户文件检查工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="检查 users.csv 格式")
    validate_parser.add_argument("path", help="users.csv 文件路径")
    args = parser.parse_args(argv)

    if args.command == "validate":
        count = validate_users_file(args.path)
        print(f"用户文件有效，共 {count} 个用户")


if __name__ == "__main__":
    main()
