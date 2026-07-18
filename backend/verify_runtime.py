"""故障分析工具容器构建和运行时自检命令。"""

import argparse
import json
import sys

from app.runtime_checks import run_build_checks, run_readiness_checks


def _print_result(result):
    """以 UTF-8 JSON 输出检查结果，便于 Docker 日志和人工排障。"""
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    """执行指定检查，并用退出码表示整体可用状态。"""
    parser = argparse.ArgumentParser(description="故障分析工具运行时自检")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="检查镜像内全部核心组件")
    group.add_argument("--runtime", action="store_true", help="检查外部依赖和运行目录")
    group.add_argument("--ocr", action="store_true", help="只检查 PaddleOCR 初始化与预测")
    args = parser.parse_args(argv)

    if args.runtime:
        from app import create_app

        application = create_app()
        with application.app_context():
            result = run_readiness_checks()
        success = result["ready"]
    else:
        result = run_build_checks()
        if args.ocr:
            result = {"ocr": result["ocr"]}
        success = all(item["ok"] for item in result.values())

    _print_result(result)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
