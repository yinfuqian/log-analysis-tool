#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
校验 docker-compose.yml 是否符合 CI v3 格式规范。
兼容 Python 2.7 和 Python 3。
"""

from __future__ import print_function
import io
import re
import sys

RUNTIME_PLACEHOLDERS = {"REGISTRY_ADDR"}


def _is_runtime_placeholder(var):
    return var in RUNTIME_PLACEHOLDERS or var.endswith("_IMAGE_TAG") or var.endswith("_WORKING_DIR")


def validate(path):
    content = _read_file(path)
    if not content:
        print("无法读取文件: " + path)
        return False

    errors = []
    lines = content.split("\n")

    # 1. 检查环境变量是否使用了带默认值的形式
    for i, line in enumerate(lines, start=1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # 查找 $VAR 或 ${VAR} 或 ${VAR:-default} 形式，变量名支持连字符
        for m in re.finditer(r'[$]([A-Z_][A-Z0-9_-]*)|[$]\{([A-Z_][A-Z0-9_-]*)(?::-[^}]*)?\}', line):
            var = m.group(1) or m.group(2)
            full = m.group(0)
            if not var:
                continue
            # 运行时占位符必须保持纯 $VAR 形式（无花括号、无默认值）
            if _is_runtime_placeholder(var):
                if full.startswith("${") or re.search(r':-[^}]+', full):
                    errors.append("第 {} 行: ${} 为运行时占位符，必须写成纯 ${} 形式，禁止使用花括号或默认值".format(i, var, var))
                continue
            # 普通变量要求使用带默认值的形式
            if not re.search(r'\$\{' + re.escape(var) + r':-[^}]+\}', full):
                errors.append("第 {} 行: 环境变量 ${} 缺少默认值形式，应改为 ${{{}:-default}}".format(i, var, var))

    # 2. 检查常见字符串值是否用双引号（image、container_name、hostname、restart 等右侧的值）
    string_keys = {"image", "container_name", "hostname", "restart", "shm_size"}
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)', stripped)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if key in string_keys and val:
                # 允许数字或者已带双引号
                if not (val.startswith('"') and val.endswith('"')) and not val.isdigit():
                    errors.append("第 {} 行: {} 的值 '{}' 建议使用双引号包裹".format(i, key, val))

    if errors:
        print("docker-compose.yml 校验未通过：")
        for err in errors:
            print("  - " + err)
        return False

    print("docker-compose.yml 校验通过")
    return True


def _read_file(path):
    try:
        with io.open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "docker-compose.yml"
    ok = validate(path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
