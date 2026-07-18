#!/usr/bin/env python3
"""审计生产源码的中文模块职责、类说明、函数说明和脚本文件头注释。"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".venv-win",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "migrations",
    "node_modules",
    "tests",
}


class AuditIssue(NamedTuple):
    """表示一项缺失或不符合要求的源码维护说明。"""

    path: Path
    line: int
    message: str


def contains_chinese(value: str | None) -> bool:
    """判断说明文本是否至少包含一个中文字符。"""
    return bool(value and CHINESE_PATTERN.search(value))


def audit_python_file(path: Path) -> list[AuditIssue]:
    """检查 Python 模块以及其中所有类、同步函数和异步函数的中文文档字符串。"""
    source = path.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [AuditIssue(path, exc.lineno or 1, f"Python 语法无法解析：{exc.msg}")]

    issues: list[AuditIssue] = []
    if not contains_chinese(ast.get_docstring(tree, clean=False)):
        issues.append(AuditIssue(path, 1, "模块缺少中文职责说明"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if not contains_chinese(ast.get_docstring(node, clean=False)):
                issues.append(AuditIssue(path, node.lineno, f"类 {node.name} 缺少中文说明"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not contains_chinese(ast.get_docstring(node, clean=False)):
                issues.append(AuditIssue(path, node.lineno, f"函数 {node.name} 缺少中文说明"))
    return issues


def audit_text_file(path: Path) -> list[AuditIssue]:
    """检查前端、Shell 和 Batch 文件开头是否存在中文文件职责注释。"""
    source = path.read_text(encoding="utf-8-sig")
    header = "\n".join(source.splitlines()[:30])
    suffix = path.suffix.lower()
    if suffix == ".vue":
        has_comment = bool(re.search(r"<!--[\s\S]*?[\u4e00-\u9fff][\s\S]*?-->", header))
    elif suffix in {".js", ".sh"}:
        has_comment = bool(
            re.search(r"(?:/\*[\s\S]*?[\u4e00-\u9fff][\s\S]*?\*/|^\s*(?://|#).*?[\u4e00-\u9fff])", header, re.MULTILINE)
        )
    else:
        has_comment = bool(re.search(r"^\s*(?:::|REM\b).*?[\u4e00-\u9fff]", header, re.IGNORECASE | re.MULTILINE))
    if has_comment:
        return []
    return [AuditIssue(path, 1, "文件开头缺少中文文件职责注释")]


def should_ignore(path: Path) -> bool:
    """判断路径是否属于测试、迁移、依赖、缓存或构建产物。"""
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return False
    return any(part in IGNORED_PARTS for part in relative.parts)


def iter_source_files(root: Path, suffixes: set[str]):
    """自顶向下遍历源码，并在进入依赖或产物目录前完成剪枝。"""
    if not root.exists():
        return
    for current_root, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(directory for directory in directories if directory not in IGNORED_PARTS)
        current_path = Path(current_root)
        for filename in sorted(filenames):
            path = current_path / filename
            if path.suffix.lower() in suffixes:
                yield path


def discover_source_files() -> list[Path]:
    """返回需要审计的后端、桌面客户端、前端和维护脚本生产源码。"""
    files: set[Path] = set()
    for root in (PROJECT_ROOT / "backend", PROJECT_ROOT / "windows-client", PROJECT_ROOT / "scripts"):
        files.update(iter_source_files(root, {".py"}))

    frontend_root = PROJECT_ROOT / "frontend" / "app" / "log-analyze" / "src"
    files.update(iter_source_files(frontend_root, {".js", ".vue"}))

    for pattern in ("backend/*.sh", "windows-client/*.sh", "windows-client/*.bat"):
        files.update(path for path in PROJECT_ROOT.glob(pattern) if not should_ignore(path))
    return sorted(files)


def run_audit(paths: list[Path] | None = None) -> list[AuditIssue]:
    """执行完整注释审计并返回按路径和行号排序的问题列表。"""
    issues: list[AuditIssue] = []
    for path in paths or discover_source_files():
        if path.suffix.lower() == ".py":
            issues.extend(audit_python_file(path))
        else:
            issues.extend(audit_text_file(path))
    return sorted(issues, key=lambda issue: (str(issue.path), issue.line, issue.message))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数，支持只审计指定文件以便增量维护。"""
    parser = argparse.ArgumentParser(description="检查生产源码中文维护注释")
    parser.add_argument("paths", nargs="*", type=Path, help="可选的源码文件路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """打印审计结果，并用退出码 1 表示仍存在注释缺口。"""
    args = parse_args(argv)
    selected = [path if path.is_absolute() else PROJECT_ROOT / path for path in args.paths]
    issues = run_audit(selected or None)
    if not issues:
        print("源码中文注释审计通过")
        return 0

    print(f"发现 {len(issues)} 项源码中文注释缺口：")
    for issue in issues:
        try:
            display_path = issue.path.resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            display_path = issue.path
        print(f"- {display_path}:{issue.line} {issue.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
