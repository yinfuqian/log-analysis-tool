#!/usr/bin/env python3
"""为缺少维护说明的生产源码机械补充中文模块、类、函数和文件职责注释。"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path


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


def _contains_chinese(value: str | None) -> bool:
    """判断现有文档字符串是否已经包含中文维护说明。"""
    return bool(value and CHINESE_PATTERN.search(value))


def _module_description(path: Path) -> str:
    """根据文件名生成不依赖业务实现细节的模块职责说明。"""
    label = path.stem.replace("_", " ")
    return f"{label} 模块负责本文件相关的业务流程、数据转换与依赖协作。"


def _class_description(name: str) -> str:
    """为类生成说明其封装职责的中文文档字符串。"""
    return f"{name} 类封装该领域对象的状态、依赖与相关行为。"


def _function_description(name: str) -> str:
    """根据函数命名动词生成可维护的中文职责说明。"""
    normalized = name.strip("_").lower()
    if name == "__init__":
        return "初始化当前对象的依赖、界面状态或运行参数。"
    if name == "__repr__":
        return "返回便于日志记录和调试查看的对象表示。"

    action_rules = (
        (("get", "read", "load", "fetch"), "读取并返回"),
        (("build", "make"), "构建并返回"),
        (("create",), "创建并返回"),
        (("normalize", "sanitize", "clean", "clamp"), "规范化并返回"),
        (("extract", "parse", "decode", "split"), "解析或提取并返回"),
        (("find", "search", "discover", "lookup", "guess", "infer"), "查找或推断并返回"),
        (("validate", "verify", "check", "ensure"), "校验"),
        (("update", "refresh", "sync"), "更新"),
        (("set", "apply"), "设置或应用"),
        (("handle", "on", "accept"), "处理"),
        (("is", "has", "should", "can"), "判断"),
        (("upload",), "上传"),
        (("analyze", "assess"), "执行故障分析并返回"),
        (("format", "render", "summarize", "annotate"), "格式化或整理并返回"),
        (("install", "setup"), "注册或配置"),
        (("cleanup", "remove", "delete", "clear"), "清理"),
        (("run", "execute", "main", "start", "stop"), "执行"),
        (("submit", "request"), "提交"),
        (("poll", "wait"), "轮询或等待"),
        (("cancel", "revoke"), "取消"),
        (("merge", "dedupe", "group"), "合并整理并返回"),
        (("resolve",), "解析并返回"),
        (("save", "write", "persist", "insert", "record"), "保存"),
    )
    for prefixes, action in action_rules:
        if any(normalized == prefix or normalized.startswith(prefix + "_") for prefix in prefixes):
            return f"{action} {name} 对应的业务数据，保持现有调用约定。"
    return f"处理 {name} 对应的业务步骤，并向调用方返回所需结果。"


def _module_insert_index(lines: list[str]) -> int:
    """计算模块文档字符串应插入的位置，并保留 shebang 与编码声明。"""
    index = 0
    if lines and lines[0].startswith("#!"):
        index = 1
    if index < len(lines) and "coding" in lines[index][:40]:
        index += 1
    return index


def _statement_start_lineno(node: ast.stmt) -> int:
    """返回语句包含装饰器在内的起始行号，避免把文档插入装饰器与定义之间。"""
    decorator_list = getattr(node, "decorator_list", None) or []
    if decorator_list:
        return min(decorator.lineno for decorator in decorator_list)
    return node.lineno


def transform_python_source(source: str, path: Path) -> str:
    """仅向缺少中文说明的 Python 语法节点插入文档字符串。"""
    tree = ast.parse(source, filename=str(path))
    newline = "\r\n" if "\r\n" in source else "\n"
    lines = source.splitlines()
    trailing_newline = source.endswith(("\n", "\r"))
    insertions: list[tuple[int, str]] = []

    if not _contains_chinese(ast.get_docstring(tree, clean=False)):
        insertions.append((_module_insert_index(lines), f'"""{_module_description(path)}"""'))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            description = _class_description(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            description = _function_description(node.name)
        else:
            continue
        if _contains_chinese(ast.get_docstring(node, clean=False)):
            continue
        if not node.body or node.body[0].lineno <= node.lineno:
            continue
        body = node.body[0]
        indentation = " " * body.col_offset
        insertions.append((_statement_start_lineno(body) - 1, f'{indentation}"""{description}"""'))

    for index, text in sorted(insertions, key=lambda item: item[0], reverse=True):
        lines.insert(index, text)
    transformed = newline.join(lines)
    if trailing_newline or transformed:
        transformed += newline
    return transformed


def transform_text_source(source: str, path: Path) -> str:
    """为 Vue、JavaScript、Shell 与 Batch 文件补充中文文件职责注释。"""
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
        return source

    label = path.stem.replace("_", " ")
    if suffix == ".vue":
        comment = f"<!-- {label} 页面组件负责界面展示、交互状态和后端数据联动。 -->"
    elif suffix == ".js":
        comment = f"/** {label} 模块负责前端数据访问、状态处理或页面配置。 */"
    elif suffix == ".bat":
        comment = f"REM {label} 脚本负责 Windows 客户端的启动或构建流程。"
    else:
        comment = f"# {label} 脚本负责后端或客户端的启动、构建与运行环境准备。"

    newline = "\r\n" if "\r\n" in source else "\n"
    if source.startswith("#!"):
        first_line, separator, remainder = source.partition(newline)
        return first_line + newline + comment + newline + remainder if separator else first_line + newline + comment + newline
    return comment + newline + source


def _iter_source_files(root: Path, suffixes: set[str]):
    """遍历指定目录，并在进入依赖或构建目录前完成剪枝。"""
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
    """发现需要机械补充注释的生产源码文件。"""
    files: set[Path] = set()
    for root in (PROJECT_ROOT / "backend", PROJECT_ROOT / "windows-client", PROJECT_ROOT / "scripts"):
        files.update(_iter_source_files(root, {".py"}))
    frontend_root = PROJECT_ROOT / "frontend" / "app" / "log-analyze" / "src"
    files.update(_iter_source_files(frontend_root, {".js", ".vue"}))
    for pattern in ("backend/*.sh", "windows-client/*.sh", "windows-client/*.bat"):
        files.update(PROJECT_ROOT.glob(pattern))
    return sorted(files)


def update_file(path: Path, dry_run: bool = False) -> bool:
    """补充单个文件的缺失说明，并返回文件内容是否发生变化。"""
    source = path.read_text(encoding="utf-8-sig")
    transformed = transform_python_source(source, path) if path.suffix.lower() == ".py" else transform_text_source(source, path)
    if transformed == source:
        return False
    if not dry_run:
        path.write_text(transformed, encoding="utf-8", newline="")
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析目标文件和只预览不写入的命令行选项。"""
    parser = argparse.ArgumentParser(description="机械补充生产源码中文维护说明")
    parser.add_argument("paths", nargs="*", type=Path, help="可选的源码文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅列出将修改的文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """执行批量补全并输出修改文件数量。"""
    args = parse_args(argv)
    paths = [path if path.is_absolute() else PROJECT_ROOT / path for path in args.paths] or discover_source_files()
    changed = []
    for path in paths:
        if update_file(path, dry_run=args.dry_run):
            changed.append(path)
            print(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    action = "将修改" if args.dry_run else "已修改"
    print(f"{action} {len(changed)} 个源码文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
