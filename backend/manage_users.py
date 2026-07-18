"""manage users 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import argparse

from app.auth.users import UserStore
from app.branding import PRODUCT_NAME


def validate_users_file(path):
    """校验 validate_users_file 对应的业务数据，保持现有调用约定。"""
    store = UserStore(path)
    return store.user_count()


def main(argv=None):
    """执行 main 对应的业务数据，保持现有调用约定。"""
    parser = argparse.ArgumentParser(description=f"{PRODUCT_NAME} CSV 用户文件检查工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate", help="检查 users.csv 格式")
    validate_parser.add_argument("path", help="users.csv 文件路径")
    args = parser.parse_args(argv)

    if args.command == "validate":
        count = validate_users_file(args.path)
        print(f"用户文件有效，共 {count} 个用户")


if __name__ == "__main__":
    main()
