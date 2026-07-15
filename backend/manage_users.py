import argparse
import getpass

from werkzeug.security import generate_password_hash


def build_password_hash(password):
    if not str(password or ""):
        raise ValueError("密码不能为空")
    return generate_password_hash(password, method="scrypt")


def main(argv=None, password_reader=getpass.getpass):
    parser = argparse.ArgumentParser(description="日志分析系统用户配置辅助工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("hash-password", help="交互式生成密码哈希")
    args = parser.parse_args(argv)

    if args.command == "hash-password":
        password = password_reader("请输入密码: ")
        confirmation = password_reader("请再次输入密码: ")
        if password != confirmation:
            raise SystemExit("两次输入的密码不一致")
        print(build_password_hash(password))


if __name__ == "__main__":
    main()
