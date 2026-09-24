#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
扫描工程源码中是否存在健康检查端点实现。
输出 JSON 格式，包含是否找到规范端点 /readyz、/livez，以及其他可能端点列表。
兼容 Python 2.7 和 Python 3。
"""

from __future__ import print_function
import io
import json
import os
import re
import sys

# 支持的源码后缀
SOURCE_EXTS = {
    ".go", ".java", ".kt", ".py", ".js", ".ts", ".jsx", ".tsx",
    ".rs", ".cpp", ".cc", ".h", ".c",
}

# 规范端点
STANDARD_ENDPOINTS = {"/readyz", "/livez"}

# 常见替代端点（用于生成 TODO 提示）
ALTERNATIVE_ENDPOINTS = {"/health", "/check", "/hello", "/actuator/health"}

SKIP_DIRS = {"node_modules", "vendor", "build", "dist", "target"}


def _should_skip_dir(dirpath_parts):
    """根据目录名判断是否需要跳过。"""
    for part in dirpath_parts:
        # 跳过隐藏目录和常见依赖/构建目录
        if part.startswith(".") or part in SKIP_DIRS:
            return True
    return False


def _endswith_any(filename, suffixes):
    """检查文件名是否以任一后缀结尾。"""
    for suffix in suffixes:
        if filename.endswith(suffix):
            return True
    return False


def find_endpoints(root):
    """遍历源码，查找规范端点和替代端点。"""
    found_standard = set()
    found_alternative = set()

    for dirpath, _dirnames, filenames in os.walk(root):
        parts = dirpath.split(os.sep)
        if _should_skip_dir(parts):
            continue

        for filename in filenames:
            if not _endswith_any(filename, SOURCE_EXTS):
                continue
            filepath = os.path.join(dirpath, filename)
            try:
                with io.open(filepath, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            # 搜索规范端点
            for endpoint in STANDARD_ENDPOINTS:
                pattern = re.compile(re.escape(endpoint) + r'[^\w/]')
                if pattern.search(content):
                    found_standard.add(endpoint)

            # 搜索替代端点
            for endpoint in ALTERNATIVE_ENDPOINTS:
                pattern = re.compile(re.escape(endpoint) + r'[^\w/]')
                if pattern.search(content):
                    found_alternative.add(endpoint)

    return found_standard, found_alternative


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    found_standard, found_alternative = find_endpoints(root)

    has_both = {"/readyz", "/livez"}.issubset(found_standard)
    if has_both:
        recommendation = "standard"
    elif found_alternative:
        recommendation = "todo_check"
    else:
        recommendation = "todo_implement"

    result = {
        "has_readyz": "/readyz" in found_standard,
        "has_livez": "/livez" in found_standard,
        "standard_endpoints": sorted(found_standard),
        "alternative_endpoints": sorted(found_alternative),
        "recommendation": recommendation,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
