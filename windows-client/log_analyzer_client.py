"""log analyzer client 模块负责本文件相关的业务流程、数据转换与依赖协作。"""

import json
import html as html_lib
import os
import re
import sys
import threading
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import requests

try:
    from PIL import ImageGrab
except ImportError:  # pragma: no cover - optional during local tests
    ImageGrab = None

try:
    import windnd
except ImportError:  # pragma: no cover - optional during local tests
    windnd = None


CLIENT_DIR = Path(__file__).resolve().parent
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

try:
    from client_build_info import APP_RELEASE_DATE, APP_VERSION, DEFAULT_BACKEND_URL
except ImportError:  # pragma: no cover - keeps source runnable before first build metadata generation
    APP_VERSION = "v1.0.0"
    APP_RELEASE_DATE = "2026-06-24"
    DEFAULT_BACKEND_URL = os.getenv("WINDOWS_CLIENT_BACKEND_URL", "http://127.0.0.1:5000")

from api_client import ApiClient
from client_branding import CLIENT_WINDOW_TITLE, PRODUCT_NAME
from login_window import LoginWindow

APP_RELEASE_LABEL = f"{CLIENT_WINDOW_TITLE}/{APP_VERSION} fix on {APP_RELEASE_DATE}"
DRAG_DROP_ENABLED = windnd is not None
UNKNOWN_FILE_LABEL = "\u672a\u77e5\u6587\u4ef6"
NOTICE_CONFIG_FILENAME = "notice_config.json"
SUPPORTED_RELATED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
LANGUAGE_DISPLAY_NAMES = {
    "java": "Java",
    "python": "Python",
    "go": "Go",
    "golang": "Go",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "vue": "Vue",
    "xml": "XML",
    "yaml": "YAML",
    "json": "JSON",
    "properties": "Properties",
}


def _resource_path(filename):
    """处理 _resource_path 对应的业务步骤，并向调用方返回所需结果。"""
    if getattr(sys, "frozen", False):
        executable_path = Path(sys.executable).resolve().parent / filename
        if executable_path.exists():
            return executable_path
    bundled_root = Path(getattr(sys, "_MEIPASS", CLIENT_DIR))
    return bundled_root / filename


NOTICE_CONFIG_PATHS = [
    Path(sys.executable).resolve().parent / NOTICE_CONFIG_FILENAME if getattr(sys, "frozen", False) else CLIENT_DIR / NOTICE_CONFIG_FILENAME,
    _resource_path(NOTICE_CONFIG_FILENAME),
]


class OperationCancelled(Exception):
    """OperationCancelled 类封装该领域对象的状态、依赖与相关行为。"""
    """Raised when the user asks the client to stop the current operation."""


def format_exception_message(exc):
    """格式化或整理并返回 format_exception_message 对应的业务数据，保持现有调用约定。"""
    if isinstance(exc, requests.HTTPError):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        payload = None
        if response is not None:
            try:
                payload = response.json()
            except ValueError:
                payload = None

        details = []
        if isinstance(payload, dict):
            for key in ("error", "message", "detail"):
                value = payload.get(key)
                if value:
                    details.append(str(value))
            missing_fields = payload.get("missing_fields")
            if missing_fields:
                details.append("\u7f3a\u5c11\u5b57\u6bb5: " + "\u3001".join(str(item) for item in missing_fields))
        elif isinstance(payload, list):
            details.append(json.dumps(payload, ensure_ascii=False))

        if details:
            prefix = f"HTTP {status_code}: " if status_code else ""
            return prefix + "\uff1b".join(details)
        if status_code:
            return f"HTTP {status_code}: \u540e\u7aef\u8bf7\u6c42\u5931\u8d25\uff0c\u8bf7\u67e5\u770b\u670d\u52a1\u65e5\u5fd7"

    if isinstance(exc, requests.Timeout):
        return "\u8bf7\u6c42\u8d85\u65f6\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1\u662f\u5426\u7e41\u5fd9\u6216\u7f51\u7edc\u662f\u5426\u8fde\u901a"
    if isinstance(exc, requests.ConnectionError):
        return "\u65e0\u6cd5\u8fde\u63a5\u540e\u7aef\u670d\u52a1\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u5730\u5740\u3001\u7f51\u7edc\u6216\u670d\u52a1\u662f\u5426\u542f\u52a8"
    if isinstance(exc, requests.RequestException):
        text = str(exc).strip()
        return text or "\u7f51\u7edc\u8bf7\u6c42\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1\u6216\u7f51\u7edc"

    text = str(exc).strip()
    return text if text and text != "None" else "\u672a\u77e5\u9519\u8bef\uff0c\u8bf7\u67e5\u770b\u540e\u7aef\u65e5\u5fd7\u6216\u91cd\u8bd5"


MOJIBAKE_REPLACEMENTS = {
    "\u6d60\uff47\u721c\u95c2\ue1c0\ue57d": "\u4ee3\u7801\u95ee\u9898",
    "\u93c1\u7248\u5d41\u95c2\ue1c0\ue57d": "\u6570\u636e\u95ee\u9898",
    "\u95b0\u5d87\u7586\u95c2\ue1c0\ue57d": "\u914d\u7f6e\u95ee\u9898",
    "\u7f03\u6220\u7cb6\u95c2\ue1c0\ue57d": "\u7f51\u7edc\u95ee\u9898",
    "\u74a7\u52ec\u7c2e\u95c2\ue1c0\ue57d": "\u8d44\u6e90\u95ee\u9898",
    "\u93c8\ue046\u7161\u93c2\u56e6\u6b22": "\u672a\u77e5\u6587\u4ef6",
    "\u93c8\ue046\u7161": "\u672a\u77e5",
    "\u6d60\uff47\u721c\u7039\u6c2b\u7d85\u7f01\u64b9\ue191": "\u4ee3\u7801\u5b9a\u4f4d\u7ed3\u8bba",
    "\u9352\u55d8\u703d\u7f01\u64b4\u7049\u7487\ufe3d\u510f": "\u5206\u6790\u7ed3\u679c\u8be6\u60c5",
    "\u6fb6\u5d85\u57d7\u934f\u3129\u5134": "\u590d\u5236\u5168\u90e8",
    "\u934f\u62bd\u68f4": "\u5173\u95ed",
    "\u9429\ue1bc\u7d8d": "\u76ee\u5f55",
    "\u6d60\u72b1\ue1e7\u6fde\u719a\u6f7b\u5a11\u6a3a\ue0c6": "\u4efb\u52a1\u8fdb\u5ea6",
}


def repair_mojibake_text(value):
    """处理 repair_mojibake_text 对应的业务步骤，并向调用方返回所需结果。"""
    text = str(value)
    for bad_text, good_text in sorted(MOJIBAKE_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(bad_text, good_text)
    return text


DEFAULT_NOTICE_CONFIG = {
    "title": "{app_release_label}",
    "lines": [
        "\u4f7f\u7528\u65b9\u6cd5\uff1a1\uff09\u70b9\u51fb\u201c\u540c\u6b65 Git \u9879\u76ee\u201d\u5237\u65b0\u4ea7\u54c1/\u6a21\u5757/\u5206\u652f/Tag\uff1b2\uff09\u9009\u62e9\u4ea7\u54c1\u3001\u6a21\u5757\u3001\u4ee3\u7801\u5206\u652f\u6216 Tag\uff1b3\uff09\u4e0a\u4f20\u65e5\u5fd7\u6587\u4ef6\uff08.log/.txt/.gz\uff09\u6216\u7c98\u8d34/\u9009\u62e9\u56fe\u7247\uff1b4\uff09\u70b9\u51fb\u201c\u5f00\u59cb\u5206\u6790\u201d\u67e5\u770b\u7ed3\u8bba\u548c\u4ee3\u7801\u5b9a\u4f4d\u3002",
        "\u9002\u7528\u8303\u56f4\uff1a\u9002\u7528\u4e8e\u540e\u7aef Java \u670d\u52a1\u3001\u5e38\u89c1\u4e2d\u95f4\u4ef6\u8c03\u7528\u3001Git \u4ee3\u7801\u53ef\u8bbf\u95ee\u4e14\u65e5\u5fd7\u53ef\u5b9a\u4f4d\u7684\u6545\u969c\u6392\u67e5\u3002",
        "\u4f7f\u7528\u573a\u666f\uff1a\u652f\u6301\u65e5\u5fd7\u6587\u4ef6\u6392\u969c\u3001\u65e5\u5fd7\u622a\u56fe OCR \u5206\u6790\u3001\u4e1a\u52a1\u9875\u9762\u622a\u56fe\u7406\u89e3\uff1b\u9002\u5408\u590d\u76d8\u7ebf\u4e0a\u62a5\u9519\u3001\u5ba2\u8bc9/\u544a\u8b66\u5206\u6790\u3001\u5b9a\u4f4d\u4ee3\u7801/\u914d\u7f6e/\u7f51\u7edc/\u6570\u636e/\u4e0b\u6e38\u4f9d\u8d56\u7b49\u95ee\u9898\u3002",
        "\u540e\u7aef\u5730\u5740\uff1a{backend_url}",
        "\u6545\u969c\u8054\u7cfb\u4eba\uff1a\u5c39\u752b\u4e7e&\u5f20\u5c27",
        "\u9690\u79c1\u6027\u8bf4\u660e\uff1a\u8bf7\u4ec5\u4e0a\u4f20\u6392\u969c\u5fc5\u8981\u7684\u6700\u5c0f\u65e5\u5fd7\u7247\u6bb5\u6216\u622a\u56fe\uff0c\u4e0a\u4f20\u524d\u8bf7\u8131\u654f\u5ba2\u6237\u59d3\u540d\u3001\u624b\u673a\u53f7\u3001\u8bc1\u4ef6\u53f7\u3001Token\u3001\u5bc6\u94a5\u3001\u53e3\u4ee4\u3001\u8ba2\u5355\u91d1\u989d\u7b49\u654f\u611f\u6570\u636e\uff1b\u4e0d\u5efa\u8bae\u4e0a\u4f20\u5b8c\u6574\u751f\u4ea7\u65e5\u5fd7\u6216\u5305\u542b\u5ba2\u6237\u9690\u79c1\u7684\u4e1a\u52a1\u622a\u56fe\u3002",
    ],
}


def _notice_format_values():
    """处理 _notice_format_values 对应的业务步骤，并向调用方返回所需结果。"""
    return {
        "app_version": APP_VERSION,
        "app_release_date": APP_RELEASE_DATE,
        "app_release_label": APP_RELEASE_LABEL,
        "backend_url": DEFAULT_BACKEND_URL,
    }


def _format_notice_template(value):
    """格式化或整理并返回 _format_notice_template 对应的业务数据，保持现有调用约定。"""
    try:
        return str(value).format(**_notice_format_values())
    except (KeyError, ValueError):
        return str(value)


def load_notice_config():
    """读取并返回 load_notice_config 对应的业务数据，保持现有调用约定。"""
    for config_path in NOTICE_CONFIG_PATHS:
        try:
            if config_path and Path(config_path).exists():
                with Path(config_path).open("r", encoding="utf-8") as file_obj:
                    payload = json.load(file_obj)
                if isinstance(payload, dict):
                    return payload
        except (OSError, json.JSONDecodeError):
            continue
    return DEFAULT_NOTICE_CONFIG


def build_notice_title():
    """构建并返回 build_notice_title 对应的业务数据，保持现有调用约定。"""
    config = load_notice_config()
    return _format_notice_template(config.get("title") or DEFAULT_NOTICE_CONFIG["title"])


def build_notice_text():
    """构建并返回 build_notice_text 对应的业务数据，保持现有调用约定。"""
    config = load_notice_config()
    lines = config.get("lines")
    if isinstance(lines, str):
        return _format_notice_template(lines)
    if not isinstance(lines, list):
        lines = DEFAULT_NOTICE_CONFIG["lines"]
    return "\n".join(_format_notice_template(line) for line in lines if str(line).strip())


SMOOTH_PROGRESS_STAGE_LIMITS = {
    "clone_repo_started": 44,
    "clone_repo_done": 49,
    "read_image_started": 74,
    "read_image_done": 75,
    "read_log_started": 54,
    "read_log_done": 59,
    "analyze_log_started": 69,
    "analyze_log_done": 77,
    "extract_code_started": 84,
    "extract_code_done": 89,
    "analyze_code_started": 98,
    "analyze_code_done": 99,
}


def get_smooth_progress_limit(progress):
    """读取并返回 get_smooth_progress_limit 对应的业务数据，保持现有调用约定。"""
    percent = int(progress.get("percent", 0) or 0)
    stage = progress.get("stage")
    return max(percent, SMOOTH_PROGRESS_STAGE_LIMITS.get(stage, min(percent + 8, 98)))


def next_smooth_progress(current, target):
    """处理 next_smooth_progress 对应的业务步骤，并向调用方返回所需结果。"""
    current = int(current or 0)
    target = int(target or 0)
    if current >= target:
        return current
    return min(target, current + 1)


def format_progress_message_for_percent(message, percent):
    """格式化或整理并返回 format_progress_message_for_percent 对应的业务数据，保持现有调用约定。"""
    text = str(message or "")
    safe_percent = max(0, min(100, int(percent or 0)))
    if re.search(r"\d+%\s*$", text):
        return re.sub(r"\d+%\s*$", f"{safe_percent}%", text)
    return f"{text} {safe_percent}%".strip()


def format_result_payload(title, payload):
    """格式化或整理并返回 format_result_payload 对应的业务数据，保持现有调用约定。"""
    if isinstance(payload, dict):
        if _is_analysis_payload(payload):
            return _format_analysis_result(title, payload)
        if _is_upload_payload(payload):
            return _format_upload_result(title, payload)
        if _is_task_payload(payload):
            return _format_task_result(title, payload)
        return _format_key_value_result(title, payload)
    return f"\u3010{title}\u3011\n\n{_clean_markdown_text(payload)}\n\n"


def _is_analysis_payload(payload):
    """判断 _is_analysis_payload 对应的业务数据，保持现有调用约定。"""
    return any(key in payload for key in ("log_analysis", "code_analysis", "code_snippets"))


def _is_upload_payload(payload):
    """判断 _is_upload_payload 对应的业务数据，保持现有调用约定。"""
    return "file_path" in payload and any(
        key in payload
        for key in ("original_line_count", "filtered_line_count", "target_date", "source_type", "image_tag")
    )


def _is_task_payload(payload):
    """判断 _is_task_payload 对应的业务数据，保持现有调用约定。"""
    return "task_id" in payload and "status_url" in payload


def _format_analysis_result(title, payload):
    """格式化或整理并返回 _format_analysis_result 对应的业务数据，保持现有调用约定。"""
    lines = [f"\u3010{title}\u3011", ""]
    for section in build_analysis_sections(payload):
        lines.append(f"\u3010{section['title']}\u3011")
        if section["kind"] == "code_list":
            lines.append(_format_code_snippets(section["items"]))
        elif section["kind"] == "code_finding_list":
            lines.append(_format_code_findings(section["items"]))
        elif section["kind"] == "issue_list":
            lines.append(_format_issue_items(section["items"]))
        else:
            section_text = [section.get("content", "")]
            for child in section.get("children", []):
                section_text.extend([f"{'#' * child.get('level', 2)} {child['title']}", child.get("content", "")])
            lines.append("\n".join(item for item in section_text if item).strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n\n"


def _normalize_issue_items(payload):
    """规范化并返回 _normalize_issue_items 对应的业务数据，保持现有调用约定。"""
    conclusion = payload.get("issue_conclusion") or {}
    issues = _get_issue_list_alias(conclusion)
    if not issues:
        raw_analysis = _parse_json_object_text(payload.get("code_analysis"))
        issues = _get_issue_list_alias(raw_analysis, include_top_level=True)
    if not isinstance(issues, list):
        issues = []
    code_items = _normalize_code_findings(payload.get("code_findings")) or _normalize_code_snippets(payload.get("code_snippets"))
    normalized = []
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            continue
        item = dict(issue)
        item["index"] = item.get("index") or index
        item["title"] = _clean_issue_title(
            repair_mojibake_text(
                item.get("title")
                or item.get("issue_title")
                or item.get("conclusion_summary")
                or f"问题{index}"
            )
        )
        item["summary"] = repair_mojibake_text(item.get("summary") or item.get("conclusion_summary") or "")
        item["root_cause"] = repair_mojibake_text(item.get("root_cause") or "")
        item["solution"] = repair_mojibake_text(item.get("solution") or "")
        category = str(item.get("issue_category") or "unknown").strip()
        category_label = {
            "code_issue": "代码问题",
            "data_issue": "数据问题",
            "config_issue": "配置问题",
            "network_issue": "网络问题",
            "dependency_issue": "依赖问题",
            "resource_issue": "资源问题",
            "unknown": "未知",
        }.get(category, category)
        item["issue_category_label"] = repair_mojibake_text(
            item.get("issue_category_label") or category_label
        )
        item["evidence"] = [repair_mojibake_text(value) for value in _ensure_text_list(item.get("evidence"))]
        item["query_commands"] = _ensure_text_list(
            item.get("query_commands") or item.get("query_command") or item.get("query_commond")
        )
        item["fix_commands"] = _ensure_text_list(
            item.get("fix_commands") or item.get("fix_command") or item.get("fix_commond")
        )
        item["code_locations"] = _normalize_issue_code_locations(item.get("code_locations") or item.get("code_snippets"))
        item["code_items"] = _match_issue_code_items(item["code_locations"], code_items)
        normalized.append(item)
    evidence = payload.get("analysis_evidence") or {}
    grouped_errors = evidence.get("grouped_log_errors") or []
    if isinstance(grouped_errors, list) and grouped_errors:
        log_events = [
            {
                "index": index,
                "line": group.get("first_line"),
                "text": group.get("representative_text"),
                "occurrence_count": group.get("occurrence_count", 1),
                "languages": group.get("languages") or [],
            }
            for index, group in enumerate(grouped_errors, start=1)
            if isinstance(group, dict)
        ]
    else:
        log_events = evidence.get("log_error_events") or []
    if isinstance(log_events, list):
        event_texts = [
            repair_mojibake_text(event.get("text") or "")
            for event in log_events
            if isinstance(event, dict) and event.get("text")
        ]
        if (
            len(event_texts) > 1
            and len(normalized) == 1
            and not any(_is_log_event_covered_by_issue(text, normalized) for text in event_texts)
        ):
            normalized = []
        for event in log_events:
            if not isinstance(event, dict):
                continue
            event_text = repair_mojibake_text(event.get("text") or "")
            if not event_text or _is_log_event_covered_by_issue(event_text, normalized):
                continue
            event_index = event.get("index") or len(normalized) + 1
            line = event.get("line")
            title = _build_log_event_issue_title(event_text, event_index)
            summary = event_text.splitlines()[0][:180]
            if line:
                summary = f"line {line}: {summary}"
            normalized.append({
                "index": len(normalized) + 1,
                "title": title,
                "summary": summary,
                "root_cause": "AI 未单独展开该日志错误事件，需要结合这段异常上下文继续确认根因。",
                "solution": "按该错误事件中的异常类型、文件行号和请求链路补充排查；如已选择相关代码分支，需结合对应代码片段复核。",
                "issue_category_label": "日志错误事件",
                "evidence": [event_text],
                "query_commands": [],
                "fix_commands": [],
                "code_locations": _extract_code_locations_from_log_event(event_text),
                "code_items": [],
                "occurrence_count": int(event.get("occurrence_count") or 1),
                "language": next(iter(event.get("languages") or []), "unknown"),
            })
    return normalized


def _clean_issue_title(value):
    """规范化并返回 _clean_issue_title 对应的业务数据，保持现有调用约定。"""
    title = str(value or "").strip()
    cleaned = re.sub(r"^问题\s*\d+\s*[:：、.\-]\s*", "", title, count=1)
    return cleaned or title


def _is_log_event_covered_by_issue(event_text, issue_items):
    """判断 _is_log_event_covered_by_issue 对应的业务数据，保持现有调用约定。"""
    event_text_lower = str(event_text or "").lower()
    issue_blob_parts = []
    for item in issue_items or []:
        for key in ("title", "summary", "root_cause", "solution", "issue_category_label"):
            issue_blob_parts.append(str(item.get(key) or ""))
        issue_blob_parts.extend(str(value) for value in item.get("evidence") or [])
        for location in item.get("code_locations") or []:
            file_path = str(location.get("file") or "")
            line = location.get("line")
            issue_blob_parts.append(file_path)
            if file_path and line is not None:
                issue_blob_parts.append(f"{file_path}:{line}")
                issue_blob_parts.append(f"{os.path.basename(file_path)}:{line}")
    issue_blob = "\n".join(issue_blob_parts).lower()
    if not issue_blob:
        return False
    markers = set(re.findall(r"[A-Za-z_][\w.$]*(?:Exception|Error)", event_text))
    markers.update(re.findall(r"[A-Za-z0-9_.$-]+\.java:\d+", event_text))
    markers.update(re.findall(r"\b(?:ERROR|FATAL)\b.*", event_text)[:1])
    return any(marker.lower() in issue_blob for marker in markers if marker)


def _build_log_event_issue_title(event_text, index):
    """构建并返回 _build_log_event_issue_title 对应的业务数据，保持现有调用约定。"""
    exception_match = re.search(r"([A-Za-z_][\w.$]*(?:Exception|Error))", event_text or "")
    if exception_match:
        return f"日志错误事件{index}: {exception_match.group(1).split('.')[-1]}"
    first_line = str(event_text or "").splitlines()[0] if event_text else ""
    if "ERROR" in first_line:
        return f"日志错误事件{index}: ERROR"
    return f"日志错误事件{index}"


def _extract_java_code_locations_from_log_event(event_text):
    """解析或提取并返回 _extract_java_code_locations_from_log_event 对应的业务数据，保持现有调用约定。"""
    locations = []
    for match in re.finditer(r"([A-Za-z0-9_.$-]+\.java):(\d+)", event_text or ""):
        locations.append({
            "file": match.group(1),
            "line": int(match.group(2)),
            "reason": "日志堆栈定位到该代码行。",
        })
        if len(locations) >= 5:
            break
    return locations


def _extract_code_locations_from_log_event(event_text):
    """解析或提取并返回 _extract_code_locations_from_log_event 对应的业务数据，保持现有调用约定。"""
    locations = []
    seen = set()
    patterns = [
        ("java", r"([A-Za-z0-9_.$/\\-]+\.(?:java|kt|groovy)):(\d+)"),
        ("python", r'File\s+"([^"]+\.py)",\s+line\s+(\d+)'),
        ("go", r"(?m)^\s*([^\s]+\.go):(\d+)(?:\s+\+0x[0-9a-fA-F]+)?"),
        ("shell", r"([^\s:]+\.(?:sh|bash|zsh))(?::\s*line\s+|:)(\d+)"),
    ]
    for language, pattern in patterns:
        for match in re.finditer(pattern, event_text or ""):
            file_path = os.path.basename(match.group(1).replace("\\", "/"))
            line = int(match.group(2))
            key = (file_path, line, language)
            if key in seen:
                continue
            seen.add(key)
            locations.append({
                "file": file_path,
                "line": line,
                "language": language,
                "reason": "\u65e5\u5fd7\u5806\u6808\u5b9a\u4f4d\u5230\u8be5\u4ee3\u7801\u884c\u3002",
            })
            if len(locations) >= 12:
                return locations
    return locations


def _ensure_text_list(value):
    """校验 _ensure_text_list 对应的业务数据，保持现有调用约定。"""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _parse_json_object_text(value):
    """解析或提取并返回 _parse_json_object_text 对应的业务数据，保持现有调用约定。"""
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _get_issue_list_alias(payload, include_top_level=False):
    """读取并返回 _get_issue_list_alias 对应的业务数据，保持现有调用约定。"""
    if not isinstance(payload, dict):
        return []
    value = (
        payload.get("issues")
        or payload.get("issue_details")
        or payload.get("problem_details")
        or payload.get("problems")
    )
    if isinstance(value, list):
        return value
    if include_top_level and any(
        payload.get(key)
        for key in (
            "conclusion_summary", "summary", "root_cause", "solution", "evidence",
            "query_commands", "query_command", "query_commond",
            "fix_commands", "fix_command", "fix_commond",
        )
    ):
        return [payload]
    return []


def _normalize_issue_code_locations(value):
    """规范化并返回 _normalize_issue_code_locations 对应的业务数据，保持现有调用约定。"""
    if not isinstance(value, list):
        return []
    locations = []
    for item in value:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file") or item.get("file_path") or "").strip()
        line = item.get("line")
        try:
            line = int(line) if line not in (None, "") else None
        except (TypeError, ValueError):
            line = None
        if file_path or line is not None:
            locations.append({
                "file": file_path,
                "line": line,
                "reason": repair_mojibake_text(item.get("reason") or ""),
            })
    return locations


def _match_issue_code_items(locations, code_items):
    """处理 _match_issue_code_items 对应的业务步骤，并向调用方返回所需结果。"""
    if not locations:
        return []
    matched = []
    for location in locations:
        location_file = str(location.get("file") or "")
        location_line = location.get("line")
        for code_item in code_items or []:
            code_file = str(code_item.get("file") or "")
            code_line = code_item.get("line")
            same_file = location_file and (
                code_file == location_file
                or code_file.endswith(location_file)
                or location_file.endswith(code_file)
                or os.path.basename(code_file) == os.path.basename(location_file)
            )
            same_line = location_line is None or str(code_line) == str(location_line)
            if same_file and same_line and code_item not in matched:
                matched.append(code_item)
    return matched


def build_analysis_sections(payload):
    """构建并返回 build_analysis_sections 对应的业务数据，保持现有调用约定。"""
    evidence = payload.get("analysis_evidence") or {}
    sections = []

    conclusion = payload.get("issue_conclusion") or {}
    if conclusion:
        confidence = conclusion.get("confidence")
        try:
            confidence_text = f"{float(confidence) * 100:.0f}%"
        except (TypeError, ValueError):
            confidence_text = "0%"
        hit_cache = "\u662f" if payload.get("knowledge_hit") else "\u5426"
        category_label = repair_mojibake_text(
            conclusion.get("issue_category_label") or conclusion.get("issue_category") or "\u672a\u77e5"
        )
        conclusion_lines = [
            f"\u95ee\u9898\u5206\u7c7b: {category_label}",
            f"\u7f6e\u4fe1\u5ea6: {confidence_text}",
            f"\u662f\u5426\u547d\u4e2d\u77e5\u8bc6\u5e93: {hit_cache}",
        ]
        if payload.get("knowledge_hit_count") is not None:
            conclusion_lines.append(f"\u5386\u53f2\u547d\u4e2d\u6b21\u6570: {payload.get('knowledge_hit_count')}")
        if conclusion.get("conclusion_summary"):
            conclusion_lines.append(f"\u4e00\u53e5\u8bdd\u7ed3\u8bba: {conclusion.get('conclusion_summary')}")
        if conclusion.get("root_cause"):
            conclusion_lines.append(f"\u6839\u56e0: {conclusion.get('root_cause')}")
        if conclusion.get("solution"):
            conclusion_lines.append(f"\u5efa\u8bae: {conclusion.get('solution')}")
        evidence_items = conclusion.get("evidence") or []
        if evidence_items:
            conclusion_lines.append("\u5224\u65ad\u4f9d\u636e: " + "\u3001".join(str(item) for item in evidence_items[:5]))
        sections.append({
            "title": "\u7ed3\u8bba",
            "kind": "text",
            "content": "\n".join(f"- {line}" for line in conclusion_lines),
        })

    issue_items = _normalize_issue_items(payload)
    if issue_items:
        sections.append({
            "title": "问题明细",
            "kind": "issue_list",
            "items": issue_items,
        })

    if evidence:
        if evidence.get("used_related_code_context"):
            used_code = "是（包含上下游代码）"
        else:
            used_code = "是（仅主模块代码）" if evidence.get("used_code_context") else "否"
        evidence_lines = [
            f"\u662f\u5426\u7ed3\u5408\u4ee3\u7801: {used_code}",
            f"识别到的日志问题: {evidence.get('log_error_event_count', conclusion.get('issue_count', 0))}",
            f"\u8bc6\u522b\u5230\u7684\u9519\u8bef\u6808: {evidence.get('error_info_count', 0)}",
            f"\u5b9a\u4f4d\u5230\u7684\u4ee3\u7801\u6587\u4ef6: {evidence.get('resolved_file_count', 0)}",
            f"\u4ee3\u7801\u7247\u6bb5\u6570\u91cf: {evidence.get('code_snippet_count', 0)}",
        ]
        snippet_files = evidence.get("code_snippet_files") or []
        code_context_modules = evidence.get("code_context_modules") or []
        if code_context_modules:
            evidence_lines.append(
                "实际参与分析的代码模块: "
                + "、".join(
                    f"{item.get('role')} {item.get('moduleName')} ({item.get('snippetCount', 0)} 个片段)"
                    for item in code_context_modules
                )
            )
        if snippet_files:
            evidence_lines.append("\u4ee3\u7801\u7247\u6bb5\u6587\u4ef6: " + "\u3001".join(str(item) for item in snippet_files[:8]))
        else:
            evidence_lines.append("\u63d0\u9192: \u672a\u5b9a\u4f4d\u5230\u4ee3\u7801\u7247\u6bb5\uff0c\u672c\u6b21\u7ed3\u8bba\u4e3b\u8981\u6765\u81ea\u65e5\u5fd7\u5185\u5bb9")
        sections.append({
            "title": "\u5206\u6790\u4f9d\u636e",
            "kind": "text",
            "content": "\n".join(f"- {line}" for line in evidence_lines),
        })

    image_analysis = payload.get("image_analysis") or {}
    if image_analysis:
        image_lines = []
        if image_analysis.get("image_tag"):
            image_lines.append(f"\u56fe\u7247\u6807\u7b7e: {image_analysis.get('image_tag')}")
        if image_analysis.get("image_description"):
            image_lines.append(f"\u56fe\u7247\u63cf\u8ff0: {image_analysis.get('image_description')}")
        for label, key in [
            ("\u4e1a\u52a1\u573a\u666f", "scene_summary"),
            ("\u4e1a\u52a1\u57df", "business_domain"),
            ("\u9875\u9762\u540d\u79f0", "page_name"),
            ("\u7528\u6237\u52a8\u4f5c", "user_action"),
            ("\u9875\u9762\u62a5\u9519", "error_message"),
        ]:
            if image_analysis.get(key):
                image_lines.append(f"{label}: {image_analysis.get(key)}")
        if image_analysis.get("summary"):
            image_lines.append(f"\u56fe\u7247\u6458\u8981: {image_analysis.get('summary')}")
        if image_analysis.get("extracted_text"):
            image_lines.append(f"\u8bc6\u522b\u6587\u672c: {image_analysis.get('extracted_text')}")
        if image_analysis.get("candidate_apis"):
            image_lines.append("\u5019\u9009\u63a5\u53e3: " + "\u3001".join(str(item) for item in image_analysis.get("candidate_apis", [])[:10]))
        if image_analysis.get("candidate_code_keywords"):
            image_lines.append("\u5019\u9009\u4ee3\u7801\u5173\u952e\u8bcd: " + "\u3001".join(str(item) for item in image_analysis.get("candidate_code_keywords", [])[:10]))
        if image_analysis.get("keywords"):
            image_lines.append("\u5173\u952e\u8bcd: " + "\u3001".join(str(item) for item in image_analysis.get("keywords", [])[:10]))
        missing_context = image_analysis.get("missing_context") or []
        if missing_context:
            image_lines.append("\u9700\u8981\u8865\u5145\u7684\u4e0a\u4e0b\u6e38\u4fe1\u606f:")
            for item in missing_context:
                if not isinstance(item, dict):
                    continue
                missing_title = item.get("title") or "\u4fe1\u606f\u7f3a\u53e3"
                image_lines.append(f"{item.get('direction', 'unknown')} - {missing_title}")
                if item.get("reason"):
                    image_lines.append(f"\u539f\u56e0: {item.get('reason')}")
                if item.get("needed"):
                    image_lines.append("\u9700\u8981: " + "\u3001".join(str(value) for value in item.get("needed", [])))
                if item.get("how_to_get"):
                    image_lines.append("\u83b7\u53d6\u65b9\u5f0f: " + "\u3001".join(str(value) for value in item.get("how_to_get", [])))
        if image_lines:
            sections.append({
                "title": "\u56fe\u7247/\u4e1a\u52a1\u8bc6\u522b\u6458\u8981",
                "kind": "text",
                "content": "\n".join(f"- {line}" for line in image_lines),
            })

    code_findings = _normalize_code_findings(payload.get("code_findings"))
    if code_findings:
        sections.append({
            "title": "\u4ee3\u7801\u5b9a\u4f4d\u7ed3\u8bba",
            "kind": "code_finding_list",
            "items": code_findings,
        })

    code_section = _build_text_analysis_section("\u95ee\u9898\u7ed3\u8bba", payload.get("code_analysis"))
    if code_section:
        sections.append(code_section)

    log_section = _build_text_analysis_section("\u65e5\u5fd7\u5206\u6790", payload.get("log_analysis"))
    if log_section:
        sections.append(log_section)

    code_items = _normalize_code_snippets(payload.get("code_snippets"))
    if code_items:
        sections.append({
            "title": "\u76f8\u5173\u4ee3\u7801\u7247\u6bb5",
            "kind": "code_list",
            "items": code_items,
        })

    task_lines = []
    if payload.get("task_id"):
        task_lines.append(f"task_id: {payload.get('task_id')}")
    if payload.get("repo_path"):
        task_lines.append(f"\u4ee3\u7801\u76ee\u5f55: {payload.get('repo_path')}")
    if task_lines:
        sections.append({
            "title": "\u4efb\u52a1\u4fe1\u606f",
            "kind": "text",
            "content": "\n".join(f"- {line}" for line in task_lines),
        })

    if not sections:
        sections.append({
            "title": "\u5206\u6790\u7ed3\u679c",
            "kind": "text",
            "content": _clean_markdown_text(payload),
        })
    return sections


_RAW_BUILD_ANALYSIS_SECTIONS = build_analysis_sections


def build_analysis_sections(payload):
    """构建并返回 build_analysis_sections 对应的业务数据，保持现有调用约定。"""
    sections = _RAW_BUILD_ANALYSIS_SECTIONS(payload)
    repaired_sections = []
    for section in sections:
        updated = dict(section)
        title = repair_mojibake_text(updated.get("title", ""))
        title = {
            "\u56fe\u7247\u8bc6\u522b\u6458\u8981": "\u56fe\u7247\u8bc6\u522b\u6458\u8981",
        }.get(title, title)
        updated["title"] = title
        if updated.get("kind") == "text":
            updated["content"] = repair_mojibake_text(updated.get("content", ""))
        repaired_sections.append(updated)

    conclusion = payload.get("issue_conclusion") or {}
    issue_section = next(
        (section for section in repaired_sections if section.get("kind") == "issue_list"),
        None,
    )
    if issue_section:
        issue_section["title"] = "\u95ee\u9898\u660e\u7ec6"
        issue_section["overview"] = repair_mojibake_text(
            conclusion.get("conclusion_summary") or conclusion.get("summary") or ""
        )
        filtered_sections = []
        for section in repaired_sections:
            if section is not issue_section and section.get("title") == "\u95ee\u9898\u7ed3\u8bba":
                content = str(section.get("content") or "").strip()
                parsed_content = _parse_json_object_text(content)
                if isinstance(parsed_content, dict) and any(
                    key in parsed_content
                    for key in ("issues", "issue_details", "problem_details", "problems", "issue_category")
                ):
                    continue
            filtered_sections.append(section)
        repaired_sections = filtered_sections

    insertion_index = next(
        (index + 1 for index, section in enumerate(repaired_sections) if section.get("kind") == "code_finding_list"),
        2 if len(repaired_sections) >= 2 else len(repaired_sections),
    )

    query_commands = [str(item).strip() for item in (conclusion.get("query_commands") or []) if str(item).strip()]
    if query_commands and not issue_section:
        repaired_sections.insert(
            insertion_index,
            {
                "title": "\u6392\u67e5\u547d\u4ee4",
                "kind": "text",
                "content": "\n".join(f"{index}. `{command}`" for index, command in enumerate(query_commands, start=1)),
            },
        )
        insertion_index += 1

    fix_commands = [str(item).strip() for item in (conclusion.get("fix_commands") or []) if str(item).strip()]
    if fix_commands and not issue_section:
        repaired_sections.insert(
            insertion_index,
            {
                "title": "\u4fee\u590d\u547d\u4ee4",
                "kind": "text",
                "content": "\n".join(f"{index}. `{command}`" for index, command in enumerate(fix_commands, start=1)),
            },
        )

    return repaired_sections


def build_analysis_summary(payload):
    """构建并返回 build_analysis_summary 对应的业务数据，保持现有调用约定。"""
    evidence = payload.get("analysis_evidence") or {}
    conclusion = payload.get("issue_conclusion") or {}
    if evidence.get("used_related_code_context"):
        used_code = "是（包含上下游代码）"
    else:
        used_code = "是（仅主模块代码）" if evidence.get("used_code_context") else "否"
    hit_cache = "\u662f" if payload.get("knowledge_hit") else "\u5426"
    issue_count = _get_distinct_issue_count(evidence, conclusion)
    category_label = repair_mojibake_text(
        conclusion.get("issue_category_label") or conclusion.get("issue_category") or "\u672a\u77e5"
    )
    lines = [
        "\u5206\u6790\u5b8c\u6210\uff0c\u8be6\u60c5\u5df2\u5728\u5f39\u7a97\u4e2d\u6253\u5f00\u3002",
        f"- \u95ee\u9898\u5206\u7c7b: {category_label}",
        f"- \u662f\u5426\u547d\u4e2d\u77e5\u8bc6\u5e93: {hit_cache}",
        f"- \u662f\u5426\u7ed3\u5408\u4ee3\u7801: {used_code}",
        f"- 识别到的日志问题: {issue_count}",
        f"- \u8bc6\u522b\u5230\u7684\u9519\u8bef\u6808: {evidence.get('error_info_count', 0)}",
        f"- \u5b9a\u4f4d\u5230\u7684\u4ee3\u7801\u6587\u4ef6: {evidence.get('resolved_file_count', 0)}",
        f"- \u4ee3\u7801\u7247\u6bb5\u6570\u91cf: {evidence.get('code_snippet_count', 0)}",
    ]
    if payload.get("task_id"):
        lines.append(f"- task_id: {payload.get('task_id')}")
    return "\n".join(lines) + "\n\n"


def _get_distinct_issue_count(evidence, conclusion):
    """读取并返回 _get_distinct_issue_count 对应的业务数据，保持现有调用约定。"""
    return (
        evidence.get("grouped_issue_count")
        or conclusion.get("issue_count")
        or len(conclusion.get("issues") or [])
        or evidence.get("log_error_event_count")
        or evidence.get("error_info_count", 0)
    )


def _build_text_analysis_section(title, value):
    """构建并返回 _build_text_analysis_section 对应的业务数据，保持现有调用约定。"""
    parsed = _parse_markdown_sections(value)
    if not parsed["content"] and not parsed["children"]:
        return None
    return {
        "title": title,
        "kind": "text",
        "content": parsed["content"],
        "children": parsed["children"],
    }


def _parse_markdown_sections(value):
    """解析或提取并返回 _parse_markdown_sections 对应的业务数据，保持现有调用约定。"""
    text = _clean_text(value)
    result = {"content": "", "children": []}
    if not text:
        return result

    main_lines = []
    current_child = None
    in_code_block = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        heading = _parse_markdown_heading(stripped) if not in_code_block else None
        if heading:
            current_child = {
                "title": heading["title"],
                "level": heading["level"],
                "content_lines": [],
            }
            result["children"].append(current_child)
            continue

        if current_child is not None:
            current_child["content_lines"].append(line)
        else:
            main_lines.append(line)

    result["content"] = "\n".join(main_lines).strip()
    for child in result["children"]:
        child["content"] = "\n".join(child.pop("content_lines")).strip()
    return result


def _parse_markdown_heading(stripped):
    """解析或提取并返回 _parse_markdown_heading 对应的业务数据，保持现有调用约定。"""
    if not stripped.startswith("#"):
        return None
    level = len(stripped) - len(stripped.lstrip("#"))
    if level < 1 or level > 6:
        return None
    title = stripped[level:].strip()
    if not title:
        return None
    return {"title": title, "level": level}


def _format_upload_result(title, payload):
    """格式化或整理并返回 _format_upload_result 对应的业务数据，保持现有调用约定。"""
    lines = [f"\u3010{title}\u3011", ""]
    message = _clean_text(payload.get("message"))
    if message:
        lines.append(f"- \u72b6\u6001: {message}")
    if payload.get("file_path"):
        lines.append(f"- \u5904\u7406\u540e\u6587\u4ef6: {payload.get('file_path')}")
    if payload.get("target_date"):
        lines.append(f"- \u76ee\u6807\u65e5\u671f: {payload.get('target_date')}")
    if "date_filter_applied" in payload:
        applied = "\u662f" if payload.get("date_filter_applied") else "\u5426"
        lines.append(f"- \u662f\u5426\u6309\u65e5\u671f\u8fc7\u6ee4: {applied}")
    if payload.get("original_line_count") is not None:
        lines.append(f"- \u539f\u59cb\u884c\u6570: {payload.get('original_line_count')}")
    if payload.get("filtered_line_count") is not None:
        lines.append(f"- \u8fc7\u6ee4\u540e\u884c\u6570: {payload.get('filtered_line_count')}")
    if payload.get("matched_line_count") is not None:
        lines.append(f"- \u5339\u914d\u65f6\u95f4\u884c\u6570: {payload.get('matched_line_count')}")
    if payload.get("upload_count") is not None:
        lines.append(f"- \u4e0a\u4f20\u6b21\u6570: {payload.get('upload_count')}")
    if payload.get("warning"):
        lines.extend(["", "\u3010\u63d0\u9192\u3011", _clean_text(payload.get("warning"))])
    return "\n".join(lines).rstrip() + "\n\n"


def _format_task_result(title, payload):
    """格式化或整理并返回 _format_task_result 对应的业务数据，保持现有调用约定。"""
    lines = [f"\u3010{title}\u3011", ""]
    if payload.get("task_id"):
        lines.append(f"- task_id: {payload.get('task_id')}")
    if payload.get("state"):
        lines.append(f"- \u72b6\u6001: {payload.get('state')}")
    if payload.get("status_url"):
        lines.append(f"- \u67e5\u8be2\u5730\u5740: {payload.get('status_url')}")
    return "\n".join(lines).rstrip() + "\n\n"


def _format_key_value_result(title, payload):
    """格式化或整理并返回 _format_key_value_result 对应的业务数据，保持现有调用约定。"""
    lines = [f"\u3010{title}\u3011", ""]
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines).rstrip() + "\n\n"


def build_result_export_filename(payload):
    """构建并返回 build_result_export_filename 对应的业务数据，保持现有调用约定。"""
    task_id = ""
    if isinstance(payload, dict):
        task_id = str(payload.get("task_id") or "").strip()
    suffix = f"-{_safe_filename_part(task_id)}" if task_id else ""
    return f"log-analysis-result{suffix}.html"


def build_result_html_document(title, payload):
    """构建并返回 build_result_html_document 对应的业务数据，保持现有调用约定。"""
    safe_title = _html_escape(title or "\u5206\u6790\u7ed3\u679c")
    sections = build_analysis_sections(payload) if isinstance(payload, dict) else [
        {"title": title or "\u5206\u6790\u7ed3\u679c", "kind": "text", "content": _clean_markdown_text(payload)}
    ]
    rendered_sections = "\n".join(_render_html_section(section, index) for index, section in enumerate(sections, start=1))
    toc_items = "\n".join(
        _render_html_toc_item(section, index)
        for index, section in enumerate(sections, start=1)
    )
    summary = _build_html_report_summary(payload if isinstance(payload, dict) else {})
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202c;
      --muted: #697586;
      --line: #d9e1ea;
      --panel: #ffffff;
      --canvas: #f3f6f9;
      --soft: #f7f9fc;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --danger: #b42318;
      --code: #111827;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", Arial, sans-serif;
      line-height: 1.7;
    }}
    .report-shell {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 32px 28px 48px;
    }}
    .report-header {{
      background: #fff;
      border: 1px solid var(--line);
      border-top: 5px solid var(--accent);
      border-radius: 12px;
      padding: 28px 32px;
      box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 24px;
      align-items: start;
    }}
    .eyebrow {{
      color: var(--accent-strong);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }}
    h1, h2, h3 {{ letter-spacing: 0; }}
    h1 {{
      margin: 0 0 6px;
      font-size: 30px;
      line-height: 1.2;
    }}
    .report-subtitle {{
      color: var(--muted);
      margin: 10px 0 0;
      max-width: 760px;
    }}
    .meta-panel {{
      border-left: 1px solid var(--line);
      padding-left: 20px;
      color: var(--muted);
      font-size: 13px;
    }}
    .meta-panel strong {{
      display: block;
      color: var(--ink);
      font-size: 15px;
      margin-bottom: 4px;
    }}
    .executive-summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 18px 0 22px;
    }}
    .metric {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px 16px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .metric strong {{
      display: block;
      color: var(--ink);
      font-size: 18px;
      line-height: 1.35;
      word-break: break-word;
    }}
    .report-layout {{
      display: grid;
      grid-template-columns: 240px minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }}
    .report-toc {{
      position: sticky;
      top: 16px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 16px;
    }}
    .report-toc h2 {{
      margin: 0 0 10px;
      font-size: 14px;
      color: var(--ink);
    }}
    .report-toc a {{
      display: flex;
      gap: 8px;
      padding: 8px 0;
      color: #334155;
      text-decoration: none;
      border-top: 1px solid #edf1f5;
      font-size: 13px;
    }}
    .report-toc a:first-of-type {{ border-top: 0; }}
    .report-toc span {{
      color: var(--accent-strong);
      font-weight: 700;
      min-width: 28px;
    }}
    .issue-nav {{
      margin: 2px 0 10px 36px;
      padding-left: 12px;
      border-left: 2px solid #d7e8e5;
    }}
    .issue-nav a {{
      display: block;
      border: 0;
      padding: 6px 0;
      color: #526070;
      font-size: 12px;
      line-height: 1.45;
    }}
    .issue-nav a:hover {{ color: var(--accent-strong); }}
    .issue-detail-nav {{
      margin: 0 0 4px 12px;
      padding-left: 10px;
      border-left: 1px dashed #b8cbc8;
    }}
    .issue-detail-nav a {{
      padding: 3px 0;
      color: #718096;
      font-size: 11px;
    }}
    .analysis-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 22px 24px;
      margin-bottom: 16px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 20px;
      color: var(--ink);
    }}
    h3 {{
      margin: 18px 0 8px;
      font-size: 15px;
      color: var(--accent-strong);
    }}
    h4 {{
      margin: 14px 0 8px;
      font-size: 13px;
      color: #334155;
    }}
    p {{
      margin: 0 0 10px;
      white-space: pre-wrap;
    }}
    .section-text {{
      color: #263445;
      font-size: 14px;
    }}
    pre {{
      margin: 8px 0 16px;
      padding: 14px 16px;
      overflow-x: auto;
      background: var(--code);
      color: #e5edf5;
      border: 1px solid #0f172a;
      border-radius: 8px;
      font: 13px/1.6 Consolas, "SFMono-Regular", Menlo, monospace;
      white-space: pre;
    }}
    code {{ font-family: Consolas, "SFMono-Regular", Menlo, monospace; }}
    .reason {{
      color: var(--muted);
      font-size: 14px;
      background: var(--soft);
      border-left: 3px solid var(--accent);
      padding: 8px 10px;
      border-radius: 6px;
    }}
    .code-label {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--ink);
      font-weight: 700;
      margin-top: 12px;
    }}
    .code-label::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--accent);
    }}
    .issue-card {{
      border: 1px solid #dce4ec;
      border-radius: 10px;
      margin: 18px 0;
      background: #fff;
      overflow: hidden;
    }}
    .issue-card__header {{
      display: grid;
      grid-template-columns: 48px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
      padding: 18px 20px;
      background: #f7fafc;
      border-bottom: 1px solid #e3e9ef;
    }}
    .issue-number {{
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      border-radius: 8px;
      background: var(--accent);
      color: #fff;
      font-size: 16px;
      font-weight: 800;
    }}
    .issue-heading h3 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.4;
      color: #0f172a;
    }}
    .issue-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-top: 6px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border: 1px solid #cfd9e3;
      border-radius: 999px;
      color: #526070;
      background: #fff;
      font-size: 11px;
      font-weight: 700;
    }}
    .badge--confidence {{
      color: var(--accent-strong);
      border-color: #a9d4cd;
      background: #edf8f6;
    }}
    .issue-card__body {{ padding: 20px; }}
    .issue-summary {{
      margin: 0 0 16px;
      padding: 13px 15px;
      border-left: 4px solid var(--accent);
      border-radius: 0 7px 7px 0;
      background: #f2f8f7;
      color: #1f3440;
      font-size: 14px;
    }}
    .diagnostic-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .diagnostic-panel {{
      border: 1px solid #e1e7ee;
      border-radius: 8px;
      padding: 14px 15px;
      background: #fbfcfe;
    }}
    .diagnostic-panel h4 {{ margin-top: 0; }}
    .diagnostic-panel p {{ margin-bottom: 0; color: #334155; font-size: 14px; }}
    .issue-section {{
      padding-top: 14px;
      margin-top: 14px;
      border-top: 1px solid #e8edf2;
    }}
    .issue-section h4 {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 0;
      font-size: 14px;
      color: #17202c;
    }}
    .issue-section h4::before {{
      content: "";
      width: 4px;
      height: 14px;
      border-radius: 2px;
      background: var(--accent);
    }}
    .issue-card ul {{
      margin: 6px 0 0 20px;
      padding: 0;
      color: #263445;
      font-size: 14px;
    }}
    .issue-card li {{ margin: 6px 0; }}
    .command-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .command-panel {{
      min-width: 0;
      border: 1px solid #263344;
      border-radius: 8px;
      overflow: hidden;
      background: #111827;
    }}
    .command-panel__title {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 0;
      padding: 9px 12px;
      color: #d7e2ed;
      background: #1f2937;
      border-bottom: 1px solid #344154;
      font: 700 12px/1.4 "Microsoft YaHei UI", sans-serif;
    }}
    .command-panel__title span {{
      color: #8ea0b5;
      font-size: 10px;
      font-weight: 600;
    }}
    .command-list {{ margin: 0; padding: 8px 0; list-style: none; }}
    .command-list li {{
      display: grid;
      grid-template-columns: 22px minmax(0, 1fr);
      gap: 4px;
      margin: 0;
      padding: 6px 12px;
      color: #dbe7f3;
      font: 12px/1.65 Consolas, "SFMono-Regular", Menlo, monospace;
    }}
    .command-prompt {{ color: #5eead4; user-select: none; }}
    .command-list code {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
    .code-location-list {{
      display: grid;
      gap: 8px;
      margin-left: 0 !important;
      list-style: none;
    }}
    .code-location-list li {{
      padding: 9px 11px;
      border: 1px solid #e1e7ee;
      border-radius: 7px;
      background: #f8fafc;
    }}
    .code-location-list code {{ color: #0f5f58; font-weight: 700; }}
    @media (max-width: 960px) {{
      .report-header, .report-layout, .executive-summary {{
        grid-template-columns: 1fr;
      }}
      .diagnostic-grid, .command-grid {{ grid-template-columns: 1fr; }}
      .issue-card__header {{ grid-template-columns: 42px minmax(0, 1fr); }}
      .meta-panel {{
        border-left: 0;
        border-top: 1px solid var(--line);
        padding: 16px 0 0;
      }}
      .report-toc {{ position: static; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .report-shell {{ padding: 0; }}
      .report-toc {{ display: none; }}
      .report-layout {{ display: block; }}
      .analysis-card, .report-header, .metric {{ box-shadow: none; }}
    }}
  </style>
</head>
<body>
  <main class="report-shell">
    <header class="report-header">
      <div>
        <div class="eyebrow">Log Analysis Report</div>
      <h1>{safe_title}</h1>
        <p class="report-subtitle">本报告汇总日志错误、代码证据、上下游链路和处置建议，适合归档、复盘和研发协同排障。</p>
      </div>
      <div class="meta-panel">
        <strong>导出时间</strong>
        <div>{_html_escape(generated_at)}</div>
        <strong style="margin-top:14px;">任务编号</strong>
        <div>{_html_escape(summary.get('task_id') or '未提供')}</div>
      </div>
    </header>
    <section class="executive-summary" aria-label="报告摘要">
      <div class="metric"><span>问题分类</span><strong>{_html_escape(summary.get('category'))}</strong></div>
      <div class="metric"><span>代码上下文</span><strong>{_html_escape(summary.get('used_code'))}</strong></div>
      <div class="metric"><span>问题数量</span><strong>{_html_escape(summary.get('error_count'))}</strong></div>
      <div class="metric"><span>代码片段</span><strong>{_html_escape(summary.get('snippet_count'))}</strong></div>
    </section>
    <div class="report-layout">
      <nav class="report-toc" aria-label="报告目录">
        <h2>报告目录</h2>
        {toc_items}
      </nav>
      <article>
        {rendered_sections}
      </article>
    </div>
  </main>
</body>
</html>
"""


def _build_html_report_summary(payload):
    """构建并返回 _build_html_report_summary 对应的业务数据，保持现有调用约定。"""
    evidence = payload.get("analysis_evidence") or {}
    conclusion = payload.get("issue_conclusion") or {}
    category = repair_mojibake_text(conclusion.get("issue_category_label") or conclusion.get("issue_category") or "未知")
    if evidence.get("used_related_code_context"):
        used_code = "已结合上下游代码"
    else:
        used_code = "仅主模块代码" if evidence.get("used_code_context") else "仅日志/图片"
    issue_count = _get_distinct_issue_count(evidence, conclusion)
    return {
        "task_id": str(payload.get("task_id") or "").strip(),
        "category": category,
        "used_code": used_code,
        "error_count": str(issue_count),
        "snippet_count": str(evidence.get("code_snippet_count", len(payload.get("code_snippets") or []))),
    }


def _render_html_toc_item(section, index):
    """格式化或整理并返回 _render_html_toc_item 对应的业务数据，保持现有调用约定。"""
    anchor = _html_escape(_section_anchor(section, index))
    title = _html_escape(section.get("title") or "\u5206\u6790\u7ed3\u679c")
    parts = [f'<a href="#{anchor}"><span>{index:02d}</span>{title}</a>']
    if section.get("kind") == "issue_list":
        issue_links = []
        for item_index, issue in enumerate(section.get("items") or [], start=1):
            issue_number = issue.get("index") or item_index
            issue_title = issue.get("title") or f"\u95ee\u9898{issue_number}"
            issue_links.append(
                f'<a href="#issue-{_html_escape(issue_number)}">'
                f'\u95ee\u9898{_html_escape(issue_number)} \u00b7 {_html_escape(issue_title)}</a>'
            )
            detail_links = "".join(
                f'<a href="#issue-{_html_escape(issue_number)}-{_html_escape(slug)}">'
                f'{_html_escape(detail_title)}</a>'
                for slug, detail_title in _issue_detail_entries(issue)
            )
            if detail_links:
                issue_links.append(f'<div class="issue-detail-nav">{detail_links}</div>')
        if issue_links:
            parts.append('<div class="issue-nav">' + "".join(issue_links) + "</div>")
    return "".join(parts)


def _issue_detail_entries(issue):
    """处理 _issue_detail_entries 对应的业务步骤，并向调用方返回所需结果。"""
    entries = []
    for slug, title, value in (
        ("summary", "\u73b0\u8c61\u6458\u8981", issue.get("summary")),
        ("root-cause", "\u6839\u56e0\u5224\u65ad", issue.get("root_cause")),
        ("evidence", "\u5206\u6790\u4f9d\u636e", issue.get("evidence")),
        ("solution", "\u4fee\u590d\u5efa\u8bae", issue.get("solution")),
        ("query-commands", "\u6392\u67e5\u547d\u4ee4", issue.get("query_commands")),
        ("fix-commands", "\u4fee\u590d\u547d\u4ee4", issue.get("fix_commands")),
        ("code", "\u76f8\u5173\u4ee3\u7801", issue.get("code_items") or issue.get("code_locations")),
    ):
        if value:
            entries.append((slug, title))
    return entries


def _section_anchor(section, index):
    """处理 _section_anchor 对应的业务步骤，并向调用方返回所需结果。"""
    title = _safe_filename_part(section.get("title") or f"section-{index}") or f"section-{index}"
    return f"section-{index}-{title}"


def _render_html_section(section, index):
    """格式化或整理并返回 _render_html_section 对应的业务数据，保持现有调用约定。"""
    title = _html_escape(section.get("title") or "\u5206\u6790\u7ed3\u679c")
    anchor = _html_escape(_section_anchor(section, index))
    parts = [f"<section class=\"analysis-card\" id=\"{anchor}\">\n<h2>{title}</h2>"]
    kind = section.get("kind")
    if kind == "code_list":
        parts.extend(_render_html_code_items(section.get("items", []), "content"))
    elif kind == "code_finding_list":
        parts.extend(_render_html_code_items(section.get("items", []), "code", include_reason=True))
    elif kind == "issue_list":
        if section.get("overview"):
            parts.append(f'<p class="issue-summary">{_html_escape(section.get("overview"))}</p>')
        parts.extend(_render_html_issue_items(section.get("items", [])))
    else:
        if section.get("content"):
            parts.append(f"<p class=\"section-text\">{_html_escape(section.get('content'))}</p>")
        for child in section.get("children", []):
            parts.append(f"<h3>{_html_escape(child.get('title') or '')}</h3>")
            if child.get("content"):
                parts.append(f"<p class=\"section-text\">{_html_escape(child.get('content'))}</p>")
    parts.append("</section>")
    return "\n".join(parts)


def _render_html_issue_items_legacy(items):
    """格式化或整理并返回 _render_html_issue_items_legacy 对应的业务数据，保持现有调用约定。"""
    parts = []
    for item_index, issue in enumerate(items or [], start=1):
        issue_index = issue.get("index") or item_index
        title = issue.get("title") or f"问题{issue_index}"
        category = issue.get("issue_category_label") or "未分类"
        confidence = _format_confidence(issue.get("confidence"))
        parts.append(f'<article class="issue-card" id="issue-{_html_escape(issue_index)}">')
        parts.append('<header class="issue-card__header">')
        parts.append(f'<div class="issue-number">{_html_escape(issue_index)}</div>')
        parts.append('<div class="issue-heading">')
        parts.append(f'<h3>{_html_escape(title)}</h3>')
        parts.append('<div class="issue-meta">')
        parts.append(f'<span class="badge">{_html_escape(category)}</span>')
        if confidence:
            parts.append(f'<span class="badge badge--confidence">置信度 {confidence}</span>')
        occurrence_count = int(issue.get("occurrence_count") or 0)
        if occurrence_count > 1:
            parts.append(f'<span class="badge">出现 {occurrence_count} 次</span>')
        parts.append('</div></div></header>')
        parts.append('<div class="issue-card__body">')
        if issue.get("summary"):
            parts.append(f'<p class="issue-summary"><strong>现象摘要</strong><br>{_html_escape(issue.get("summary"))}</p>')
        root_cause = issue.get("root_cause")
        solution = issue.get("solution")
        if root_cause or solution:
            parts.append('<div class="diagnostic-grid">')
            if root_cause:
                parts.append(
                    '<section class="diagnostic-panel"><h4>根因判断</h4>'
                    f'<p>{_html_escape(root_cause)}</p></section>'
                )
            if solution:
                parts.append(
                    '<section class="diagnostic-panel"><h4>修复建议</h4>'
                    f'<p>{_html_escape(solution)}</p></section>'
                )
            parts.append('</div>')
        evidence = issue.get("evidence") or []
        if evidence:
            parts.append('<section class="issue-section"><h4>分析依据</h4>')
            parts.append("<ul>" + "".join(f"<li>{_html_escape(item)}</li>" for item in evidence) + "</ul>")
            parts.append('</section>')
        query_commands = issue.get("query_commands") or []
        fix_commands = issue.get("fix_commands") or []
        if query_commands or fix_commands:
            parts.append('<div class="command-grid">')
            if query_commands:
                parts.append(_render_html_command_panel("排查命令", query_commands, "query"))
            if fix_commands:
                parts.append(_render_html_command_panel("修复命令", fix_commands, "fix"))
            parts.append('</div>')
        code_items = issue.get("code_items") or []
        if code_items:
            parts.append('<section class="issue-section"><h4>相关代码片段</h4>')
            parts.extend(_render_html_code_items(code_items, "code" if "code" in code_items[0] else "content", include_reason=True))
            parts.append('</section>')
        elif issue.get("code_locations"):
            parts.append('<section class="issue-section"><h4>相关代码位置</h4>')
            parts.append("<ul class=\"code-location-list\">" + "".join(
                f"<li><code>{_html_escape(location.get('file') or UNKNOWN_FILE_LABEL)}"
                f"{':' + _html_escape(location.get('line')) if location.get('line') else ''}</code> "
                f" {_html_escape(location.get('reason') or '')}</li>"
                for location in issue.get("code_locations")
            ) + "</ul>")
            parts.append('</section>')
        parts.append("</div></article>")
    return parts


def _render_html_issue_items(items):
    """格式化或整理并返回 _render_html_issue_items 对应的业务数据，保持现有调用约定。"""
    parts = []
    for item_index, issue in enumerate(items or [], start=1):
        issue_index = issue.get("index") or item_index
        escaped_index = _html_escape(issue_index)
        title = issue.get("title") or f"\u95ee\u9898{issue_index}"
        category = issue.get("issue_category_label") or "\u672a\u5206\u7c7b"
        confidence = _format_confidence(issue.get("confidence"))
        try:
            issue_number_label = f"{int(issue_index):02d}"
        except (TypeError, ValueError):
            issue_number_label = str(issue_index)
        parts.append(f'<article class="issue-card" id="issue-{escaped_index}">')
        parts.append('<header class="issue-card__header">')
        parts.append(f'<div class="issue-number">{_html_escape(issue_number_label)}</div>')
        parts.append('<div class="issue-heading">')
        parts.append(f'<h3>\u95ee\u9898{escaped_index} \u00b7 {_html_escape(title)}</h3><div class="issue-meta">')
        parts.append(f'<span class="badge">{_html_escape(category)}</span>')
        if confidence:
            parts.append(f'<span class="badge badge--confidence">\u7f6e\u4fe1\u5ea6 {confidence}</span>')
        occurrence_count = int(issue.get("occurrence_count") or 0)
        if occurrence_count > 1:
            parts.append(f'<span class="badge">\u51fa\u73b0 {occurrence_count} \u6b21</span>')
        parts.append('</div></div></header><div class="issue-card__body">')
        if issue.get("summary"):
            parts.append(
                f'<section id="issue-{escaped_index}-summary" class="issue-section">'
                f'<h4>\u73b0\u8c61\u6458\u8981</h4><p>{_html_escape(issue.get("summary"))}</p></section>'
            )
        if issue.get("root_cause") or issue.get("solution"):
            parts.append('<div class="diagnostic-grid">')
        if issue.get("root_cause"):
            parts.append(
                f'<section id="issue-{escaped_index}-root-cause" class="diagnostic-panel">'
                f'<h4>\u6839\u56e0\u5224\u65ad</h4><p>{_html_escape(issue.get("root_cause"))}</p></section>'
            )
        evidence = issue.get("evidence") or []
        if evidence:
            parts.append(f'<section id="issue-{escaped_index}-evidence" class="issue-section"><h4>\u5206\u6790\u4f9d\u636e</h4>')
            parts.append("<ul>" + "".join(f"<li>{_html_escape(item)}</li>" for item in evidence) + "</ul></section>")
        if issue.get("solution"):
            parts.append(
                f'<section id="issue-{escaped_index}-solution" class="diagnostic-panel">'
                f'<h4>\u4fee\u590d\u5efa\u8bae</h4><p>{_html_escape(issue.get("solution"))}</p></section>'
            )
        if issue.get("root_cause") or issue.get("solution"):
            parts.append('</div>')
        query_commands = issue.get("query_commands") or []
        if query_commands:
            parts.append(f'<div id="issue-{escaped_index}-query-commands">{_render_html_command_panel("排查命令", query_commands, "query")}</div>')
        fix_commands = issue.get("fix_commands") or []
        if fix_commands:
            parts.append(f'<div id="issue-{escaped_index}-fix-commands">{_render_html_command_panel("修复命令", fix_commands, "fix")}</div>')
        code_items = issue.get("code_items") or []
        code_locations = issue.get("code_locations") or []
        if code_items or code_locations:
            parts.append(f'<section id="issue-{escaped_index}-code" class="issue-section"><h4>\u76f8\u5173\u4ee3\u7801</h4>')
            if code_items:
                parts.extend(_render_html_code_items(code_items, "code" if "code" in code_items[0] else "content", include_reason=True))
            else:
                parts.append("<ul class=\"code-location-list\">" + "".join(
                    f"<li><code>{_html_escape(location.get('file') or UNKNOWN_FILE_LABEL)}"
                    f"{':' + _html_escape(location.get('line')) if location.get('line') else ''}</code> "
                    f"{_html_escape(location.get('reason') or '')}</li>"
                    for location in code_locations
                ) + "</ul>")
            parts.append("</section>")
        parts.append("</div></article>")
    return parts


def _render_html_command_panel(title, commands, panel_type):
    """格式化或整理并返回 _render_html_command_panel 对应的业务数据，保持现有调用约定。"""
    command_items = "".join(
        '<li><span class="command-prompt">$</span>'
        f'<code>{_html_escape(command)}</code></li>'
        for command in commands or []
    )
    return (
        f'<section class="command-panel command-panel--{_html_escape(panel_type)}">'
        f'<h4 class="command-panel__title">{_html_escape(title)}'
        f'<span>{len(commands or [])} 条</span></h4>'
        f'<ol class="command-list">{command_items}</ol></section>'
    )


def _format_confidence(value):
    """格式化或整理并返回 _format_confidence 对应的业务数据，保持现有调用约定。"""
    if value in (None, ""):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _html_escape(value)
    if numeric <= 1:
        numeric *= 100
    return f"{numeric:.0f}%"


def _render_html_code_items(items, content_key, include_reason=False):
    """格式化或整理并返回 _render_html_code_items 对应的业务数据，保持现有调用约定。"""
    parts = []
    for index, item in enumerate(items or [], start=1):
        parts.append(f"<h3 class=\"code-label\">{_html_escape(_format_code_item_header(index, item))}</h3>")
        if include_reason and item.get("reason"):
            parts.append(f"<p class=\"reason\">\u5b9a\u4f4d\u539f\u56e0: {_html_escape(item.get('reason'))}</p>")
        parts.append(f"<pre><code>{_html_escape(item.get(content_key) or '')}</code></pre>")
    return parts


def _html_escape(value):
    """处理 _html_escape 对应的业务步骤，并向调用方返回所需结果。"""
    return html_lib.escape(_clean_text(value), quote=True)


def _safe_filename_part(value):
    """处理 _safe_filename_part 对应的业务步骤，并向调用方返回所需结果。"""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "").strip())
    return cleaned.strip(".-")[:80]


def _format_code_snippets(snippets):
    """格式化或整理并返回 _format_code_snippets 对应的业务数据，保持现有调用约定。"""
    blocks = []
    for index, snippet in enumerate(_normalize_code_snippets(snippets), start=1):
        header = _format_code_item_header(index, snippet)
        blocks.append(f"{header}\n{_indent_code(snippet['content'])}".rstrip())
    return "\n\n".join(blocks)


def _format_code_findings(findings):
    """格式化或整理并返回 _format_code_findings 对应的业务数据，保持现有调用约定。"""
    blocks = []
    for index, finding in enumerate(_normalize_code_findings(findings), start=1):
        header = _format_code_item_header(index, finding)
        reason = f"定位原因: {finding.get('reason')}\n" if finding.get("reason") else ""
        blocks.append(f"{header}\n{reason}{_indent_code(finding['code'])}".rstrip())
    return "\n\n".join(blocks)


def _format_issue_items(items):
    """格式化或整理并返回 _format_issue_items 对应的业务数据，保持现有调用约定。"""
    blocks = []
    for issue in items or []:
        issue_index = issue.get("index") or 1
        lines = [f"问题{issue_index}: {issue.get('title') or ''}".rstrip()]
        if issue.get("summary"):
            lines.append(f"现象摘要: {issue.get('summary')}")
        if issue.get("root_cause"):
            lines.append(f"根因判断: {issue.get('root_cause')}")
        if issue.get("evidence"):
            lines.append("分析依据:")
            lines.extend(f"- {item}" for item in issue.get("evidence"))
        if issue.get("solution"):
            lines.append(f"修复建议: {issue.get('solution')}")
        if issue.get("query_commands"):
            lines.append("排查命令:")
            lines.extend(f"{index}. {command}" for index, command in enumerate(issue.get("query_commands"), start=1))
        if issue.get("fix_commands"):
            lines.append("修复命令:")
            lines.extend(f"{index}. {command}" for index, command in enumerate(issue.get("fix_commands"), start=1))
        if issue.get("code_items"):
            lines.append("相关代码片段:")
            lines.append(_format_code_findings(issue.get("code_items")))
        elif issue.get("code_locations"):
            lines.append("相关代码位置:")
            for location in issue.get("code_locations"):
                suffix = f":{location.get('line')}" if location.get("line") else ""
                reason = f" - {location.get('reason')}" if location.get("reason") else ""
                lines.append(f"- {location.get('file') or UNKNOWN_FILE_LABEL}{suffix}{reason}")
        blocks.append("\n".join(line for line in lines if str(line).strip()))
    return "\n\n".join(blocks)


def _format_code_item_header(index, item):
    """格式化或整理并返回 _format_code_item_header 对应的业务数据，保持现有调用约定。"""
    module_name = item.get("module_name") or item.get("moduleName")
    module_prefix = f"[{module_name}] " if module_name else ""
    header = f"{index}. {module_prefix}{item.get('file') or UNKNOWN_FILE_LABEL}"
    if item.get("line"):
        header += f":{item['line']}"
    language = item.get("language")
    if language:
        header += f"  [{language}]"
    return header


def _normalize_code_snippets(snippets):
    """规范化并返回 _normalize_code_snippets 对应的业务数据，保持现有调用约定。"""
    if not snippets:
        return []
    if isinstance(snippets, str):
        return [{
            "file": "\u672a\u77e5\u6587\u4ef6",
            "line": None,
            "content": snippets.strip(),
            "language": "",
        }]

    items = []
    for snippet in snippets:
        if isinstance(snippet, dict):
            file_path = snippet.get("file") or snippet.get("file_path") or snippet.get("path") or "\u672a\u77e5\u6587\u4ef6"
            line = snippet.get("line") or snippet.get("line_number")
            content = snippet.get("snippet") or snippet.get("code") or snippet.get("content") or ""
            items.append({
                "file": str(file_path),
                "line": line,
                "content": _clean_text(content),
                "language": _format_language_label(_guess_code_language(file_path)),
                "module_name": snippet.get("module_name") or snippet.get("moduleName"),
                "module_role": snippet.get("module_role") or snippet.get("moduleRole"),
            })
        else:
            items.append({
                "file": "\u672a\u77e5\u6587\u4ef6",
                "line": None,
                "content": _clean_text(snippet),
                "language": "",
            })
    return items


def _normalize_code_findings(findings):
    """规范化并返回 _normalize_code_findings 对应的业务数据，保持现有调用约定。"""
    items = []
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        file_path = finding.get("file") or finding.get("file_path") or finding.get("path") or "\u672a\u77e5\u6587\u4ef6"
        code = finding.get("code") or finding.get("numbered_snippet") or finding.get("snippet") or ""
        items.append({
            "file": str(file_path),
            "line": finding.get("line") or finding.get("line_number"),
            "reason": _clean_text(finding.get("reason") or ""),
            "code": _clean_text(code),
            "language": _format_language_label(_guess_code_language(file_path)),
            "module_name": finding.get("module_name") or finding.get("moduleName"),
            "module_role": finding.get("module_role") or finding.get("moduleRole"),
        })
    return [item for item in items if item["code"]]


def _format_language_label(language):
    """格式化或整理并返回 _format_language_label 对应的业务数据，保持现有调用约定。"""
    normalized = str(language or "").strip().lower()
    if not normalized:
        return ""
    return LANGUAGE_DISPLAY_NAMES.get(normalized, normalized.upper() if len(normalized) <= 3 else normalized.title())


def build_related_module_selection_items(related_modules, modules, branch_versions=None):
    """构建并返回 build_related_module_selection_items 对应的业务数据，保持现有调用约定。"""
    branch_versions = branch_versions or {}
    by_id = {str(module.get("module_id")): module for module in modules or []}
    by_name = {str(module.get("module_name") or "").lower(): module for module in modules or []}
    items = []
    seen = set()
    for related in related_modules or []:
        module_id = str(related.get("moduleId") or related.get("module_id") or "")
        module_name = str(related.get("moduleName") or related.get("module_name") or "")
        module = by_id.get(module_id) or by_name.get(module_name.lower()) or {}
        module_branch_address, module_default_version = _module_branch_info(module)
        branch_address = module_branch_address or related.get("branchAddress") or related.get("branch_address") or ""
        default_version = module_default_version or related.get("tagVersion") or related.get("tag_version") or ""
        key = module_id or module_name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        versions = list(branch_versions.get(branch_address, []))
        if default_version and default_version not in versions:
            versions.insert(0, default_version)
        items.append({
            "moduleId": module_id or str(module.get("module_id") or ""),
            "moduleName": module_name or str(module.get("module_name") or ""),
            "role": related.get("role") or "related",
            "reason": related.get("reason") or "",
            "branchAddress": branch_address,
            "tagVersion": default_version,
            "versions": versions,
        })
    return items


def build_related_code_module_candidates(
    modules,
    primary_module_id="",
    branch_versions=None,
    suggested_modules=None,
    primary_branch_address="",
    primary_module_name="",
):
    """构建并返回 build_related_code_module_candidates 对应的业务数据，保持现有调用约定。"""
    branch_versions = branch_versions or {}
    suggested_modules = suggested_modules or []
    primary_branch_key = _normalize_branch_address(primary_branch_address)
    primary_name_key = _normalize_module_match_key(primary_module_name)
    suggested_by_id = {str(item.get("moduleId") or item.get("module_id") or ""): item for item in suggested_modules}
    suggested_by_alias = {}
    suggested_by_fuzzy_alias = {}
    for item in suggested_modules:
        for alias in _module_match_aliases(item):
            suggested_by_alias.setdefault(alias, item)
        for alias in _module_fuzzy_match_aliases(item, suggested=True):
            suggested_by_fuzzy_alias.setdefault(alias, item)
    candidates = []
    seen = set()
    matched_suggested_keys = set()
    for module in modules or []:
        module_id = str(module.get("module_id") or module.get("moduleId") or "")
        if module_id and module_id == str(primary_module_id or ""):
            continue
        module_name = str(module.get("module_name") or module.get("moduleName") or module.get("name") or "")
        branch_address, default_version = _module_branch_info(module)
        if primary_branch_key and _normalize_branch_address(branch_address) == primary_branch_key:
            continue
        if primary_name_key and _normalize_module_match_key(module_name) == primary_name_key:
            continue
        if not (module_id or module_name):
            continue
        key = _candidate_identity_key(module_id, module_name, branch_address)
        if key in seen:
            continue
        seen.add(key)
        suggested = suggested_by_id.get(module_id) or {}
        if not suggested:
            for alias in _module_match_aliases(module):
                suggested = suggested_by_alias.get(alias) or {}
                if suggested:
                    break
        if not suggested:
            for alias in _module_fuzzy_match_aliases(module):
                suggested = suggested_by_fuzzy_alias.get(alias) or {}
                if suggested:
                    break
        if suggested:
            matched_suggested_keys.add(_suggested_module_key(suggested))
        versions = list(branch_versions.get(branch_address, []))
        if default_version:
            versions = [default_version] + [version for version in versions if version != default_version]
        branch_values = [branch_address] if branch_address else []
        candidates.append({
            "moduleId": module_id,
            "moduleName": module_name,
            "matchedModuleName": suggested.get("moduleName") or suggested.get("module_name") or "",
            "role": suggested.get("role") or "related",
            "reason": suggested.get("reason") or "",
            "autoSelect": bool(suggested),
            "repositoryAvailable": bool(branch_address and default_version),
            "repositoryMessage": "" if branch_address and default_version else "模块在仓库配置中不存在或当前账号无权限，请补充仓库权限。",
            "branchAddress": branch_address,
            "branchOptions": branch_values,
            "tagVersion": default_version,
            "versions": versions,
        })
    for suggested in suggested_modules:
        module_id = str(suggested.get("moduleId") or suggested.get("module_id") or "")
        module_name = str(suggested.get("moduleName") or suggested.get("module_name") or "")
        if _suggested_module_key(suggested) in matched_suggested_keys:
            continue
        if _is_ignored_missing_module_name(module_name):
            continue
        key = module_id or module_name.lower()
        if module_id and module_id == str(primary_module_id or ""):
            continue
        if primary_name_key and _normalize_module_match_key(module_name) == primary_name_key:
            continue
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append({
            "moduleId": module_id,
            "moduleName": module_name,
            "role": suggested.get("role") or "related",
            "reason": suggested.get("reason") or "",
            "autoSelect": True,
            "repositoryAvailable": False,
            "repositoryMessage": "模块在当前产品仓库列表中不存在，请补充仓库权限或模块配置。",
            "branchAddress": "",
            "branchOptions": [],
            "tagVersion": "",
            "versions": [],
        })
    return candidates


def _candidate_identity_key(module_id, module_name, branch_address):
    """处理 _candidate_identity_key 对应的业务步骤，并向调用方返回所需结果。"""
    branch_key = _normalize_branch_address(branch_address)
    if branch_key:
        return f"branch:{branch_key}"
    if module_id:
        return f"id:{module_id}"
    return f"name:{_normalize_module_match_key(module_name)}"


def _module_branch_info(module):
    """处理 _module_branch_info 对应的业务步骤，并向调用方返回所需结果。"""
    module = module or {}
    branch = module.get("branch") or {}
    address = (
        branch.get("branch_address")
        or branch.get("branchAddress")
        or branch.get("address")
        or module.get("branch_address")
        or module.get("branchAddress")
        or module.get("address")
        or module.get("repo_url")
        or module.get("repoUrl")
        or module.get("git_url")
        or module.get("gitUrl")
        or ""
    )
    version = (
        branch.get("tag_version")
        or branch.get("tagVersion")
        or branch.get("version")
        or branch.get("default_branch")
        or branch.get("defaultBranch")
        or module.get("tag_version")
        or module.get("tagVersion")
        or module.get("version")
        or module.get("default_branch")
        or module.get("defaultBranch")
        or ""
    )
    return str(address or ""), str(version or "")


def _module_match_aliases(module):
    """处理 _module_match_aliases 对应的业务步骤，并向调用方返回所需结果。"""
    aliases = set()
    for value in [
        module.get("moduleName"),
        module.get("module_name"),
        module.get("name"),
        module.get("moduleId"),
        module.get("module_id"),
    ]:
        normalized = _normalize_module_match_key(value)
        if normalized:
            aliases.add(normalized)
    branch_address, _ = _module_branch_info(module)
    branch = module.get("branch") or {}
    for value in [
        module.get("branchAddress"),
        module.get("branch_address"),
        branch.get("branchAddress"),
        branch.get("branch_address"),
        branch_address,
    ]:
        slug = _repo_slug_from_branch_address(value)
        normalized_slug = _normalize_module_match_key(slug)
        if normalized_slug:
            aliases.add(normalized_slug)
    return aliases


def _module_fuzzy_match_aliases(module, suggested=False):
    """处理 _module_fuzzy_match_aliases 对应的业务步骤，并向调用方返回所需结果。"""
    aliases = set()
    names = [
        module.get("moduleName"),
        module.get("module_name"),
        module.get("name"),
    ]
    branch_address, _ = _module_branch_info(module)
    branch = module.get("branch") or {}
    repo_slugs = [
        _repo_slug_from_branch_address(module.get("branchAddress")),
        _repo_slug_from_branch_address(module.get("branch_address")),
        _repo_slug_from_branch_address(branch.get("branchAddress")),
        _repo_slug_from_branch_address(branch.get("branch_address")),
        _repo_slug_from_branch_address(branch_address),
    ]
    for value in [*names, *repo_slugs]:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if suggested and text.startswith("zhuiyi-"):
            stripped = text[len("zhuiyi-"):]
            normalized = _normalize_module_match_key(stripped)
            if normalized:
                aliases.add(normalized)
        if not suggested:
            first_segment = re.split(r"[-_]+", text)[0]
            if len(first_segment) >= 3:
                aliases.add(_normalize_module_match_key(first_segment))
    return aliases


def _repo_slug_from_branch_address(value):
    """处理 _repo_slug_from_branch_address 对应的业务步骤，并向调用方返回所需结果。"""
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    tail = re.split(r"[\\/]", text)[-1]
    return re.sub(r"\.git$", "", tail, flags=re.IGNORECASE)


def _normalize_module_match_key(value):
    """规范化并返回 _normalize_module_match_key 对应的业务数据，保持现有调用约定。"""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _normalize_branch_address(value):
    """规范化并返回 _normalize_branch_address 对应的业务数据，保持现有调用约定。"""
    return str(value or "").strip().rstrip("/").lower()


def _suggested_module_key(module):
    """处理 _suggested_module_key 对应的业务步骤，并向调用方返回所需结果。"""
    return "|".join(sorted(_module_match_aliases(module)))


def _is_ignored_missing_module_name(value):
    """判断 _is_ignored_missing_module_name 对应的业务数据，保持现有调用约定。"""
    text = str(value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9-]+", "-", text).strip("-")
    if not normalized:
        return True
    if normalized in {"once", "query", "querier", "client", "server", "service", "request", "response", "rpc", "http"}:
        return True
    if normalized.startswith("zhuiyi-"):
        return True
    if "minio" in normalized or normalized.endswith("-cluster") or normalized == "cluster":
        return True
    return False


def dedupe_related_modules(modules):
    """合并整理并返回 dedupe_related_modules 对应的业务数据，保持现有调用约定。"""
    deduped = []
    seen = set()
    for module in modules or []:
        key = (
            str(module.get("moduleId") or module.get("moduleName") or ""),
            module.get("role") or "related",
            module.get("branchAddress") or "",
            module.get("tagVersion") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(module)
    return deduped


def _guess_code_language(file_path):
    """查找或推断并返回 _guess_code_language 对应的业务数据，保持现有调用约定。"""
    suffix = Path(str(file_path)).suffix.lower()
    return {
        ".java": "java",
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".vue": "vue",
        ".go": "go",
        ".xml": "xml",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".properties": "properties",
    }.get(suffix, "")


def _clean_text(value):
    """规范化并返回 _clean_text 对应的业务数据，保持现有调用约定。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return repair_mojibake_text(json.dumps(value, ensure_ascii=False, indent=2)).strip()
    return repair_mojibake_text(value).strip()


def _clean_markdown_text(value):
    """规范化并返回 _clean_markdown_text 对应的业务数据，保持现有调用约定。"""
    text = _clean_text(value)
    if not text:
        return ""
    cleaned_lines = []
    in_code_block = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block and stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                cleaned_lines.append(f"\u3010{heading}\u3011")
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def _indent_code(content):
    """处理 _indent_code 对应的业务步骤，并向调用方返回所需结果。"""
    return "\n".join(f"    {line}" if line else "" for line in content.splitlines())


class AnalysisResultWindow:
    """AnalysisResultWindow 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, parent, payload):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.window = tk.Toplevel(parent)
        self.window.title("\u5206\u6790\u7ed3\u679c\u8be6\u60c5")
        self.window.geometry("1120x760")
        self.payload = payload
        self.sections = build_analysis_sections(payload)
        self.section_marks = {}
        self.nav_entries = []

        self._build_layout()
        self._render_sections()
        self.nav_list.selection_set(0)

    def _build_layout(self):
        """构建并返回 _build_layout 对应的业务数据，保持现有调用约定。"""
        container = ttk.Frame(self.window, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))
        ttk.Label(header, text="\u5206\u6790\u7ed3\u679c\u8be6\u60c5", font=("Microsoft YaHei UI", 15, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="\u590d\u5236\u5168\u90e8", command=self._copy_all).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="\u5bfc\u51fa HTML", command=self._export_html).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="\u5173\u95ed", command=self.window.destroy).pack(side=tk.RIGHT)

        nav_frame = ttk.LabelFrame(container, text="\u76ee\u5f55", padding=8)
        nav_frame.grid(row=1, column=0, sticky=tk.NS, padx=(0, 12))
        self.nav_list = tk.Listbox(
            nav_frame,
            width=22,
            activestyle="none",
            font=("Microsoft YaHei UI", 10),
            exportselection=False,
        )
        self.nav_list.pack(fill=tk.BOTH, expand=True)
        self.nav_list.bind("<<ListboxSelect>>", self._on_nav_selected)

        content_frame = ttk.Frame(container)
        content_frame.grid(row=1, column=1, sticky=tk.NSEW)
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        self.content_text = scrolledtext.ScrolledText(
            content_frame,
            wrap=tk.WORD,
            font=("Microsoft YaHei UI", 10),
            padx=18,
            pady=14,
        )
        self.content_text.grid(row=0, column=0, sticky=tk.NSEW)
        self.content_text.tag_configure("title", font=("Microsoft YaHei UI", 15, "bold"), spacing1=10, spacing3=8)
        self.content_text.tag_configure("subtitle", font=("Microsoft YaHei UI", 12, "bold"), spacing1=8, spacing3=6)
        self.content_text.tag_configure("body", lmargin1=8, lmargin2=8, spacing3=8)
        self.content_text.tag_configure("code_header", font=("Consolas", 10, "bold"), foreground="#24517a", spacing1=10)
        self.content_text.tag_configure(
            "code",
            font=("Consolas", 10),
            background="#f3f6f8",
            foreground="#202124",
            lmargin1=18,
            lmargin2=18,
            spacing1=4,
            spacing3=10,
        )

    def _render_sections(self):
        """格式化或整理并返回 _render_sections 对应的业务数据，保持现有调用约定。"""
        self.content_text.configure(state=tk.NORMAL)
        self.content_text.delete("1.0", tk.END)
        self.nav_list.delete(0, tk.END)
        self.nav_entries = []
        for index, section in enumerate(self.sections):
            mark_name = f"section_{index}"
            self.section_marks[index] = mark_name
            self.content_text.mark_set(mark_name, tk.INSERT)
            self.content_text.mark_gravity(mark_name, tk.LEFT)
            self._add_nav_entry(section["title"], mark_name)
            self.content_text.insert(tk.END, section["title"] + "\n", "title")
            if section["kind"] == "code_list":
                self._insert_code_items(section.get("items", []))
            elif section["kind"] == "code_finding_list":
                self._insert_code_findings(section.get("items", []))
            elif section["kind"] == "issue_list":
                self._insert_issue_items(section.get("items", []), index)
            else:
                self._insert_text_section(section, index)
        self.content_text.configure(state=tk.DISABLED)

    def _insert_text_section(self, section, section_index):
        """保存 _insert_text_section 对应的业务数据，保持现有调用约定。"""
        content = section.get("content", "")
        if content:
            self.content_text.insert(tk.END, content + "\n\n", "body")
        for child_index, child in enumerate(section.get("children", [])):
            mark_name = f"section_{section_index}_child_{child_index}"
            self.content_text.mark_set(mark_name, tk.INSERT)
            self.content_text.mark_gravity(mark_name, tk.LEFT)
            indent_level = max(1, min(4, int(child.get("level", 2)) - 1))
            self._add_nav_entry(("  " * indent_level) + child["title"], mark_name)
            self.content_text.insert(tk.END, child["title"] + "\n", "subtitle")
            if child.get("content"):
                self.content_text.insert(tk.END, child["content"] + "\n\n", "body")

    def _add_nav_entry(self, label, mark_name):
        """处理 _add_nav_entry 对应的业务步骤，并向调用方返回所需结果。"""
        safe_label = repair_mojibake_text(label)
        self.nav_entries.append({"label": safe_label, "mark": mark_name})
        self.nav_list.insert(tk.END, safe_label)

    def _insert_code_items(self, items):
        """保存 _insert_code_items 对应的业务数据，保持现有调用约定。"""
        for index, item in enumerate(items, start=1):
            header = _format_code_item_header(index, item)
            self.content_text.insert(tk.END, header + "\n", "code_header")
            self.content_text.insert(tk.END, (item.get("content") or "") + "\n\n", "code")

    def _insert_code_findings(self, items):
        """保存 _insert_code_findings 对应的业务数据，保持现有调用约定。"""
        for index, item in enumerate(items, start=1):
            header = _format_code_item_header(index, item)
            self.content_text.insert(tk.END, header + "\n", "code_header")
            if item.get("reason"):
                self.content_text.insert(tk.END, f"  \u5b9a\u4f4d\u539f\u56e0: {item['reason']}\n", "body")
            self.content_text.insert(tk.END, (item.get("code") or "") + "\n\n", "code")

    def _insert_issue_items(self, items, section_index):
        """保存 _insert_issue_items 对应的业务数据，保持现有调用约定。"""
        for item_index, issue in enumerate(items or [], start=1):
            issue_number = issue.get("index") or item_index
            issue_title = issue.get("title") or f"问题{issue_number}"
            issue_mark = f"section_{section_index}_issue_{item_index}"
            self.content_text.mark_set(issue_mark, tk.INSERT)
            self.content_text.mark_gravity(issue_mark, tk.LEFT)
            self._add_nav_entry(f"  问题{issue_number} · {issue_title}", issue_mark)
            self.content_text.insert(tk.END, f"问题{issue_number} · {issue_title}\n", "subtitle")

            details = [
                ("现象摘要", issue.get("summary"), "body"),
                ("根因判断", issue.get("root_cause"), "body"),
                ("分析依据", "\n".join(f"- {value}" for value in issue.get("evidence") or []), "body"),
                ("修复建议", issue.get("solution"), "body"),
                ("排查命令", "\n".join(f"{i}. {value}" for i, value in enumerate(issue.get("query_commands") or [], start=1)), "code"),
                ("修复命令", "\n".join(f"{i}. {value}" for i, value in enumerate(issue.get("fix_commands") or [], start=1)), "code"),
            ]
            if issue.get("code_items"):
                code_text = _format_code_findings(issue.get("code_items"))
            else:
                code_text = "\n".join(
                    f"{location.get('file') or UNKNOWN_FILE_LABEL}"
                    f"{':' + str(location.get('line')) if location.get('line') else ''}"
                    f" - {location.get('reason') or ''}".rstrip()
                    for location in issue.get("code_locations") or []
                )
            details.append(("相关代码", code_text, "code"))

            for detail_index, (title, content, tag) in enumerate(details):
                if not content:
                    continue
                detail_mark = f"{issue_mark}_detail_{detail_index}"
                self.content_text.mark_set(detail_mark, tk.INSERT)
                self.content_text.mark_gravity(detail_mark, tk.LEFT)
                self._add_nav_entry(f"    {title}", detail_mark)
                self.content_text.insert(tk.END, title + "\n", "subtitle")
                self.content_text.insert(tk.END, str(content) + "\n\n", tag)

    def _on_nav_selected(self, event=None):
        """处理 _on_nav_selected 对应的业务数据，保持现有调用约定。"""
        selection = self.nav_list.curselection()
        if not selection:
            return
        entry = self.nav_entries[selection[0]] if selection[0] < len(self.nav_entries) else None
        mark_name = entry.get("mark") if entry else None
        if mark_name:
            self.content_text.see(mark_name)
            self.window.after_idle(lambda: self.content_text.see(mark_name))

    def _copy_all(self):
        """处理 _copy_all 对应的业务步骤，并向调用方返回所需结果。"""
        text = self.content_text.get("1.0", tk.END).strip()
        self.window.clipboard_clear()
        self.window.clipboard_append(text)

    def _export_html(self):
        """处理 _export_html 对应的业务步骤，并向调用方返回所需结果。"""
        file_path = filedialog.asksaveasfilename(
            parent=self.window,
            title="\u5bfc\u51fa\u5206\u6790\u7ed3\u679c\u4e3a HTML",
            defaultextension=".html",
            initialfile=build_result_export_filename(self.payload),
            filetypes=[("HTML \u6587\u4ef6", "*.html"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
        )
        if not file_path:
            return
        try:
            html = build_result_html_document("\u5206\u6790\u7ed3\u679c", self.payload)
            Path(file_path).write_text(html, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("\u5bfc\u51fa\u5931\u8d25", format_exception_message(exc), parent=self.window)
            return
        messagebox.showinfo("\u5bfc\u51fa\u6210\u529f", f"\u5df2\u5bfc\u51fa\uff1a{file_path}", parent=self.window)


class RelatedModuleVersionDialog:
    """RelatedModuleVersionDialog 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, parent, items):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.parent = parent
        self.items = items
        self.result = None
        self.rows = []
        self.window = tk.Toplevel(parent)
        self.window.title("\u9009\u62e9\u4e0a\u4e0b\u6e38\u6a21\u5757\u7248\u672c")
        self.window.geometry("860x420")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()

    def _build(self):
        """构建并返回 _build 对应的业务数据，保持现有调用约定。"""
        container = ttk.Frame(self.window, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            container,
            text="\u8bc6\u522b\u5230\u53ef\u80fd\u76f8\u5173\u7684\u4e0a\u4e0b\u6e38\u6a21\u5757\uff0c\u8bf7\u9009\u62e9\u5b83\u4eec\u5b9e\u9645\u53d1\u5e03\u7684\u5206\u652f/Tag\u3002",
            font=("Microsoft YaHei UI", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))

        table = ttk.Frame(container)
        table.pack(fill=tk.BOTH, expand=True)
        for column, text, width in [
            (0, "\u6a21\u5757", 20),
            (1, "Git \u5730\u5740", 42),
            (2, "\u5206\u652f/Tag", 24),
            (3, "\u8bc6\u522b\u539f\u56e0", 36),
        ]:
            ttk.Label(table, text=text, font=("Microsoft YaHei UI", 10, "bold"), width=width).grid(row=0, column=column, sticky=tk.W, padx=4, pady=4)

        for row_index, item in enumerate(self.items, start=1):
            branch_var = tk.StringVar(value=item.get("branchAddress", ""))
            version_var = tk.StringVar(value=item.get("tagVersion", ""))
            ttk.Label(table, text=item.get("moduleName") or item.get("moduleId") or "-", width=20).grid(row=row_index, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(table, textvariable=branch_var, width=42).grid(row=row_index, column=1, sticky=tk.W, padx=4, pady=4)
            version_combo = ttk.Combobox(table, textvariable=version_var, values=item.get("versions") or [], state="normal", width=24)
            version_combo.grid(row=row_index, column=2, sticky=tk.W, padx=4, pady=4)
            reason = str(item.get("reason") or "")
            ttk.Label(table, text=reason, width=36, wraplength=250).grid(row=row_index, column=3, sticky=tk.W, padx=4, pady=4)
            self.rows.append((item, branch_var, version_var))

        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(actions, text="\u7ee7\u7eed\u5206\u6790", command=self._confirm).pack(side=tk.RIGHT)
        ttk.Button(actions, text="\u8df3\u8fc7\u5173\u8054\u6a21\u5757", command=self._skip).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="\u53d6\u6d88", command=self._cancel).pack(side=tk.RIGHT, padx=(0, 8))

    def _collect(self):
        """处理 _collect 对应的业务步骤，并向调用方返回所需结果。"""
        selected = []
        for item, branch_var, version_var in self.rows:
            branch_address = branch_var.get().strip()
            tag_version = version_var.get().strip()
            if not branch_address or not tag_version:
                raise ValueError(f"\u8bf7\u8865\u5168\u6a21\u5757 {item.get('moduleName')} \u7684 Git \u5730\u5740\u548c\u5206\u652f/Tag")
            selected.append({
                "moduleId": item.get("moduleId"),
                "moduleName": item.get("moduleName"),
                "role": item.get("role") or "related",
                "reason": item.get("reason") or "",
                "branchAddress": branch_address,
                "tagVersion": tag_version,
            })
        return selected

    def _confirm(self):
        """处理 _confirm 对应的业务步骤，并向调用方返回所需结果。"""
        try:
            self.result = self._collect()
        except ValueError as exc:
            messagebox.showwarning("\u4fe1\u606f\u4e0d\u5b8c\u6574", str(exc), parent=self.window)
            return
        self.window.destroy()

    def _skip(self):
        """处理 _skip 对应的业务步骤，并向调用方返回所需结果。"""
        self.result = []
        self.window.destroy()

    def _cancel(self):
        """取消 _cancel 对应的业务数据，保持现有调用约定。"""
        self.result = None
        self.window.destroy()

    def show(self):
        """处理 show 对应的业务步骤，并向调用方返回所需结果。"""
        self.window.wait_window()
        return self.result


class RelatedCodeVersionDialog:
    """RelatedCodeVersionDialog 类封装该领域对象的状态、依赖与相关行为。"""
    ROLE_OPTIONS = [
        ("upstream", "上游"),
        ("downstream", "下游"),
        ("related", "关联"),
    ]
    ROLE_LABEL_BY_VALUE = dict(ROLE_OPTIONS)
    ROLE_VALUE_BY_LABEL = {label: value for value, label in ROLE_OPTIONS}

    def __init__(self, parent, candidates, decision=None, version_loader=None):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.parent = parent
        self.candidates = candidates or []
        self.decision = decision or {}
        self.version_loader = version_loader
        self.result = None
        self.rows = []
        self.next_row_index = 1
        self.candidate_by_label = {
            self._candidate_label(candidate): candidate
            for candidate in self.candidates
            if candidate.get("repositoryAvailable", True)
        }
        self.window = tk.Toplevel(parent)
        self.window.title("选择上下游模块版本")
        self.window.geometry("960x560")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self._add_auto_selected()

    def _candidate_label(self, candidate):
        """处理 _candidate_label 对应的业务步骤，并向调用方返回所需结果。"""
        name = candidate.get("moduleName") or candidate.get("moduleId") or "-"
        return f"{candidate.get('moduleId') or '-'} - {name}"

    def _build(self):
        """构建并返回 _build 对应的业务数据，保持现有调用约定。"""
        container = ttk.Frame(self.window, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(container, text="选择上下游版本代码", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(
            container,
            text=self.decision.get("message") or "已识别到可能相关的上下游链路，请选择有权限仓库的实际发布分支/Tag。",
            wraplength=900,
        ).pack(anchor=tk.W, pady=(4, 8))
        ttk.Label(
            container,
            text="分支/Tag 已优先从服务端缓存自动加载；缓存不存在或需要最新数据时，可点击“手动同步所选分支/Tag”。",
            wraplength=900,
            foreground="#526070",
        ).pack(anchor=tk.W, pady=(0, 8))
        missing_modules = [
            candidate.get("moduleName") or candidate.get("moduleId") or "-"
            for candidate in self.candidates
            if candidate.get("autoSelect") and not candidate.get("repositoryAvailable", True)
        ]
        if missing_modules:
            missing_text = "以下模块未在当前 Git 仓库列表中匹配到可用仓库/版本，将仅作为分析提示，不会拉取代码：\n" + "\n".join(f"- {name}" for name in missing_modules)
            ttk.Label(container, text=missing_text, wraplength=900, foreground="#b45309").pack(anchor=tk.W, pady=(0, 8))

        picker = ttk.Frame(container)
        picker.pack(fill=tk.X, pady=(0, 10))
        self.module_var = tk.StringVar()
        module_values = list(self.candidate_by_label.keys())
        ttk.Label(picker, text="模块").pack(side=tk.LEFT)
        self.module_combo = ttk.Combobox(picker, textvariable=self.module_var, values=module_values, state="readonly", width=38)
        self.module_combo.pack(side=tk.LEFT, padx=(6, 12))
        if module_values:
            self.module_var.set(module_values[0])
        self.role_var = tk.StringVar(value=self.ROLE_LABEL_BY_VALUE["downstream"])
        ttk.Label(picker, text="方向").pack(side=tk.LEFT)
        ttk.Combobox(
            picker,
            textvariable=self.role_var,
            values=[label for _, label in self.ROLE_OPTIONS],
            state="readonly",
            width=12,
        ).pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(picker, text="添加模块", command=self._add_selected).pack(side=tk.LEFT)

        table_frame = ttk.LabelFrame(container, text="已选模块版本", padding=8)
        table_frame.pack(fill=tk.BOTH, expand=True)
        self.table = ttk.Frame(table_frame)
        self.table.pack(fill=tk.BOTH, expand=True)
        for column, text, width in [
            (0, "拉取", 6),
            (1, "方向", 10),
            (2, "模块", 24),
            (3, "Git 地址", 48),
            (4, "分支/Tag", 24),
            (5, "操作", 8),
        ]:
            ttk.Label(self.table, text=text, font=("Microsoft YaHei UI", 10, "bold"), width=width).grid(row=0, column=column, sticky=tk.W, padx=4, pady=4)

        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(footer, text="继续判断", command=self._confirm).pack(side=tk.RIGHT)
        ttk.Button(footer, text="不选择上下游代码", command=self._skip).pack(side=tk.RIGHT, padx=(0, 8))
        self.sync_button = ttk.Button(footer, text="手动同步所选分支/Tag", command=self._sync_selected_versions_async)
        self.sync_button.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(footer, text="取消", command=self._cancel).pack(side=tk.RIGHT, padx=(0, 8))

    def _role_display_value(self, role):
        """处理 _role_display_value 对应的业务步骤，并向调用方返回所需结果。"""
        return self.ROLE_LABEL_BY_VALUE.get(role, role or self.ROLE_LABEL_BY_VALUE["related"])

    def _add_auto_selected(self):
        """处理 _add_auto_selected 对应的业务步骤，并向调用方返回所需结果。"""
        for candidate in self.candidates:
            if candidate.get("autoSelect") and candidate.get("repositoryAvailable", True):
                self._add_candidate(candidate)

    def _add_selected(self):
        """处理 _add_selected 对应的业务步骤，并向调用方返回所需结果。"""
        label = self.module_var.get()
        candidate = self.candidate_by_label.get(label)
        if not candidate:
            messagebox.showwarning("未选择模块", "请先选择一个有权限的上下游模块", parent=self.window)
            return
        self._add_candidate(candidate, role_label=self.role_var.get() or self.ROLE_LABEL_BY_VALUE["related"])

    def _add_candidate(self, candidate, role_label=None):
        """处理 _add_candidate 对应的业务步骤，并向调用方返回所需结果。"""
        module_key = candidate.get("moduleId") or candidate.get("moduleName")
        if any(row["module_key"] == module_key for row in self.rows):
            messagebox.showinfo("已添加", "该模块已经在列表中", parent=self.window)
            return
        row_index = self.next_row_index
        self.next_row_index += 1
        role_var = tk.StringVar(value=role_label or self._role_display_value(candidate.get("role") or "related"))
        branch_var = tk.StringVar(value=candidate.get("branchAddress", ""))
        version_var = tk.StringVar(value=candidate.get("tagVersion", ""))
        selected_var = tk.BooleanVar(value=True)
        widgets = []
        select_check = ttk.Checkbutton(self.table, variable=selected_var)
        select_check.grid(row=row_index, column=0, sticky=tk.W, padx=4, pady=4)
        widgets.append(select_check)
        role_combo = ttk.Combobox(
            self.table,
            textvariable=role_var,
            values=[label for _, label in self.ROLE_OPTIONS],
            state="readonly",
            width=10,
        )
        role_combo.grid(row=row_index, column=1, sticky=tk.W, padx=4, pady=4)
        widgets.append(role_combo)
        module_label = ttk.Label(self.table, text=candidate.get("moduleName") or candidate.get("moduleId") or "-", width=24)
        module_label.grid(row=row_index, column=2, sticky=tk.W, padx=4, pady=4)
        widgets.append(module_label)
        branch_combo = ttk.Combobox(self.table, textvariable=branch_var, values=candidate.get("branchOptions") or ([candidate.get("branchAddress")] if candidate.get("branchAddress") else []), state="readonly", width=48)
        branch_combo.grid(row=row_index, column=3, sticky=tk.W, padx=4, pady=4)
        widgets.append(branch_combo)
        version_combo = ttk.Combobox(self.table, textvariable=version_var, values=candidate.get("versions") or [], state="readonly", width=24)
        version_combo.grid(row=row_index, column=4, sticky=tk.W, padx=4, pady=4)
        widgets.append(version_combo)
        remove_button = ttk.Button(self.table, text="移除", command=lambda key=module_key: self._remove_row(key))
        remove_button.grid(row=row_index, column=5, sticky=tk.W, padx=4, pady=4)
        widgets.append(remove_button)
        self.rows.append({
            "module_key": module_key,
            "candidate": candidate,
            "selected_var": selected_var,
            "role_var": role_var,
            "branch_var": branch_var,
            "version_var": version_var,
            "version_combo": version_combo,
            "widgets": widgets,
        })

    def _sync_selected_versions_async(self):
        """更新 _sync_selected_versions_async 对应的业务数据，保持现有调用约定。"""
        if not self.version_loader:
            messagebox.showwarning("无法同步", "当前没有可用的分支同步接口。", parent=self.window)
            return
        targets = []
        for row in self.rows:
            if not row["selected_var"].get():
                continue
            repo_url = row["branch_var"].get().strip()
            if repo_url:
                targets.append((row, repo_url))
        if not targets:
            messagebox.showinfo("无需同步", "请先勾选需要拉取代码的模块。", parent=self.window)
            return
        self.sync_button.configure(state=tk.DISABLED)

        def worker():
            """处理 worker 对应的业务步骤，并向调用方返回所需结果。"""
            results = []
            for row, repo_url in targets:
                try:
                    versions = self.version_loader(repo_url) or []
                    error = ""
                except Exception as exc:
                    versions = []
                    error = str(exc)
                results.append((row, repo_url, versions, error))
            self.window.after(0, lambda: self._apply_synced_versions(results))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_synced_versions(self, results):
        """设置或应用 _apply_synced_versions 对应的业务数据，保持现有调用约定。"""
        failed = []
        for row, repo_url, versions, error in results:
            clean_versions = []
            for version in versions or []:
                if version and version not in clean_versions:
                    clean_versions.append(version)
            if not clean_versions:
                failed.append(row["candidate"].get("moduleName") or repo_url)
                continue
            row["candidate"]["versions"] = clean_versions
            row["version_combo"].configure(values=clean_versions)
            if row["version_var"].get() not in clean_versions:
                row["version_var"].set(clean_versions[0])
        self.sync_button.configure(state=tk.NORMAL)
        if failed:
            messagebox.showwarning("部分同步失败", "以下模块未获取到分支/Tag：\n" + "\n".join(f"- {name}" for name in failed), parent=self.window)
        else:
            messagebox.showinfo("同步完成", "已同步所选模块的分支/Tag。", parent=self.window)

    def _remove_row(self, module_key):
        """清理 _remove_row 对应的业务数据，保持现有调用约定。"""
        next_rows = []
        for row in self.rows:
            if row["module_key"] == module_key:
                for widget in row["widgets"]:
                    widget.destroy()
            else:
                next_rows.append(row)
        self.rows = next_rows

    def _collect(self):
        """处理 _collect 对应的业务步骤，并向调用方返回所需结果。"""
        selected = []
        for row in self.rows:
            if not row["selected_var"].get():
                continue
            candidate = row["candidate"]
            branch_address = row["branch_var"].get().strip()
            tag_version = row["version_var"].get().strip()
            if not branch_address or not tag_version:
                raise ValueError(f"模块 {candidate.get('moduleName')} 没有可用仓库或版本，请先选择分支/Tag，或移除该模块后继续。")
            selected.append({
                "moduleId": candidate.get("moduleId"),
                "moduleName": candidate.get("moduleName"),
                "role": self.ROLE_VALUE_BY_LABEL.get(row["role_var"].get(), row["role_var"].get() or "related"),
                "reason": candidate.get("reason") or "用户选择参与上下游版本代码判断",
                "branchAddress": branch_address,
                "tagVersion": tag_version,
            })
        return selected

    def _confirm(self):
        """处理 _confirm 对应的业务步骤，并向调用方返回所需结果。"""
        try:
            self.result = self._collect()
        except ValueError as exc:
            messagebox.showwarning("信息不完整", str(exc), parent=self.window)
            return
        self.window.destroy()

    def _skip(self):
        """处理 _skip 对应的业务步骤，并向调用方返回所需结果。"""
        self.result = []
        self.window.destroy()

    def _cancel(self):
        """取消 _cancel 对应的业务数据，保持现有调用约定。"""
        self.result = None
        self.window.destroy()

    def show(self):
        """处理 show 对应的业务步骤，并向调用方返回所需结果。"""
        self.window.wait_window()
        return self.result


class RelatedEvidenceDialog:
    """RelatedEvidenceDialog 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, parent, decision):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.parent = parent
        self.decision = decision or {}
        self.result = None
        self.items = []
        self.window = tk.Toplevel(parent)
        self.window.title("\u8865\u5145\u4e0a\u4e0b\u6e38\u65e5\u5fd7/\u56fe\u7247")
        self.window.geometry("760x420")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()

    def _build(self):
        """构建并返回 _build 对应的业务数据，保持现有调用约定。"""
        container = ttk.Frame(self.window, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        summary = self.decision.get("issueSummary") or "\u5f53\u524d\u95ee\u9898\u53ef\u80fd\u6d89\u53ca\u4e0a\u4e0b\u6e38\u94fe\u8def"
        ttk.Label(container, text="\u9700\u8981\u8865\u5145\u4e0a\u4e0b\u6e38\u8bc1\u636e", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Label(container, text=summary, wraplength=700).pack(anchor=tk.W, pady=(4, 8))
        ttk.Label(container, text=self.decision.get("reason") or "", wraplength=700).pack(anchor=tk.W, pady=(0, 10))

        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(actions, text="\u6dfb\u52a0\u4e0a\u4e0b\u6e38\u65e5\u5fd7", command=self._add_logs).pack(side=tk.LEFT)
        ttk.Button(actions, text="\u6dfb\u52a0\u4e0a\u4e0b\u6e38\u56fe\u7247", command=self._add_images).pack(side=tk.LEFT, padx=(8, 0))

        list_frame = ttk.LabelFrame(container, text="\u5df2\u9009\u8bc1\u636e", padding=8)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.listbox = tk.Listbox(list_frame, height=8, font=("Microsoft YaHei UI", 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(footer, text="\u7ee7\u7eed\u5206\u6790", command=self._confirm).pack(side=tk.RIGHT)
        ttk.Button(footer, text="\u6682\u4e0d\u8865\u5145\uff0c\u7ee7\u7eed\u5206\u6790", command=self._skip).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(footer, text="\u53d6\u6d88", command=self._cancel).pack(side=tk.RIGHT, padx=(0, 8))

    def _add_logs(self):
        """处理 _add_logs 对应的业务步骤，并向调用方返回所需结果。"""
        paths = filedialog.askopenfilenames(
            parent=self.window,
            title="\u9009\u62e9\u4e0a\u4e0b\u6e38\u65e5\u5fd7",
            filetypes=[("\u65e5\u5fd7\u6587\u4ef6", "*.log *.txt *.gz"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
        )
        self._add_paths(paths, "file")

    def _add_images(self):
        """处理 _add_images 对应的业务步骤，并向调用方返回所需结果。"""
        paths = filedialog.askopenfilenames(
            parent=self.window,
            title="\u9009\u62e9\u4e0a\u4e0b\u6e38\u56fe\u7247",
            filetypes=[("\u56fe\u7247\u6587\u4ef6", "*.png *.jpg *.jpeg"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
        )
        self._add_paths(paths, "image")

    def _add_paths(self, paths, source_type):
        """处理 _add_paths 对应的业务步骤，并向调用方返回所需结果。"""
        for path in paths or []:
            normalized = str(Path(path))
            if any(item["path"] == normalized for item in self.items):
                continue
            label_type = "\u56fe\u7247" if source_type == "image" else "\u65e5\u5fd7"
            item = {
                "path": normalized,
                "source_type": source_type,
                "label": f"{label_type}: {Path(normalized).name}",
            }
            self.items.append(item)
            self.listbox.insert(tk.END, item["label"])

    def _confirm(self):
        """处理 _confirm 对应的业务步骤，并向调用方返回所需结果。"""
        self.result = list(self.items)
        self.window.destroy()

    def _skip(self):
        """处理 _skip 对应的业务步骤，并向调用方返回所需结果。"""
        self.result = []
        self.window.destroy()

    def _cancel(self):
        """取消 _cancel 对应的业务数据，保持现有调用约定。"""
        self.result = None
        self.window.destroy()

    def show(self):
        """处理 show 对应的业务步骤，并向调用方返回所需结果。"""
        self.window.wait_window()
        return self.result


class LogAnalyzerApiClient(ApiClient):

    """LogAnalyzerApiClient 类封装该领域对象的状态、依赖与相关行为。"""
    def get_products(self):
        """读取并返回 get_products 对应的业务数据，保持现有调用约定。"""
        response = self.session.get(f"{self.base_url}/product/get")
        response.raise_for_status()
        return response.json().get("products", [])

    def get_modules_by_product(self, product_id):
        """读取并返回 get_modules_by_product 对应的业务数据，保持现有调用约定。"""
        response = self.session.get(f"{self.base_url}/module/get", params={"product_id": product_id})
        response.raise_for_status()
        return response.json().get("modules", [])

    def search_modules_by_names(self, names):
        """查找或推断并返回 search_modules_by_names 对应的业务数据，保持现有调用约定。"""
        clean_names = [str(name).strip() for name in names or [] if str(name or "").strip()]
        if not clean_names:
            return []
        response = self.session.get(f"{self.base_url}/module/search", params={"names": ",".join(clean_names)})
        response.raise_for_status()
        return response.json().get("modules", [])

    def get_remote_branches(self, repo_url, force_refresh=False):
        """读取并返回 get_remote_branches 对应的业务数据，保持现有调用约定。"""
        params = {"repo_url": repo_url}
        if force_refresh:
            params["refresh"] = "1"
        response = self.session.get(f"{self.base_url}/git/branches", params=params)
        response.raise_for_status()
        payload = response.json()
        return payload.get("versions") or payload.get("branches", []) + payload.get("tags", [])

    def get_cached_branches(self, repo_url):
        """读取并返回 get_cached_branches 对应的业务数据，保持现有调用约定。"""
        response = self.session.get(
            f"{self.base_url}/git/branches",
            params={"repo_url": repo_url, "cached_only": "1"},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("versions") or []

    def sync_git_projects(self):
        """更新 sync_git_projects 对应的业务数据，保持现有调用约定。"""
        response = self.session.post(f"{self.base_url}/git/sync-projects")
        response.raise_for_status()
        return response.json()

    def upload_log(self, file_path, product_id, module_id, branch_address, tag_version, date_filter=""):
        """上传 upload_log 对应的业务数据，保持现有调用约定。"""
        path = Path(file_path)
        data = {
            "product_id": product_id,
            "module_id": module_id,
            "address": branch_address,
            "tag_version": tag_version,
        }
        if date_filter:
            data["date_filter"] = date_filter

        with path.open("rb") as file_obj:
            files = {"file": (path.name, file_obj)}
            response = self.session.post(f"{self.base_url}/logfile/upload", data=data, files=files)
            response.raise_for_status()
            return response.json()

    def upload_image(
        self,
        image_path,
        product_id,
        module_id,
        branch_address,
        tag_version,
        image_tag,
        image_description="",
    ):
        """上传 upload_image 对应的业务数据，保持现有调用约定。"""
        path = Path(image_path)
        data = {
            "product_id": product_id,
            "module_id": module_id,
            "address": branch_address,
            "tag_version": tag_version,
            "image_tag": image_tag,
            "image_description": image_description,
        }
        with path.open("rb") as file_obj:
            files = {"file": (path.name, file_obj)}
            response = self.session.post(f"{self.base_url}/logfile/upload_image", data=data, files=files)
            response.raise_for_status()
            return response.json()

    def upload_images(
        self,
        image_paths,
        product_id,
        module_id,
        branch_address,
        tag_version,
        image_tag,
        image_description="",
    ):
        """上传 upload_images 对应的业务数据，保持现有调用约定。"""
        paths = [Path(path) for path in image_paths if path]
        if not paths:
            raise ValueError("\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u5f20\u56fe\u7247")
        data = {
            "product_id": product_id,
            "module_id": module_id,
            "address": branch_address,
            "tag_version": tag_version,
            "image_tag": image_tag,
            "image_description": image_description,
        }
        with ExitStack() as stack:
            files = [
                ("files", (path.name, stack.enter_context(path.open("rb"))))
                for path in paths
            ]
            response = self.session.post(f"{self.base_url}/logfile/upload_image", data=data, files=files)
            response.raise_for_status()
            return response.json()

    def get_branch(self, branch_address, tag_version):
        """读取并返回 get_branch 对应的业务数据，保持现有调用约定。"""
        response = self.session.post(
            f"{self.base_url}/analysis/branch_get",
            json={"branchAddress": branch_address, "tagVersion": tag_version},
        )
        response.raise_for_status()
        return response.json()

    def analyze_log(self, product_id, module_id, branch_address, tag_version, repo_path, file_path):
        """执行故障分析并返回 analyze_log 对应的业务数据，保持现有调用约定。"""
        response = self.session.post(
            f"{self.base_url}/analysis/log_analysis",
            json={
                "productId": product_id,
                "moduleId": module_id,
                "branchAddress": branch_address,
                "tagVersion": tag_version,
                "repo_path": repo_path,
                "file_path": file_path,
            },
        )
        response.raise_for_status()
        return response.json()

    def discover_related_modules(
        self,
        product_id,
        module_id,
        branch_address,
        tag_version,
        file_path,
        source_type="file",
        image_tag="",
        image_description="",
        file_paths=None,
    ):
        """查找或推断并返回 discover_related_modules 对应的业务数据，保持现有调用约定。"""
        payload = {
            "productId": product_id,
            "moduleId": module_id,
            "branchAddress": branch_address,
            "tagVersion": tag_version,
            "file_path": file_path,
            "source_type": source_type,
        }
        if image_tag:
            payload["image_tag"] = image_tag
        if image_description:
            payload["image_description"] = image_description
        if file_paths:
            payload["file_paths"] = list(file_paths)
        response = self.session.post(
            f"{self.base_url}/analysis/discover_related_modules",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def assess_related_code(
        self,
        product_id,
        module_id,
        branch_address,
        tag_version,
        file_path,
        related_modules,
        source_type="file",
        image_tag="",
        image_description="",
        file_paths=None,
    ):
        """执行故障分析并返回 assess_related_code 对应的业务数据，保持现有调用约定。"""
        payload = {
            "productId": product_id,
            "moduleId": module_id,
            "branchAddress": branch_address,
            "tagVersion": tag_version,
            "file_path": file_path,
            "source_type": source_type,
            "relatedModules": list(related_modules or []),
        }
        if image_tag:
            payload["image_tag"] = image_tag
        if image_description:
            payload["image_description"] = image_description
        if file_paths:
            payload["file_paths"] = list(file_paths)
        response = self.session.post(
            f"{self.base_url}/analysis/assess_related_code",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def submit_analysis_task(
        self,
        product_id,
        module_id,
        branch_address,
        tag_version,
        file_path,
        log_id=None,
        source_type="file",
        image_tag="",
        image_description="",
        file_paths=None,
        log_ids=None,
        related_modules=None,
        related_evidence=None,
        skipped_chain_issues=None,
        image_ocr=None,
    ):
        """提交 submit_analysis_task 对应的业务数据，保持现有调用约定。"""
        payload = {
            "productId": product_id,
            "moduleId": module_id,
            "branchAddress": branch_address,
            "tagVersion": tag_version,
            "file_path": file_path,
            "source_type": source_type,
        }
        if log_id:
            payload["log_id"] = log_id
        if image_tag:
            payload["image_tag"] = image_tag
        if image_description:
            payload["image_description"] = image_description
        if file_paths:
            payload["file_paths"] = list(file_paths)
        if log_ids:
            payload["log_ids"] = list(log_ids)
        if related_modules:
            payload["relatedModules"] = list(related_modules)
        if related_evidence:
            payload["relatedEvidence"] = list(related_evidence)
        if skipped_chain_issues:
            payload["skippedChainIssues"] = list(skipped_chain_issues)
        if isinstance(image_ocr, dict):
            payload["image_ocr"] = dict(image_ocr)
        response = self.session.post(
            f"{self.base_url}/analysis/submit_async",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def get_task_status(self, task_id):
        """读取并返回 get_task_status 对应的业务数据，保持现有调用约定。"""
        response = self.session.get(f"{self.base_url}/analysis/task/{task_id}")
        response.raise_for_status()
        return response.json()

    def cancel_task(self, task_id):
        """取消 cancel_task 对应的业务数据，保持现有调用约定。"""
        response = self.session.post(f"{self.base_url}/analysis/task/{task_id}/cancel")
        response.raise_for_status()
        return response.json()


def poll_task_until_ready(
    client,
    task_id,
    on_status=None,
    on_progress=None,
    should_cancel=None,
    sleep_func=time.sleep,
    poll_interval=2,
    max_status_errors=10,
    max_polls=600,
):
    """轮询或等待 poll_task_until_ready 对应的业务数据，保持现有调用约定。"""
    consecutive_errors = 0
    poll_count = 0

    while True:
        if should_cancel and should_cancel():
            raise OperationCancelled("\u64cd\u4f5c\u5df2\u4e2d\u65ad")
        poll_count += 1
        if max_polls and poll_count > max_polls:
            raise RuntimeError(
                f"分析任务长时间未完成，已停止轮询。task_id={task_id}，"
                "请检查 Celery worker 是否在运行、任务是否卡住、result backend 是否能写回状态。"
            )

        try:
            task_status = client.get_task_status(task_id)
            consecutive_errors = 0
        except requests.RequestException as exc:
            consecutive_errors += 1
            message = f"\u8f6e\u8be2\u6682\u65f6\u5931\u8d25\uff0c\u7b49\u5f85\u670d\u52a1\u6062\u590d({consecutive_errors}/{max_status_errors})"
            if on_status:
                on_status(message)
            if consecutive_errors > max_status_errors:
                raise RuntimeError(f"\u8fde\u7eed\u8f6e\u8be2\u4efb\u52a1\u72b6\u6001\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u540e\u7aef\u670d\u52a1\u6216\u7f51\u7edc: {exc}") from exc
            sleep_func(poll_interval)
            continue

        state = task_status.get("state", "UNKNOWN")
        progress = task_status.get("progress")
        if isinstance(progress, dict):
            if on_progress:
                on_progress(progress)
        elif on_status:
            on_status(f"\u5206\u6790\u4efb\u52a1\u72b6\u6001\uff1a{state}")
        if state == "REVOKED":
            raise OperationCancelled("\u4efb\u52a1\u5df2\u4e2d\u65ad")
        if task_status.get("ready"):
            if task_status.get("successful"):
                return task_status.get("result", task_status)
            raise RuntimeError(task_status.get("error") or f"\u5206\u6790\u4efb\u52a1\u5931\u8d25\uff1a{state}")
        sleep_func(poll_interval)


class LogAnalyzerWindow:
    """LogAnalyzerWindow 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, root, api_client=None):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.root = root
        self.api_client = api_client
        self.root.title(APP_RELEASE_LABEL)
        self.root.geometry("1280x860")
        self.root.minsize(1100, 760)
        self.root.deiconify()
        self.upload_result = None
        self.repo_path = None
        self.task_id = None
        self.products = []
        self.modules = []
        self.all_modules = []
        self.all_modules_loaded = False
        self.product_by_label = {}
        self.module_by_label = {}
        self.branch_versions = {}
        self.version_refresh_attempted = set()
        self.last_failed_action = None
        self.retry_button = None
        self.cancel_button = None
        self.cancel_requested = False
        self.analysis_running = False
        self.progress_animation_job = None
        self.progress_animation_target = 0
        self._combobox_all_values = {}
        self._pasted_image_path = None
        self.image_paths = []

        self.backend_url = tk.StringVar(value=api_client.base_url if api_client else DEFAULT_BACKEND_URL)
        self.product_selection = tk.StringVar()
        self.module_selection = tk.StringVar()
        self.product_id = tk.StringVar()
        self.module_id = tk.StringVar()
        self.branch_address = tk.StringVar()
        self.tag_version = tk.StringVar()
        self.input_mode = tk.StringVar(value="file")
        self.image_tag = tk.StringVar(value="log_image")
        self.path_label_var = tk.StringVar(value="\u65e5\u5fd7\u6587\u4ef6")
        self.choose_button_text = tk.StringVar(value="\u9009\u62e9\u6587\u4ef6")
        self.date_filter = tk.StringVar(value="")
        self.file_path = tk.StringVar()
        self.status = tk.StringVar(value="\u5c31\u7eea")
        self.progress_text = tk.StringVar(value="\u7b49\u5f85\u5f00\u59cb")
        self.progress_percent = tk.DoubleVar(value=0)

        self._build_layout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.root.after(200, self.refresh_products_async)

    def _build_layout(self):
        """构建并返回 _build_layout 对应的业务数据，保持现有调用约定。"""
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        self._build_notice(container)

        progress_frame = ttk.Frame(container, padding=(0, 0, 0, 8))
        progress_frame.pack(fill=tk.X)
        ttk.Progressbar(progress_frame, variable=self.progress_percent, maximum=100, mode="determinate").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_text, justify=tk.LEFT, wraplength=520)
        self.progress_label.pack(side=tk.LEFT, padx=8)

        form = ttk.LabelFrame(container, text="\u5206\u6790\u914d\u7f6e", padding=12)
        form.pack(fill=tk.X)
        for column in range(5):
            form.columnconfigure(column, weight=0)
        form.columnconfigure(1, weight=1)

        self.backend_entry = self._add_entry(form, "\u540e\u7aef\u5730\u5740", self.backend_url, 0, 0, width=42)
        self.sync_git_button = ttk.Button(form, text="\u540c\u6b65 Git \u9879\u76ee", command=self.sync_git_projects_async)
        self.sync_git_button.grid(row=0, column=2, padx=8, pady=6, sticky=tk.W)

        ttk.Label(form, text="\u4ea7\u54c1").grid(row=1, column=0, sticky=tk.W, pady=6)
        self.product_combo = ttk.Combobox(form, textvariable=self.product_selection, state="normal", width=42)
        self.product_combo.grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=6)
        self._bind_searchable_combobox(self.product_combo, self.on_product_selected)

        ttk.Label(form, text="\u6a21\u5757").grid(row=2, column=0, sticky=tk.W, pady=6)
        self.module_combo = ttk.Combobox(form, textvariable=self.module_selection, state="normal", width=42)
        self.module_combo.grid(row=2, column=1, columnspan=3, sticky=tk.EW, pady=6)
        self._bind_searchable_combobox(self.module_combo, self.on_module_selected)

        ttk.Label(form, text="\u5206\u652f\u5730\u5740").grid(row=3, column=0, sticky=tk.W, pady=6)
        self.branch_combo = ttk.Combobox(form, textvariable=self.branch_address, state="normal", width=56)
        self.branch_combo.grid(row=3, column=1, columnspan=3, sticky=tk.EW, pady=6)
        self._bind_searchable_combobox(self.branch_combo, self.on_branch_selected)

        ttk.Label(form, text="\u7248\u672c/Tag").grid(row=4, column=0, sticky=tk.W, pady=6)
        self.tag_combo = ttk.Combobox(form, textvariable=self.tag_version, state="normal", width=28)
        self.tag_combo.grid(row=4, column=1, sticky=tk.W, pady=6)
        self._bind_searchable_combobox(self.tag_combo)
        self.refresh_versions_button = ttk.Button(form, text="\u62c9\u53d6\u7248\u672c\u53f7", command=self.refresh_branch_versions_async)
        self.refresh_versions_button.grid(row=4, column=2, padx=8, pady=6, sticky=tk.W)

        ttk.Label(form, text="\u8f93\u5165\u65b9\u5f0f").grid(row=5, column=0, sticky=tk.W, pady=6)
        mode_frame = ttk.Frame(form)
        mode_frame.grid(row=5, column=1, columnspan=3, sticky=tk.W, pady=6)
        ttk.Radiobutton(mode_frame, text="\u65e5\u5fd7\u6587\u4ef6", value="file", variable=self.input_mode, command=self._on_input_mode_changed).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="\u56fe\u7247\u8bc6\u522b", value="image", variable=self.input_mode, command=self._on_input_mode_changed).pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(form, text="\u65e5\u671f\u8fc7\u6ee4").grid(row=6, column=0, sticky=tk.W, pady=6)
        self.date_combo = ttk.Combobox(form, textvariable=self.date_filter, values=("", "-1", "-2", "-3", "-7", "2026-06-07"), state="normal", width=24)
        self.date_combo.grid(row=6, column=1, sticky=tk.W, pady=6)
        self._bind_searchable_combobox(self.date_combo)
        self._set_combobox_values(self.date_combo, ["", "-1", "-2", "-3", "-7", "2026-06-07"])

        self.path_label = ttk.Label(form, textvariable=self.path_label_var)
        self.path_label.grid(row=7, column=0, sticky=tk.W, pady=6)
        self.log_file_entry = ttk.Entry(form, textvariable=self.file_path, width=48)
        self.log_file_entry.grid(row=7, column=1, sticky=tk.EW, pady=6)
        self.choose_file_button = ttk.Button(form, textvariable=self.choose_button_text, command=self.choose_file)
        self.choose_file_button.grid(row=7, column=2, padx=8, pady=6, sticky=tk.W)
        self.paste_image_button = ttk.Button(form, text="\u7c98\u8d34\u56fe\u7247", command=self.paste_image)
        self.paste_image_button.grid(row=7, column=3, padx=8, pady=6, sticky=tk.W)
        self.clear_file_button = ttk.Button(form, text="\u6e05\u7a7a", command=self.clear_selected_input)
        self.clear_file_button.grid(row=7, column=4, padx=8, pady=6, sticky=tk.W)

        self.image_tag_label = ttk.Label(
            form,
            text="图片类型（日志截图请选择 log_image；业务页面请选择 business_image）",
        )
        self.image_tag_label.grid(row=8, column=0, sticky=tk.W, pady=6)
        self.image_tag_label.configure(text="\u56fe\u7247\u7c7b\u578b")
        self.image_tag_combo = ttk.Combobox(form, textvariable=self.image_tag, values=("log_image", "business_image"), state="readonly", width=24)
        self.image_tag_combo.grid(row=8, column=1, sticky=tk.W, pady=6)
        self.image_tag_help = ttk.Label(
            form,
            text="\u65e5\u5fd7\u622a\u56fe\u8bf7\u9009\u62e9 log_image\uff1b\u4e1a\u52a1\u9875\u9762\u8bf7\u9009\u62e9 business_image",
            justify=tk.LEFT,
            wraplength=820,
        )
        self.image_tag_help.grid(row=9, column=1, columnspan=4, sticky=tk.EW, pady=(0, 4))

        self.image_description_label = ttk.Label(form, text="\u56fe\u7247\u63cf\u8ff0")
        self.image_description_label.grid(row=10, column=0, sticky=tk.NW, pady=6)
        self.image_description_text = tk.Text(form, width=48, height=4, font=("Microsoft YaHei UI", 10))
        self.image_description_text.grid(row=10, column=1, columnspan=4, sticky=tk.EW, pady=6)

        drop_hint_text = (
            "\u652f\u6301\u76f4\u63a5\u62d6\u62fd\u56fe\u7247\u5230\u8fd9\u91cc\uff0c\u4e5f\u53ef\u4ee5\u4f7f\u7528\u7c98\u8d34\u56fe\u7247/\u9009\u62e9\u6587\u4ef6"
            if DRAG_DROP_ENABLED
            else "\u5f53\u524d\u6253\u5305\u73af\u5883\u672a\u542f\u7528\u62d6\u62fd\uff0c\u8bf7\u4f7f\u7528\u7c98\u8d34\u56fe\u7247\u6216\u9009\u62e9\u6587\u4ef6"
        )
        self.drop_hint = ttk.Label(form, text=drop_hint_text, relief=tk.GROOVE, padding=10, justify=tk.LEFT, wraplength=820)
        self.drop_hint.grid(row=11, column=1, columnspan=4, sticky=tk.EW, pady=(0, 6))

        self.image_list_frame = ttk.LabelFrame(form, text="\u5df2\u6682\u5b58\u56fe\u7247", padding=6)
        self.image_list_frame.grid(row=12, column=1, columnspan=4, sticky=tk.EW, pady=(0, 6))
        self.image_list_rows = ttk.Frame(self.image_list_frame)
        self.image_list_rows.pack(fill=tk.X)
        self.image_list_empty_label = ttk.Label(self.image_list_rows, text="\u8fd8\u6ca1\u6709\u6682\u5b58\u56fe\u7247\uff0c\u53ef\u9009\u62e9\u3001\u7c98\u8d34\u6216\u62d6\u62fd\u591a\u5f20\u56fe\u7247")
        self.image_list_empty_label.pack(anchor=tk.W)

        actions = ttk.Frame(form)
        actions.grid(row=8, column=2, columnspan=3, sticky=tk.W, padx=8, pady=6)
        self.upload_button = ttk.Button(actions, text="\u4e0a\u4f20\u65e5\u5fd7", command=self.upload_async)
        self.upload_button.pack(side=tk.LEFT)
        self.analyze_button = ttk.Button(actions, text="\u5f00\u59cb\u5206\u6790", command=self.analyze_or_cancel)
        self.analyze_button.pack(side=tk.LEFT, padx=8)
        self.status_label = ttk.Label(form, textvariable=self.status, justify=tk.LEFT, wraplength=960)
        self.status_label.grid(row=13, column=1, columnspan=4, sticky=tk.EW, pady=(0, 4))

        result_frame = ttk.LabelFrame(container, text="\u6267\u884c\u7ed3\u679c", padding=8)
        result_frame.pack(fill=tk.BOTH, expand=True)
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.result_text.pack(fill=tk.BOTH, expand=True)

        self._install_drop_support()
        self._on_input_mode_changed()

    def _build_notice(self, parent):
        """构建并返回 _build_notice 对应的业务数据，保持现有调用约定。"""
        notice = ttk.LabelFrame(parent, text="\u516c\u544a\u8bf4\u660e", padding=10)
        notice.pack(fill=tk.X, pady=(0, 10))
        notice.columnconfigure(0, weight=1)
        ttk.Label(notice, text=build_notice_title(), font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        ttk.Label(notice, text=build_notice_text(), justify=tk.LEFT, wraplength=1320).grid(row=1, column=0, sticky=tk.W)

    def _add_entry(self, parent, label, variable, row, column, columnspan=1, width=30):
        """处理 _add_entry 对应的业务步骤，并向调用方返回所需结果。"""
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky=tk.W, pady=6)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=column + 1, columnspan=columnspan, sticky=tk.EW, pady=6)
        return entry

    def _bind_searchable_combobox(self, combobox, selected_callback=None):
        """处理 _bind_searchable_combobox 对应的业务步骤，并向调用方返回所需结果。"""
        if selected_callback:
            combobox.bind("<<ComboboxSelected>>", selected_callback)
        combobox.bind("<KeyRelease>", lambda event, widget=combobox: self._filter_combobox_values(widget, event))
        combobox.bind("<Return>", lambda event, widget=combobox, callback=selected_callback: self._accept_combobox_filter(widget, callback))

    def _set_combobox_values(self, combobox, values):
        """设置或应用 _set_combobox_values 对应的业务数据，保持现有调用约定。"""
        normalized_values = list(values or [])
        self._combobox_all_values[combobox] = normalized_values
        combobox["values"] = normalized_values

    def _filter_combobox_values(self, combobox, event=None):
        """处理 _filter_combobox_values 对应的业务步骤，并向调用方返回所需结果。"""
        if event and event.keysym in {"Return", "Escape", "Tab", "Up", "Down", "Left", "Right"}:
            return
        query = combobox.get().strip().lower()
        all_values = self._combobox_all_values.get(combobox, list(combobox["values"]))
        combobox["values"] = all_values if not query else [value for value in all_values if query in str(value).lower()]

    def _accept_combobox_filter(self, combobox, selected_callback=None):
        """处理 _accept_combobox_filter 对应的业务数据，保持现有调用约定。"""
        values = list(combobox["values"])
        current = combobox.get()
        all_values = self._combobox_all_values.get(combobox, values)
        if current not in all_values and values:
            combobox.set(values[0])
        if selected_callback:
            selected_callback()
        return "break"

    def choose_file(self):
        """处理 choose_file 对应的业务步骤，并向调用方返回所需结果。"""
        if self.input_mode.get() == "image":
            selected = filedialog.askopenfilenames(title="\u9009\u62e9\u56fe\u7247\u6587\u4ef6", filetypes=[("\u56fe\u7247\u6587\u4ef6", "*.png *.jpg *.jpeg"), ("\u6240\u6709\u6587\u4ef6", "*.*")])
            self._add_image_paths(selected)
            return
        else:
            selected = filedialog.askopenfilename(title="\u9009\u62e9\u65e5\u5fd7\u6587\u4ef6", filetypes=[("\u65e5\u5fd7\u6587\u4ef6", "*.log *.txt *.gz"), ("\u6240\u6709\u6587\u4ef6", "*.*")])
        if selected:
            self.file_path.set(selected)

    def _on_input_mode_changed(self):
        """处理 _on_input_mode_changed 对应的业务数据，保持现有调用约定。"""
        is_image_mode = self.input_mode.get() == "image"
        self.path_label_var.set("\u56fe\u7247\u6587\u4ef6" if is_image_mode else "\u65e5\u5fd7\u6587\u4ef6")
        self.choose_button_text.set("\u9009\u62e9\u56fe\u7247" if is_image_mode else "\u9009\u62e9\u6587\u4ef6")
        self.upload_button.configure(text="\u4e0a\u4f20\u56fe\u7247" if is_image_mode else "\u4e0a\u4f20\u65e5\u5fd7")
        self.date_combo.configure(state="disabled" if is_image_mode else "normal")
        if is_image_mode:
            self.image_tag_label.grid()
            self.image_tag_combo.grid()
            self.image_tag_help.grid()
            self.image_description_label.grid()
            self.image_description_text.grid()
            self.drop_hint.grid()
            self.image_list_frame.grid()
            self.paste_image_button.grid()
            self.clear_file_button.grid()
        else:
            self.image_tag_label.grid_remove()
            self.image_tag_combo.grid_remove()
            self.image_tag_help.grid_remove()
            self.image_description_label.grid_remove()
            self.image_description_text.grid_remove()
            self.drop_hint.grid_remove()
            self.image_list_frame.grid_remove()
            self.paste_image_button.grid_remove()
            self.clear_file_button.grid_remove()

    def _get_image_description(self):
        """读取并返回 _get_image_description 对应的业务数据，保持现有调用约定。"""
        return self.image_description_text.get("1.0", tk.END).strip()

    def clear_selected_input(self):
        """清理 clear_selected_input 对应的业务数据，保持现有调用约定。"""
        self.file_path.set("")
        self.image_paths = []
        self._refresh_image_list()
        self.image_description_text.delete("1.0", tk.END)

    def paste_image(self):
        """处理 paste_image 对应的业务步骤，并向调用方返回所需结果。"""
        if ImageGrab is None:
            raise ValueError("\u7f3a\u5c11 Pillow \u4f9d\u8d56\uff0c\u65e0\u6cd5\u4ece\u526a\u8d34\u677f\u8bfb\u53d6\u56fe\u7247")
        image = ImageGrab.grabclipboard()
        if image is None:
            raise ValueError("\u526a\u8d34\u677f\u4e2d\u6ca1\u6709\u56fe\u7247")
        if isinstance(image, list):
            selected = [str(Path(item)) for item in image if Path(item).suffix.lower() in {".png", ".jpg", ".jpeg"}]
            if not selected:
                raise ValueError("\u526a\u8d34\u677f\u4e2d\u6ca1\u6709\u53ef\u7528\u7684\u56fe\u7247\u6587\u4ef6")
            self._add_image_paths(selected)
            return
        temp_path = Path(tempfile.gettempdir()) / f"log-analyzer-paste-{int(time.time() * 1000)}.png"
        image.save(temp_path, format="PNG")
        self._pasted_image_path = str(temp_path)
        self._add_image_paths([str(temp_path)])

    def _add_image_paths(self, paths):
        """处理 _add_image_paths 对应的业务步骤，并向调用方返回所需结果。"""
        changed = False
        for path in paths or []:
            normalized = str(Path(path))
            if not normalized or Path(normalized).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            if normalized not in self.image_paths:
                self.image_paths.append(normalized)
                changed = True
        if changed:
            self._refresh_image_list()

    def _remove_image_path(self, path):
        """清理 _remove_image_path 对应的业务数据，保持现有调用约定。"""
        self.image_paths = [item for item in self.image_paths if item != path]
        self._refresh_image_list()

    def _refresh_image_list(self):
        """更新 _refresh_image_list 对应的业务数据，保持现有调用约定。"""
        for child in self.image_list_rows.winfo_children():
            child.destroy()
        if not self.image_paths:
            ttk.Label(self.image_list_rows, text="\u8fd8\u6ca1\u6709\u6682\u5b58\u56fe\u7247\uff0c\u53ef\u9009\u62e9\u3001\u7c98\u8d34\u6216\u62d6\u62fd\u591a\u5f20\u56fe\u7247").pack(anchor=tk.W)
            self.file_path.set("")
            return
        self.file_path.set(f"\u5df2\u6682\u5b58 {len(self.image_paths)} \u5f20\u56fe\u7247")
        for index, path in enumerate(self.image_paths, start=1):
            row = ttk.Frame(self.image_list_rows)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{index}. {Path(path).name}", width=52).pack(side=tk.LEFT)
            ttk.Button(row, text="\u5220\u9664", command=lambda item=path: self._remove_image_path(item)).pack(side=tk.LEFT, padx=8)

    def _install_drop_support(self):
        """注册或配置 _install_drop_support 对应的业务数据，保持现有调用约定。"""
        if windnd is None:
            return
        for widget in (self.drop_hint, self.log_file_entry):
            try:
                windnd.hook_dropfiles(widget, func=self._handle_drop_files)
            except Exception:
                pass

    def _handle_drop_files(self, files):
        """处理 _handle_drop_files 对应的业务数据，保持现有调用约定。"""
        image_paths = []
        for raw_value in files or []:
            value = raw_value.decode("gbk", errors="ignore") if isinstance(raw_value, bytes) else str(raw_value)
            path = value.strip().strip("{").strip("}")
            if not path:
                continue
            if self.input_mode.get() == "image":
                if Path(path).suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    image_paths.append(path)
                continue
            self.file_path.set(path)
            break
        if self.input_mode.get() == "image":
            self._add_image_paths(image_paths)

    def refresh_products_async(self):
        """更新 refresh_products_async 对应的业务数据，保持现有调用约定。"""
        self._run_background(self.refresh_products)

    def sync_git_projects_async(self):
        """更新 sync_git_projects_async 对应的业务数据，保持现有调用约定。"""
        self._run_background(self.sync_git_projects)

    def sync_git_projects(self):
        """更新 sync_git_projects 对应的业务数据，保持现有调用约定。"""
        self._set_status("\u6b63\u5728\u540c\u6b65 Git \u9879\u76ee...")
        result = self._client().sync_git_projects()
        self._write_result("Git \u540c\u6b65\u7ed3\u679c", result)
        self._set_status(f"Git \u9879\u76ee\u540c\u6b65\u5b8c\u6210\uff0c\u5df2\u540c\u6b65 {result.get('synced_projects', 0)} \u4e2a\u4ed3\u5e93")
        self.refresh_products()

    def refresh_products(self):
        """更新 refresh_products 对应的业务数据，保持现有调用约定。"""
        self._set_status("\u6b63\u5728\u52a0\u8f7d\u4ea7\u54c1...")
        products = self._client().get_products()

        def update():
            """更新 update 对应的业务数据，保持现有调用约定。"""
            self.products = products
            self.product_by_label = {self._product_label(product): product for product in products}
            values = list(self.product_by_label.keys())
            self._set_combobox_values(self.product_combo, values)
            self.product_selection.set(values[0] if values else "")
            self._clear_module_branch_selection()
            self.status.set("\u4ea7\u54c1\u52a0\u8f7d\u5b8c\u6210" if values else "\u6682\u65e0\u4ea7\u54c1")
            if values:
                self.on_product_selected()

        self.root.after(0, update)

    def on_product_selected(self, event=None):
        """处理 on_product_selected 对应的业务数据，保持现有调用约定。"""
        product = self.product_by_label.get(self.product_selection.get())
        if not product:
            self.product_id.set("")
            self._clear_module_branch_selection()
            return
        self.product_id.set(str(product.get("id", "")))
        self._run_background(self.load_modules_for_selected_product)

    def load_modules_for_selected_product(self):
        """读取并返回 load_modules_for_selected_product 对应的业务数据，保持现有调用约定。"""
        product_id = self.product_id.get()
        if not product_id:
            return
        self._set_status("\u6b63\u5728\u52a0\u8f7d\u6a21\u5757/\u4ed3\u5e93...")
        modules = self._client().get_modules_by_product(product_id)

        def update():
            """更新 update 对应的业务数据，保持现有调用约定。"""
            self.modules = modules
            self.all_modules_loaded = False
            self.module_by_label = {self._module_label(module): module for module in modules}
            self.branch_versions = self._build_branch_versions(modules)
            module_values = list(self.module_by_label.keys())
            branch_values = list(self.branch_versions.keys())
            self._set_combobox_values(self.module_combo, module_values)
            self._set_combobox_values(self.branch_combo, branch_values)
            self.module_selection.set(module_values[0] if module_values else "")
            self.branch_address.set(branch_values[0] if branch_values else "")
            self._sync_versions_for_branch()
            self.status.set("\u6a21\u5757\u52a0\u8f7d\u5b8c\u6210" if modules else "\u6682\u65e0\u6a21\u5757\u6570\u636e")
            if module_values:
                self.on_module_selected()

        self.root.after(0, update)

    def on_module_selected(self, event=None):
        """处理 on_module_selected 对应的业务数据，保持现有调用约定。"""
        module = self.module_by_label.get(self.module_selection.get())
        if not module:
            self.module_id.set("")
            return
        self.module_id.set(str(module.get("module_id", "")))
        branch_address, tag_version = _module_branch_info(module)
        if branch_address:
            self.branch_address.set(branch_address)
            self._sync_versions_for_branch()
        available_versions = self.branch_versions.get(branch_address, [])
        if tag_version and (not available_versions or tag_version in available_versions):
            self.tag_version.set(tag_version)
        if self._should_auto_refresh_versions(branch_address):
            self.load_remote_branches_for_selected_repo_async()

    def on_branch_selected(self, event=None):
        """处理 on_branch_selected 对应的业务数据，保持现有调用约定。"""
        self._sync_versions_for_branch()
        if self._should_auto_refresh_versions(self.branch_address.get()):
            self.load_remote_branches_for_selected_repo_async()

    def _has_cached_versions_for_branch(self, branch_address):
        """判断 _has_cached_versions_for_branch 对应的业务数据，保持现有调用约定。"""
        return bool(branch_address and self.branch_versions.get(branch_address))

    def _should_auto_refresh_versions(self, branch_address):
        """判断 _should_auto_refresh_versions 对应的业务数据，保持现有调用约定。"""
        if not branch_address:
            return False
        versions = self.branch_versions.get(branch_address, [])
        return not versions or (len(versions) <= 1 and branch_address not in self.version_refresh_attempted)

    def refresh_branch_versions_async(self):
        """更新 refresh_branch_versions_async 对应的业务数据，保持现有调用约定。"""
        self.load_remote_branches_for_selected_repo_async(force_refresh=True)

    def load_remote_branches_for_selected_repo_async(self, force_refresh=False):
        """读取并返回 load_remote_branches_for_selected_repo_async 对应的业务数据，保持现有调用约定。"""
        self._run_background(lambda: self.load_remote_branches_for_selected_repo(force_refresh=force_refresh))

    def load_remote_branches_for_selected_repo(self, force_refresh=False):
        """读取并返回 load_remote_branches_for_selected_repo 对应的业务数据，保持现有调用约定。"""
        repo_url = self.branch_address.get().strip()
        if not repo_url:
            return
        self._set_status("\u6b63\u5728\u62c9\u53d6 Git \u5206\u652f/Tag...")
        branches = self._client().get_remote_branches(repo_url, force_refresh=force_refresh)
        self.version_refresh_attempted.add(repo_url)

        def update():
            """更新 update 对应的业务数据，保持现有调用约定。"""
            self.branch_versions[repo_url] = branches
            self._set_combobox_values(self.tag_combo, branches)
            self.tag_version.set(branches[0] if branches else "")
            self.status.set("\u7248\u672c/Tag \u5df2\u5237\u65b0" if branches else "\u672a\u83b7\u53d6\u5230\u53ef\u7528\u7248\u672c/Tag")

        self.root.after(0, update)

    def _sync_versions_for_branch(self):
        """更新 _sync_versions_for_branch 对应的业务数据，保持现有调用约定。"""
        versions = self.branch_versions.get(self.branch_address.get(), [])
        self._set_combobox_values(self.tag_combo, versions)
        if versions and self.tag_version.get() not in versions:
            self.tag_version.set(versions[0])
        elif not versions:
            self.tag_version.set("")

    def _clear_module_branch_selection(self):
        """清理 _clear_module_branch_selection 对应的业务数据，保持现有调用约定。"""
        self.modules = []
        self.module_by_label = {}
        self.branch_versions = {}
        self.version_refresh_attempted = set()
        self._set_combobox_values(self.module_combo, [])
        self._set_combobox_values(self.branch_combo, [])
        self._set_combobox_values(self.tag_combo, [])
        self.module_selection.set("")
        self.module_id.set("")
        self.branch_address.set("")
        self.tag_version.set("")

    def _build_branch_versions(self, modules):
        """构建并返回 _build_branch_versions 对应的业务数据，保持现有调用约定。"""
        branch_versions = {}
        for module in modules:
            address, version = _module_branch_info(module)
            if not address:
                continue
            branch_versions.setdefault(address, [])
            if version and version not in branch_versions[address]:
                branch_versions[address].append(version)
        return branch_versions

    def _merge_branch_versions(self, modules):
        """合并整理并返回 _merge_branch_versions 对应的业务数据，保持现有调用约定。"""
        for address, versions in self._build_branch_versions(modules).items():
            current_versions = self.branch_versions.setdefault(address, [])
            for version in versions:
                if version and version not in current_versions:
                    current_versions.append(version)

    def _get_related_match_modules(self, client, related_suggestions=None):
        """读取并返回 _get_related_match_modules 对应的业务数据，保持现有调用约定。"""
        modules_by_key = {}
        for module in self.modules or []:
            address, version = _module_branch_info(module)
            key = (str(module.get("module_id") or module.get("moduleId") or module.get("module_name") or module.get("moduleName") or ""), address, version)
            modules_by_key.setdefault(key, module)

        lookup_names = []
        seen_names = set()
        for related in related_suggestions or []:
            module_name = str(related.get("moduleName") or related.get("module_name") or "").strip()
            if not module_name or _is_ignored_missing_module_name(module_name):
                continue
            normalized = module_name.lower()
            if normalized in seen_names:
                continue
            seen_names.add(normalized)
            lookup_names.append(module_name)

        if lookup_names:
            try:
                searched_modules = client.search_modules_by_names(lookup_names)
            except Exception:
                searched_modules = []
            for module in searched_modules or []:
                address, version = _module_branch_info(module)
                key = (str(module.get("module_id") or module.get("moduleId") or module.get("module_name") or module.get("moduleName") or ""), address, version)
                modules_by_key.setdefault(key, module)

        match_modules = list(modules_by_key.values())
        self._merge_branch_versions(match_modules)
        return match_modules

    def _product_label(self, product):
        """处理 _product_label 对应的业务步骤，并向调用方返回所需结果。"""
        return f"{product.get('id')} - {product.get('name', '')}"

    def _module_label(self, module):
        """处理 _module_label 对应的业务步骤，并向调用方返回所需结果。"""
        return f"{module.get('module_id')} - {module.get('module_name', '')}"

    def _current_module_name(self):
        """处理 _current_module_name 对应的业务步骤，并向调用方返回所需结果。"""
        module = self.module_by_label.get(self.module_selection.get()) if hasattr(self, "module_by_label") else None
        if module:
            return str(module.get("module_name") or module.get("moduleName") or module.get("name") or "")
        return ""

    def upload_async(self):
        """上传 upload_async 对应的业务数据，保持现有调用约定。"""
        self._run_background(self.upload, cancellable=True)

    def analyze_async(self):
        """执行故障分析并返回 analyze_async 对应的业务数据，保持现有调用约定。"""
        self._run_background(self.analyze, cancellable=True, analysis_action=True)

    def upload_and_analyze_async(self):
        """上传 upload_and_analyze_async 对应的业务数据，保持现有调用约定。"""
        self._run_background(self.upload_and_analyze, cancellable=True, analysis_action=True)

    def analyze_or_cancel(self):
        """执行故障分析并返回 analyze_or_cancel 对应的业务数据，保持现有调用约定。"""
        if self.analysis_running:
            self.cancel_current_operation()
            return
        self.analyze_async()

    def upload(self):
        """上传 upload 对应的业务数据，保持现有调用约定。"""
        self._validate_common_fields(require_file=True)
        self._raise_if_cancelled()
        is_image_mode = self.input_mode.get() == "image"
        self._set_progress(0, "\u4e0a\u4f20\u56fe\u7247 0%" if is_image_mode else "\u4e0a\u4f20\u65e5\u5fd7 0%")
        self._set_status("\u6b63\u5728\u4e0a\u4f20\u56fe\u7247..." if is_image_mode else "\u6b63\u5728\u4e0a\u4f20\u65e5\u5fd7...")
        self.progress_animation_target = 18
        self.progress_animation_job = self.root.after(250, self._animate_upload_tick)
        client = self._client()
        if is_image_mode:
            self.upload_result = client.upload_images(self.image_paths, self.product_id.get(), self.module_id.get(), self.branch_address.get(), self.tag_version.get(), self.image_tag.get(), self._get_image_description())
        else:
            self.upload_result = client.upload_log(self.file_path.get(), self.product_id.get(), self.module_id.get(), self.branch_address.get(), self.tag_version.get(), self.date_filter.get().strip())
        self._raise_if_cancelled()
        self._stop_progress_animation()
        self._write_result("\u4e0a\u4f20\u7ed3\u679c", self.upload_result)
        self._set_progress(20, "\u4e0a\u4f20\u56fe\u7247 100%\uff0c\u7b49\u5f85\u5206\u6790" if is_image_mode else "\u4e0a\u4f20\u65e5\u5fd7 100%\uff0c\u7b49\u5f85\u5206\u6790")
        self._set_status("\u4e0a\u4f20\u5b8c\u6210")

    def analyze(self):
        """执行故障分析并返回 analyze 对应的业务数据，保持现有调用约定。"""
        self._validate_common_fields(require_file=False)
        self._raise_if_cancelled()
        if not self.upload_result or not self.upload_result.get("file_path"):
            raise ValueError("\u8bf7\u5148\u5b8c\u6210\u4e0a\u4f20")
        client = self._client()
        current_percent = int(self.progress_percent.get() or 0)
        start_percent = 21 if current_percent >= 100 else max(1, current_percent)
        self._set_progress(start_percent, "\u6b63\u5728\u63d0\u4ea4\u5206\u6790\u4efb\u52a1...")
        self._start_progress_animation(24)
        self._set_status("\u6b63\u5728\u63d0\u4ea4\u5206\u6790\u4efb\u52a1...")
        related_modules, related_evidence, skipped_chain_issues = self._assess_chain_code_and_upload_evidence(client)
        self._raise_if_cancelled()
        task_result = client.submit_analysis_task(self.product_id.get(), self.module_id.get(), self.branch_address.get(), self.tag_version.get(), self.upload_result["file_path"], self.upload_result.get("log_id"), source_type=self.upload_result.get("source_type", self.input_mode.get()), image_tag=self.upload_result.get("image_tag", ""), image_description=self.upload_result.get("image_description", self._get_image_description()), file_paths=self.upload_result.get("file_paths"), log_ids=self.upload_result.get("log_ids"), related_modules=related_modules, related_evidence=related_evidence, skipped_chain_issues=skipped_chain_issues, image_ocr=self.upload_result.get("image_ocr"))
        self.task_id = task_result.get("task_id")
        if not self.task_id:
            raise ValueError("\u670d\u52a1\u7aef\u672a\u8fd4\u56de task_id")
        self._write_result("\u4efb\u52a1\u63d0\u4ea4\u7ed3\u679c", task_result)
        self._set_progress(22, "\u5206\u6790\u4efb\u52a1\u5df2\u521b\u5efa")
        self._start_progress_animation(35)

        analysis_result = self._poll_analysis_task(client, self.task_id)
        self._write_analysis_summary(analysis_result)
        self._show_analysis_result(analysis_result)
        self._stop_progress_animation()
        self._set_progress(100, "\u5206\u6790\u5b8c\u6210 100%")
        self._set_status("\u4e0a\u4f20\u5b8c\u6210")

    def _assess_chain_code_and_upload_evidence(self, client):
        """执行故障分析并返回 _assess_chain_code_and_upload_evidence 对应的业务数据，保持现有调用约定。"""
        self._set_status("\u6b63\u5728\u5224\u65ad\u662f\u5426\u6d89\u53ca\u4e0a\u4e0b\u6e38\u94fe\u8def...")
        self._set_progress(max(22, int(self.progress_percent.get() or 0)), "\u6b63\u5728\u5224\u65ad\u662f\u5426\u6d89\u53ca\u4e0a\u4e0b\u6e38\u94fe\u8def...")
        discovery = client.discover_related_modules(
            self.product_id.get(),
            self.module_id.get(),
            self.branch_address.get(),
            self.tag_version.get(),
            self.upload_result["file_path"],
            source_type=self.upload_result.get("source_type", self.input_mode.get()),
            image_tag=self.upload_result.get("image_tag", ""),
            image_description=self.upload_result.get("image_description", self._get_image_description()),
            file_paths=self.upload_result.get("file_paths"),
        )
        if isinstance(discovery.get("imageOcr"), dict):
            self.upload_result["image_ocr"] = dict(discovery["imageOcr"])
        if discovery.get("status") == "image_ocr_unavailable":
            message = discovery.get("message") or "图片识别模型未返回可用结果，无法在分析前判断上下游链路；将保留原图进入综合分析。"
            self._set_status(message)
            self._show_info_message_async("图片识别不可用", message)
            return [], [], []
        if not discovery.get("requiresRelatedEvidence"):
            self._set_status(discovery.get("message") or "\u6b64\u95ee\u9898\u4e0d\u6d89\u53ca\u4e0a\u4e0b\u6e38\u94fe\u8def\u5224\u65ad\uff0c\u5f00\u59cb\u5206\u6790\u6545\u969c\u539f\u56e0")
            return [], [], []

        issue_candidates = discovery.get("issueCandidates") or [{
            "index": 0,
            "issueSummary": discovery.get("issueSummary"),
            "matchedSignals": discovery.get("matchedSignals", []),
            "relatedModules": discovery.get("relatedModules", []),
            "reason": discovery.get("reason"),
        }]
        related_suggestions = []
        seen_suggestions = set()
        issue_summary_lines = []
        for candidate_index, candidate in enumerate(issue_candidates, start=1):
            self._raise_if_cancelled()
            summary = candidate.get("issueSummary") or candidate.get("reason") or ""
            if summary:
                issue_summary_lines.append(f"{candidate_index}. {summary}")
            for related in candidate.get("relatedModules") or []:
                key = _suggested_module_key(related) or str(related.get("moduleName") or related.get("moduleId") or "")
                if not key or key in seen_suggestions:
                    continue
                seen_suggestions.add(key)
                related_suggestions.append(related)

        if not related_suggestions:
            related_suggestions = discovery.get("relatedModules", [])

        match_modules = self._get_related_match_modules(client, related_suggestions)
        candidates = build_related_code_module_candidates(
            match_modules,
            self.module_id.get(),
            self.branch_versions,
            related_suggestions,
            primary_branch_address=self.branch_address.get(),
            primary_module_name=self._current_module_name(),
        )
        self._load_cached_related_candidate_versions(client, candidates)
        unavailable_modules = [
            candidate for candidate in candidates
            if candidate.get("autoSelect") and not candidate.get("repositoryAvailable", True)
        ]
        candidate_decision = dict(discovery)
        candidate_decision["message"] = f"已识别到 {len(issue_candidates)} 段可能涉及上下游的链路错误，请一次性选择需要参与组合分析的模块版本。"
        candidate_decision.pop("issueSummary", None)

        selected_modules = self._show_related_code_version_dialog(candidates, candidate_decision, client)
        if selected_modules is None:
            raise OperationCancelled("已取消上下游模块版本选择")

        skipped_chain_issues = []
        if unavailable_modules:
            skipped_chain_issues.append({
                "index": "unavailable_related_modules",
                "issueSummary": "部分上下游模块未匹配到可用仓库/版本",
                "reason": "以下模块仓库不存在、未配置或当前账号无权限，仅作为链路线索参与分析，不拉取代码。",
                "relatedModules": [{
                    "moduleId": module.get("moduleId"),
                    "moduleName": module.get("moduleName"),
                    "role": module.get("role"),
                    "reason": module.get("repositoryMessage") or module.get("reason"),
                } for module in unavailable_modules],
            })
        if not selected_modules:
            for candidate_index, candidate in enumerate(issue_candidates, start=1):
                skipped_chain_issues.append({
                    "index": candidate.get("index", candidate_index - 1),
                    "issueSummary": candidate.get("issueSummary"),
                    "reason": "用户选择不补充上下游版本代码，此异常仍会随当前日志/图片一起参与分析。",
                    "relatedModules": candidate.get("relatedModules", []),
                })
            self._set_status("未选择上下游代码，开始使用当前日志/图片分析")
            return [], [], skipped_chain_issues

        self._show_info_message_async('上下游信息已获取', '异常信息已经全部获取到，开始自动拉代码做组合分析。')
        self._set_status('异常信息已经全部获取到，开始自动拉代码做组合分析')
        return dedupe_related_modules(selected_modules), [], skipped_chain_issues

    def _load_cached_related_candidate_versions(self, client, candidates):
        """读取并返回 _load_cached_related_candidate_versions 对应的业务数据，保持现有调用约定。"""
        targets = []
        for candidate in candidates or []:
            if not candidate.get("repositoryAvailable", True):
                continue
            repo_url = str(candidate.get("branchAddress") or "").strip()
            if repo_url:
                targets.append((candidate, repo_url))
        if not targets:
            return

        worker_count = min(4, len(targets))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(client.get_cached_branches, repo_url): (candidate, repo_url)
                for candidate, repo_url in targets
            }
            for future in as_completed(future_map):
                candidate, repo_url = future_map[future]
                try:
                    cached_versions = future.result() or []
                except Exception:
                    continue
                merged_versions = []
                default_version = candidate.get("tagVersion") or ""
                if default_version:
                    merged_versions.append(default_version)
                for version in cached_versions:
                    if version and version not in merged_versions:
                        merged_versions.append(version)
                if not merged_versions:
                    continue
                self.branch_versions[repo_url] = merged_versions
                candidate["versions"] = merged_versions
                candidate["versionsFromCache"] = bool(cached_versions)


    def _show_info_message_async(self, title, message):
        """处理 _show_info_message_async 对应的业务步骤，并向调用方返回所需结果。"""
        if isinstance(getattr(self, "root", None), tk.Misc):
            self.root.after(0, lambda: messagebox.showinfo(title, message))
    def _refresh_related_candidate_versions(self, client, candidates):
        """更新 _refresh_related_candidate_versions 对应的业务数据，保持现有调用约定。"""
        for candidate in candidates or []:
            self._raise_if_cancelled()
            if not candidate.get("repositoryAvailable", True):
                continue
            repo_url = str(candidate.get("branchAddress") or "").strip()
            if not repo_url:
                continue
            cached_versions = list(self.branch_versions.get(repo_url, []))
            default_version = candidate.get("tagVersion") or ""
            if cached_versions and len(cached_versions) > 1:
                continue
            try:
                remote_versions = client.get_remote_branches(repo_url)
            except Exception:
                continue
            if not remote_versions:
                continue
            merged_versions = []
            if default_version:
                merged_versions.append(default_version)
            for version in remote_versions:
                if version and version not in merged_versions:
                    merged_versions.append(version)
            self.branch_versions[repo_url] = merged_versions

    def _show_related_code_version_dialog(self, candidates, decision, client):
        """处理 _show_related_code_version_dialog 对应的业务步骤，并向调用方返回所需结果。"""
        result_holder = {}
        ready = threading.Event()

        def open_dialog():
            """处理 open_dialog 对应的业务步骤，并向调用方返回所需结果。"""
            try:
                dialog = RelatedCodeVersionDialog(
                    self.root,
                    candidates,
                    decision,
                    version_loader=lambda repo_url: client.get_remote_branches(repo_url, force_refresh=True),
                )
                result_holder["result"] = dialog.show()
            finally:
                ready.set()

        self.root.after(0, open_dialog)
        while not ready.wait(0.1):
            self._raise_if_cancelled()
        return result_holder.get("result")

    def _show_related_evidence_dialog(self, decision):
        """处理 _show_related_evidence_dialog 对应的业务步骤，并向调用方返回所需结果。"""
        result_holder = {}
        ready = threading.Event()

        def open_dialog():
            """处理 open_dialog 对应的业务步骤，并向调用方返回所需结果。"""
            try:
                dialog = RelatedEvidenceDialog(self.root, decision)
                result_holder["result"] = dialog.show()
            finally:
                ready.set()

        self.root.after(0, open_dialog)
        while not ready.wait(0.1):
            self._raise_if_cancelled()
        return result_holder.get("result")

    def _upload_related_evidence(self, client, selected_items):
        """上传 _upload_related_evidence 对应的业务数据，保持现有调用约定。"""
        uploaded = []
        for item in selected_items:
            self._raise_if_cancelled()
            path = item.get("path")
            source_type = item.get("source_type")
            if source_type == "image":
                result = client.upload_images(
                    [path],
                    self.product_id.get(),
                    self.module_id.get(),
                    self.branch_address.get(),
                    self.tag_version.get(),
                    "related_image",
                    item.get("label", ""),
                )
                uploaded.append({
                    "label": item.get("label"),
                    "source_type": "image",
                    "image_tag": "related_image",
                    "description": item.get("label", ""),
                    "file_paths": result.get("file_paths") or ([result.get("file_path")] if result.get("file_path") else []),
                    "log_ids": result.get("log_ids"),
                })
            else:
                result = client.upload_log(
                    path,
                    self.product_id.get(),
                    self.module_id.get(),
                    self.branch_address.get(),
                    self.tag_version.get(),
                    self.date_filter.get().strip(),
                )
                uploaded.append({
                    "label": item.get("label"),
                    "source_type": "file",
                    "file_path": result.get("file_path"),
                    "log_id": result.get("log_id"),
                })
        return uploaded

    def upload_and_analyze(self):
        """上传 upload_and_analyze 对应的业务数据，保持现有调用约定。"""
        self.upload()
        self.analyze()

    def _poll_analysis_task(self, client, task_id):
        """轮询或等待 _poll_analysis_task 对应的业务数据，保持现有调用约定。"""
        return poll_task_until_ready(client, task_id, on_status=self._set_status, on_progress=self._handle_task_progress, should_cancel=lambda: self.cancel_requested)

    def _client(self):
        """处理 _client 对应的业务步骤，并向调用方返回所需结果。"""
        if self.api_client is not None:
            self.api_client.set_base_url(self.backend_url.get())
            return self.api_client
        return LogAnalyzerApiClient(self.backend_url.get())

    def _validate_common_fields(self, require_file):
        """校验 _validate_common_fields 对应的业务数据，保持现有调用约定。"""
        fields = [("\u540e\u7aef\u5730\u5740", self.backend_url.get()), ("\u4ea7\u54c1 ID", self.product_id.get()), ("\u6a21\u5757 ID", self.module_id.get()), ("\u5206\u652f\u5730\u5740", self.branch_address.get()), ("\u7248\u672c/Tag", self.tag_version.get())]
        if require_file:
            if self.input_mode.get() == "image":
                fields.append((self.path_label_var.get(), ",".join(self.image_paths)))
            else:
                fields.append((self.path_label_var.get(), self.file_path.get()))
        missing = [label for label, value in fields if not value.strip()]
        if missing:
            raise ValueError("\u4ee5\u4e0b\u5b57\u6bb5\u4e0d\u80fd\u4e3a\u7a7a\uff1a" + "\u3001".join(missing))

    def _run_background(self, action, cancellable=False, analysis_action=False):
        """执行 _run_background 对应的业务数据，保持现有调用约定。"""
        if cancellable:
            self.cancel_requested = False
            self._set_cancel_enabled(True)
        if analysis_action:
            self._set_analysis_running(True)
        threading.Thread(target=self._run_action, args=(action, cancellable, analysis_action), daemon=True).start()

    def _run_action(self, action, cancellable=False, analysis_action=False):
        """执行 _run_action 对应的业务数据，保持现有调用约定。"""
        try:
            action()
        except OperationCancelled as exc:
            self.last_failed_action = None
            self._set_retry_enabled(False)
            self._set_status(str(exc) or "\u64cd\u4f5c\u5df2\u53d6\u6d88")
        except Exception as exc:
            self.last_failed_action = action
            self._set_retry_enabled(True)
            error_message = format_exception_message(exc)
            self._set_status(f"\u64cd\u4f5c\u5931\u8d25\uff1a{error_message}")
            self.root.after(0, lambda: messagebox.showerror("\u9519\u8bef", error_message))
        else:
            self.last_failed_action = None
            self._set_retry_enabled(False)
        finally:
            if cancellable:
                self._set_cancel_enabled(False)
            if analysis_action:
                self._set_analysis_running(False)

    def retry_last_failed_action(self):
        """处理 retry_last_failed_action 对应的业务步骤，并向调用方返回所需结果。"""
        if self.last_failed_action:
            self._run_background(self.last_failed_action)

    def _set_retry_enabled(self, enabled):
        """设置或应用 _set_retry_enabled 对应的业务数据，保持现有调用约定。"""
        if self.retry_button is None:
            return
        state = tk.NORMAL if enabled else tk.DISABLED
        self.root.after(0, lambda: self.retry_button.configure(state=state))

    def _set_cancel_enabled(self, enabled):
        """设置或应用 _set_cancel_enabled 对应的业务数据，保持现有调用约定。"""
        return

    def _set_analysis_running(self, running):
        """设置或应用 _set_analysis_running 对应的业务数据，保持现有调用约定。"""
        self.analysis_running = running
        text = "\u4e2d\u65ad\u5206\u6790" if running else "\u5f00\u59cb\u5206\u6790"
        if not running:
            self._stop_progress_animation()
        self.root.after(0, lambda: self.analyze_button.configure(text=text))

    def _set_status(self, text):
        """设置或应用 _set_status 对应的业务数据，保持现有调用约定。"""
        try:
            self.root.after(0, lambda: self.status.set(text))
        except RuntimeError:
            pass

    def _set_progress(self, percent, message):
        """设置或应用 _set_progress 对应的业务数据，保持现有调用约定。"""
        safe_percent = max(0, min(100, int(percent)))
        try:
            self.root.after(0, lambda: (self.progress_percent.set(safe_percent), self.progress_text.set(message)))
        except RuntimeError:
            pass

    def _handle_task_progress(self, progress):
        """处理 _handle_task_progress 对应的业务数据，保持现有调用约定。"""
        percent = progress.get("percent", self.progress_percent.get())
        default_stage_label = "\u5904\u7406\u4e2d"
        stage_label = progress.get("stage_label", default_stage_label)
        stage_percent = progress.get("stage_percent", percent)
        message = progress.get("message") or f"{stage_label} {stage_percent}%"
        message = repair_mojibake_text(message)
        if progress.get("stage") == "read_image_started":
            message = "图片模型首次加载时间较长，请耐心等待；后续分析会复用已加载模型"
        elif progress.get("stage") in ("analyze_code_started", "deep_reasoning_started"):
            message = "正在使用 gpt-5.6-sol 进行深度故障推理，请耐心等待；复杂问题可能需要更长时间"
        message = format_progress_message_for_percent(message, percent)
        self._set_progress(percent, message)
        if int(percent or 0) >= 100:
            self._stop_progress_animation()
        else:
            self._start_progress_animation(get_smooth_progress_limit(progress))

    def _start_progress_animation(self, target):
        """执行 _start_progress_animation 对应的业务数据，保持现有调用约定。"""
        self.progress_animation_target = max(0, min(99, int(target)))
        if self.progress_animation_job is None:
            self.progress_animation_job = self.root.after(700, self._animate_progress_tick)

    def _stop_progress_animation(self):
        """执行 _stop_progress_animation 对应的业务数据，保持现有调用约定。"""
        job = self.progress_animation_job
        self.progress_animation_job = None
        self.progress_animation_target = 0
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

    def _animate_progress_tick(self):
        """处理 _animate_progress_tick 对应的业务步骤，并向调用方返回所需结果。"""
        self.progress_animation_job = None
        if not self.analysis_running or self.cancel_requested:
            return
        current = int(self.progress_percent.get() or 0)
        next_percent = next_smooth_progress(current, self.progress_animation_target)
        if next_percent > current:
            self._set_progress(next_percent, format_progress_message_for_percent(self.progress_text.get(), next_percent))
        if next_percent < self.progress_animation_target:
            self.progress_animation_job = self.root.after(700, self._animate_progress_tick)

    def _animate_upload_tick(self):
        """处理 _animate_upload_tick 对应的业务步骤，并向调用方返回所需结果。"""
        self.progress_animation_job = None
        if self.cancel_requested:
            return
        current = int(self.progress_percent.get() or 0)
        next_percent = next_smooth_progress(current, self.progress_animation_target)
        if next_percent > current:
            self._set_progress(next_percent, format_progress_message_for_percent(self.progress_text.get(), next_percent))
        if next_percent < self.progress_animation_target:
            self.progress_animation_job = self.root.after(250, self._animate_upload_tick)

    def _raise_if_cancelled(self):
        """处理 _raise_if_cancelled 对应的业务步骤，并向调用方返回所需结果。"""
        if self.cancel_requested:
            raise OperationCancelled("\u64cd\u4f5c\u5df2\u4e2d\u65ad")

    def cancel_current_operation(self):
        """取消 cancel_current_operation 对应的业务数据，保持现有调用约定。"""
        self.cancel_requested = True
        self._set_status("\u6b63\u5728\u8bf7\u6c42\u4e2d\u65ad\u5f53\u524d\u4efb\u52a1...")
        self._set_progress(self.progress_percent.get(), "\u6b63\u5728\u4e2d\u65ad")
        if not self.task_id:
            return

        task_id = self.task_id

        def cancel_remote():
            """取消 cancel_remote 对应的业务数据，保持现有调用约定。"""
            try:
                result = self._client().cancel_task(task_id)
                self._write_result("\u4e2d\u65ad\u7ed3\u679c", result)
            except Exception as exc:
                self._set_status(f"\u4e2d\u65ad\u8bf7\u6c42\u5931\u8d25\uff1a{format_exception_message(exc)}")

        threading.Thread(target=cancel_remote, daemon=True).start()

    def _on_root_destroy(self, event=None):
        """处理 _on_root_destroy 对应的业务数据，保持现有调用约定。"""
        if event is None or event.widget is self.root:
            self._stop_progress_animation()

    def _on_close(self):
        """处理 _on_close 对应的业务数据，保持现有调用约定。"""
        self._stop_progress_animation()
        try:
            if self.api_client is not None:
                self.api_client.logout()
        except requests.RequestException:
            pass
        finally:
            self.root.destroy()

    def _write_analysis_summary(self, payload):
        """保存 _write_analysis_summary 对应的业务数据，保持现有调用约定。"""
        summary = build_analysis_summary(payload)
        self.root.after(0, lambda: (self.result_text.insert(tk.END, summary), self.result_text.see(tk.END)))

    def _show_analysis_result(self, payload):
        """处理 _show_analysis_result 对应的业务步骤，并向调用方返回所需结果。"""
        self.root.after(0, lambda: AnalysisResultWindow(self.root, payload))

    def _write_result(self, title, payload):
        """保存 _write_result 对应的业务数据，保持现有调用约定。"""
        formatted = format_result_payload(title, payload)
        self.root.after(0, lambda: (self.result_text.insert(tk.END, formatted), self.result_text.see(tk.END)))


class ClientApplication:
    """ClientApplication 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, root):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        self.root = root
        self.main_window = None
        self.login_window = None
        self.client = LogAnalyzerApiClient(
            DEFAULT_BACKEND_URL,
            on_unauthorized=self._handle_unauthorized,
        )
        self.show_login()

    def show_login(self):
        """处理 show_login 对应的业务步骤，并向调用方返回所需结果。"""
        if self.login_window is not None and self.login_window.exists():
            return
        self.root.withdraw()
        self.login_window = LoginWindow(
            self.root,
            self.client,
            on_success=self._login_succeeded,
            on_cancel=self.root.destroy,
        )

    def _login_succeeded(self, _username):
        """处理 _login_succeeded 对应的业务步骤，并向调用方返回所需结果。"""
        self.login_window = None
        if self.main_window is None:
            self.main_window = LogAnalyzerWindow(self.root, api_client=self.client)
        else:
            self.root.deiconify()

    def _handle_unauthorized(self):
        """处理 _handle_unauthorized 对应的业务数据，保持现有调用约定。"""
        self.root.after(0, self.show_login)


def main():
    """执行 main 对应的业务数据，保持现有调用约定。"""
    root = tk.Tk()
    ClientApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()
