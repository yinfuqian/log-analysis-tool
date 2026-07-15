
import json
import re
import sys
import threading
import time
import tempfile
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
    from client_build_info import APP_RELEASE_DATE, APP_VERSION
except ImportError:  # pragma: no cover - keeps source runnable before first build metadata generation
    APP_VERSION = "v1.0.0"
    APP_RELEASE_DATE = "2026-06-24"

from api_client import ApiClient
from login_window import LoginWindow

APP_RELEASE_LABEL = f"\u65e5\u5fd7\u5206\u6790\u5ba2\u6237\u7aef/{APP_VERSION} fix on {APP_RELEASE_DATE}"
DEFAULT_BACKEND_URL = "http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi"
DRAG_DROP_ENABLED = windnd is not None
UNKNOWN_FILE_LABEL = "\u672a\u77e5\u6587\u4ef6"
NOTICE_CONFIG_FILENAME = "notice_config.json"


def _resource_path(filename):
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
    """Raised when the user asks the client to stop the current operation."""


def format_exception_message(exc):
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
    return {
        "app_version": APP_VERSION,
        "app_release_date": APP_RELEASE_DATE,
        "app_release_label": APP_RELEASE_LABEL,
        "backend_url": DEFAULT_BACKEND_URL,
    }


def _format_notice_template(value):
    try:
        return str(value).format(**_notice_format_values())
    except (KeyError, ValueError):
        return str(value)


def load_notice_config():
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
    config = load_notice_config()
    return _format_notice_template(config.get("title") or DEFAULT_NOTICE_CONFIG["title"])


def build_notice_text():
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
    percent = int(progress.get("percent", 0) or 0)
    stage = progress.get("stage")
    return max(percent, SMOOTH_PROGRESS_STAGE_LIMITS.get(stage, min(percent + 8, 98)))


def next_smooth_progress(current, target):
    current = int(current or 0)
    target = int(target or 0)
    if current >= target:
        return current
    return min(target, current + 1)


def format_progress_message_for_percent(message, percent):
    text = str(message or "")
    safe_percent = max(0, min(100, int(percent or 0)))
    if re.search(r"\d+%\s*$", text):
        return re.sub(r"\d+%\s*$", f"{safe_percent}%", text)
    return f"{text} {safe_percent}%".strip()


def format_result_payload(title, payload):
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
    return any(key in payload for key in ("log_analysis", "code_analysis", "code_snippets"))


def _is_upload_payload(payload):
    return "file_path" in payload and any(
        key in payload
        for key in ("original_line_count", "filtered_line_count", "target_date", "source_type", "image_tag")
    )


def _is_task_payload(payload):
    return "task_id" in payload and "status_url" in payload


def _format_analysis_result(title, payload):
    lines = [f"\u3010{title}\u3011", ""]
    for section in build_analysis_sections(payload):
        lines.append(f"\u3010{section['title']}\u3011")
        if section["kind"] == "code_list":
            lines.append(_format_code_snippets(section["items"]))
        else:
            section_text = [section.get("content", "")]
            for child in section.get("children", []):
                section_text.extend([f"{'#' * child.get('level', 2)} {child['title']}", child.get("content", "")])
            lines.append("\n".join(item for item in section_text if item).strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n\n"


def build_analysis_sections(payload):
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

    if evidence:
        used_code = "\u662f" if evidence.get("used_code_context") else "\u5426"
        evidence_lines = [
            f"\u662f\u5426\u7ed3\u5408\u4ee3\u7801: {used_code}",
            f"\u8bc6\u522b\u5230\u7684\u9519\u8bef\u6808: {evidence.get('error_info_count', 0)}",
            f"\u5b9a\u4f4d\u5230\u7684\u4ee3\u7801\u6587\u4ef6: {evidence.get('resolved_file_count', 0)}",
            f"\u4ee3\u7801\u7247\u6bb5\u6570\u91cf: {evidence.get('code_snippet_count', 0)}",
        ]
        snippet_files = evidence.get("code_snippet_files") or []
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
    insertion_index = next(
        (index + 1 for index, section in enumerate(repaired_sections) if section.get("kind") == "code_finding_list"),
        2 if len(repaired_sections) >= 2 else len(repaired_sections),
    )

    query_commands = [str(item).strip() for item in (conclusion.get("query_commands") or []) if str(item).strip()]
    if query_commands:
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
    if fix_commands:
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
    evidence = payload.get("analysis_evidence") or {}
    conclusion = payload.get("issue_conclusion") or {}
    used_code = "\u662f" if evidence.get("used_code_context") else "\u5426"
    hit_cache = "\u662f" if payload.get("knowledge_hit") else "\u5426"
    category_label = repair_mojibake_text(
        conclusion.get("issue_category_label") or conclusion.get("issue_category") or "\u672a\u77e5"
    )
    lines = [
        "\u5206\u6790\u5b8c\u6210\uff0c\u8be6\u60c5\u5df2\u5728\u5f39\u7a97\u4e2d\u6253\u5f00\u3002",
        f"- \u95ee\u9898\u5206\u7c7b: {category_label}",
        f"- \u662f\u5426\u547d\u4e2d\u77e5\u8bc6\u5e93: {hit_cache}",
        f"- \u662f\u5426\u7ed3\u5408\u4ee3\u7801: {used_code}",
        f"- \u8bc6\u522b\u5230\u7684\u9519\u8bef\u6808: {evidence.get('error_info_count', 0)}",
        f"- \u5b9a\u4f4d\u5230\u7684\u4ee3\u7801\u6587\u4ef6: {evidence.get('resolved_file_count', 0)}",
        f"- \u4ee3\u7801\u7247\u6bb5\u6570\u91cf: {evidence.get('code_snippet_count', 0)}",
    ]
    if payload.get("task_id"):
        lines.append(f"- task_id: {payload.get('task_id')}")
    return "\n".join(lines) + "\n\n"


def _build_text_analysis_section(title, value):
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
    lines = [f"\u3010{title}\u3011", ""]
    if payload.get("task_id"):
        lines.append(f"- task_id: {payload.get('task_id')}")
    if payload.get("state"):
        lines.append(f"- \u72b6\u6001: {payload.get('state')}")
    if payload.get("status_url"):
        lines.append(f"- \u67e5\u8be2\u5730\u5740: {payload.get('status_url')}")
    return "\n".join(lines).rstrip() + "\n\n"


def _format_key_value_result(title, payload):
    lines = [f"\u3010{title}\u3011", ""]
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines).rstrip() + "\n\n"


def _format_code_snippets(snippets):
    blocks = []
    for index, snippet in enumerate(_normalize_code_snippets(snippets), start=1):
        header = f"{index}. {snippet['file']}"
        if snippet.get("line"):
            header += f":{snippet['line']}"
        blocks.append(f"{header}\n{_indent_code(snippet['content'])}".rstrip())
    return "\n\n".join(blocks)


def _normalize_code_snippets(snippets):
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
                "language": _guess_code_language(file_path),
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
            "language": _guess_code_language(file_path),
        })
    return [item for item in items if item["code"]]


def _guess_code_language(file_path):
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
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return repair_mojibake_text(json.dumps(value, ensure_ascii=False, indent=2)).strip()
    return repair_mojibake_text(value).strip()


def _clean_markdown_text(value):
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
    return "\n".join(f"    {line}" if line else "" for line in content.splitlines())


class AnalysisResultWindow:
    def __init__(self, parent, payload):
        self.window = tk.Toplevel(parent)
        self.window.title("\u5206\u6790\u7ed3\u679c\u8be6\u60c5")
        self.window.geometry("1120x760")
        self.sections = build_analysis_sections(payload)
        self.section_marks = {}
        self.nav_entries = []

        self._build_layout()
        self._render_sections()
        self.nav_list.selection_set(0)

    def _build_layout(self):
        container = ttk.Frame(self.window, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 10))
        ttk.Label(header, text="\u5206\u6790\u7ed3\u679c\u8be6\u60c5", font=("Microsoft YaHei UI", 15, "bold")).pack(side=tk.LEFT)
        ttk.Button(header, text="\u590d\u5236\u5168\u90e8", command=self._copy_all).pack(side=tk.RIGHT, padx=(8, 0))
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
            else:
                self._insert_text_section(section, index)
        self.content_text.configure(state=tk.DISABLED)

    def _insert_text_section(self, section, section_index):
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
        safe_label = repair_mojibake_text(label)
        self.nav_entries.append({"label": safe_label, "mark": mark_name})
        self.nav_list.insert(tk.END, safe_label)

    def _insert_code_items(self, items):
        for index, item in enumerate(items, start=1):
            header = f"{index}. {item.get('file') or UNKNOWN_FILE_LABEL}"
            if item.get("line"):
                header += f":{item['line']}"
            language = item.get("language")
            if language:
                header += f" ({language})"
            self.content_text.insert(tk.END, header + "\n", "code_header")
            self.content_text.insert(tk.END, (item.get("content") or "") + "\n\n", "code")

    def _insert_code_findings(self, items):
        for index, item in enumerate(items, start=1):
            header = f"{index}. {item.get('file') or UNKNOWN_FILE_LABEL}"
            if item.get("line"):
                header += f":{item['line']}"
            language = item.get("language")
            if language:
                header += f" ({language})"
            self.content_text.insert(tk.END, header + "\n", "code_header")
            if item.get("reason"):
                self.content_text.insert(tk.END, f"\u5b9a\u4f4d\u539f\u56e0: {item['reason']}\n", "body")
            self.content_text.insert(tk.END, (item.get("code") or "") + "\n\n", "code")

    def _on_nav_selected(self, event=None):
        selection = self.nav_list.curselection()
        if not selection:
            return
        entry = self.nav_entries[selection[0]] if selection[0] < len(self.nav_entries) else None
        mark_name = entry.get("mark") if entry else None
        if mark_name:
            self.content_text.see(mark_name)
            self.window.after_idle(lambda: self.content_text.see(mark_name))

    def _copy_all(self):
        text = self.content_text.get("1.0", tk.END).strip()
        self.window.clipboard_clear()
        self.window.clipboard_append(text)


class LogAnalyzerApiClient(ApiClient):

    def get_products(self):
        response = self.session.get(f"{self.base_url}/product/get")
        response.raise_for_status()
        return response.json().get("products", [])

    def get_modules_by_product(self, product_id):
        response = self.session.get(f"{self.base_url}/module/get", params={"product_id": product_id})
        response.raise_for_status()
        return response.json().get("modules", [])

    def get_remote_branches(self, repo_url, force_refresh=False):
        params = {"repo_url": repo_url}
        if force_refresh:
            params["refresh"] = "1"
        response = self.session.get(f"{self.base_url}/git/branches", params=params)
        response.raise_for_status()
        payload = response.json()
        return payload.get("versions") or payload.get("branches", []) + payload.get("tags", [])

    def sync_git_projects(self):
        response = self.session.post(f"{self.base_url}/git/sync-projects")
        response.raise_for_status()
        return response.json()

    def upload_log(self, file_path, product_id, module_id, branch_address, tag_version, date_filter=""):
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
        response = self.session.post(
            f"{self.base_url}/analysis/branch_get",
            json={"branchAddress": branch_address, "tagVersion": tag_version},
        )
        response.raise_for_status()
        return response.json()

    def analyze_log(self, product_id, module_id, branch_address, tag_version, repo_path, file_path):
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
    ):
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
        response = self.session.post(
            f"{self.base_url}/analysis/submit_async",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def get_task_status(self, task_id):
        response = self.session.get(f"{self.base_url}/analysis/task/{task_id}")
        response.raise_for_status()
        return response.json()

    def cancel_task(self, task_id):
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
):
    consecutive_errors = 0

    while True:
        if should_cancel and should_cancel():
            raise OperationCancelled("\u64cd\u4f5c\u5df2\u4e2d\u65ad")

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
            if on_status:
                on_status(progress.get("message") or f"\u5206\u6790\u4efb\u52a1\u72b6\u6001\uff1a{state}")
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
    def __init__(self, root, api_client=None):
        self.root = root
        self.api_client = api_client
        self.root.title(APP_RELEASE_LABEL)
        self.root.geometry("1020x780")
        self.root.deiconify()
        self.upload_result = None
        self.repo_path = None
        self.task_id = None
        self.products = []
        self.modules = []
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
        self.image_tag = tk.StringVar(value="business_image")
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
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        self._build_notice(container)

        form = ttk.LabelFrame(container, text="\u5206\u6790\u914d\u7f6e", padding=12)
        form.pack(fill=tk.X)
        for column in range(5):
            form.columnconfigure(column, weight=0)

        self.backend_entry = self._add_entry(form, "\u540e\u7aef\u5730\u5740", self.backend_url, 0, 0, width=58)
        self.sync_git_button = ttk.Button(form, text="\u540c\u6b65 Git \u9879\u76ee", command=self.sync_git_projects_async)
        self.sync_git_button.grid(row=0, column=2, padx=8, pady=6, sticky=tk.W)

        ttk.Label(form, text="\u4ea7\u54c1").grid(row=1, column=0, sticky=tk.W, pady=6)
        self.product_combo = ttk.Combobox(form, textvariable=self.product_selection, state="normal", width=58)
        self.product_combo.grid(row=1, column=1, columnspan=3, sticky=tk.W, pady=6)
        self._bind_searchable_combobox(self.product_combo, self.on_product_selected)

        ttk.Label(form, text="\u6a21\u5757").grid(row=2, column=0, sticky=tk.W, pady=6)
        self.module_combo = ttk.Combobox(form, textvariable=self.module_selection, state="normal", width=58)
        self.module_combo.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=6)
        self._bind_searchable_combobox(self.module_combo, self.on_module_selected)

        ttk.Label(form, text="\u5206\u652f\u5730\u5740").grid(row=3, column=0, sticky=tk.W, pady=6)
        self.branch_combo = ttk.Combobox(form, textvariable=self.branch_address, state="normal", width=82)
        self.branch_combo.grid(row=3, column=1, columnspan=3, sticky=tk.W, pady=6)
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
        self.log_file_entry = ttk.Entry(form, textvariable=self.file_path, width=82)
        self.log_file_entry.grid(row=7, column=1, sticky=tk.W, pady=6)
        self.choose_file_button = ttk.Button(form, textvariable=self.choose_button_text, command=self.choose_file)
        self.choose_file_button.grid(row=7, column=2, padx=8, pady=6, sticky=tk.W)
        self.paste_image_button = ttk.Button(form, text="\u7c98\u8d34\u56fe\u7247", command=self.paste_image)
        self.paste_image_button.grid(row=7, column=3, padx=8, pady=6, sticky=tk.W)
        self.clear_file_button = ttk.Button(form, text="\u6e05\u7a7a", command=self.clear_selected_input)
        self.clear_file_button.grid(row=7, column=4, padx=8, pady=6, sticky=tk.W)

        self.image_tag_label = ttk.Label(form, text="\u56fe\u7247\u6807\u7b7e")
        self.image_tag_label.grid(row=8, column=0, sticky=tk.W, pady=6)
        self.image_tag_combo = ttk.Combobox(form, textvariable=self.image_tag, values=("log_image", "business_image"), state="readonly", width=24)
        self.image_tag_combo.grid(row=8, column=1, sticky=tk.W, pady=6)

        self.image_description_label = ttk.Label(form, text="\u56fe\u7247\u63cf\u8ff0")
        self.image_description_label.grid(row=9, column=0, sticky=tk.NW, pady=6)
        self.image_description_text = tk.Text(form, width=62, height=4, font=("Microsoft YaHei UI", 10))
        self.image_description_text.grid(row=9, column=1, columnspan=3, sticky=tk.W, pady=6)

        drop_hint_text = (
            "\u652f\u6301\u76f4\u63a5\u62d6\u62fd\u56fe\u7247\u5230\u8fd9\u91cc\uff0c\u4e5f\u53ef\u4ee5\u4f7f\u7528\u7c98\u8d34\u56fe\u7247/\u9009\u62e9\u6587\u4ef6"
            if DRAG_DROP_ENABLED
            else "\u5f53\u524d\u6253\u5305\u73af\u5883\u672a\u542f\u7528\u62d6\u62fd\uff0c\u8bf7\u4f7f\u7528\u7c98\u8d34\u56fe\u7247\u6216\u9009\u62e9\u6587\u4ef6"
        )
        self.drop_hint = ttk.Label(form, text=drop_hint_text, relief=tk.GROOVE, padding=10, width=56)
        self.drop_hint.grid(row=10, column=1, columnspan=3, sticky=tk.W, pady=(0, 6))

        self.image_list_frame = ttk.LabelFrame(form, text="\u5df2\u6682\u5b58\u56fe\u7247", padding=6)
        self.image_list_frame.grid(row=11, column=1, columnspan=4, sticky=tk.W, pady=(0, 6))
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
        ttk.Label(actions, textvariable=self.status).pack(side=tk.LEFT, padx=16)

        progress_frame = ttk.Frame(container, padding=(0, 0, 0, 8))
        progress_frame.pack(fill=tk.X)
        ttk.Progressbar(progress_frame, variable=self.progress_percent, maximum=100, mode="determinate").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(progress_frame, textvariable=self.progress_text, width=32).pack(side=tk.LEFT, padx=8)

        result_frame = ttk.LabelFrame(container, text="\u6267\u884c\u7ed3\u679c", padding=8)
        result_frame.pack(fill=tk.BOTH, expand=True)
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.result_text.pack(fill=tk.BOTH, expand=True)

        self._install_drop_support()
        self._on_input_mode_changed()

    def _build_notice(self, parent):
        notice = ttk.LabelFrame(parent, text="\u516c\u544a\u8bf4\u660e", padding=10)
        notice.pack(fill=tk.X, pady=(0, 10))
        notice.columnconfigure(0, weight=1)
        ttk.Label(notice, text=build_notice_title(), font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        ttk.Label(notice, text=build_notice_text(), justify=tk.LEFT, wraplength=1320).grid(row=1, column=0, sticky=tk.W)

    def _add_entry(self, parent, label, variable, row, column, columnspan=1, width=30):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky=tk.W, pady=6)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=column + 1, columnspan=columnspan, sticky=tk.W, pady=6)
        return entry

    def _bind_searchable_combobox(self, combobox, selected_callback=None):
        if selected_callback:
            combobox.bind("<<ComboboxSelected>>", selected_callback)
        combobox.bind("<KeyRelease>", lambda event, widget=combobox: self._filter_combobox_values(widget, event))
        combobox.bind("<Return>", lambda event, widget=combobox, callback=selected_callback: self._accept_combobox_filter(widget, callback))

    def _set_combobox_values(self, combobox, values):
        normalized_values = list(values or [])
        self._combobox_all_values[combobox] = normalized_values
        combobox["values"] = normalized_values

    def _filter_combobox_values(self, combobox, event=None):
        if event and event.keysym in {"Return", "Escape", "Tab", "Up", "Down", "Left", "Right"}:
            return
        query = combobox.get().strip().lower()
        all_values = self._combobox_all_values.get(combobox, list(combobox["values"]))
        combobox["values"] = all_values if not query else [value for value in all_values if query in str(value).lower()]

    def _accept_combobox_filter(self, combobox, selected_callback=None):
        values = list(combobox["values"])
        current = combobox.get()
        all_values = self._combobox_all_values.get(combobox, values)
        if current not in all_values and values:
            combobox.set(values[0])
        if selected_callback:
            selected_callback()
        return "break"

    def choose_file(self):
        if self.input_mode.get() == "image":
            selected = filedialog.askopenfilenames(title="\u9009\u62e9\u56fe\u7247\u6587\u4ef6", filetypes=[("\u56fe\u7247\u6587\u4ef6", "*.png *.jpg *.jpeg"), ("\u6240\u6709\u6587\u4ef6", "*.*")])
            self._add_image_paths(selected)
            return
        else:
            selected = filedialog.askopenfilename(title="\u9009\u62e9\u65e5\u5fd7\u6587\u4ef6", filetypes=[("\u65e5\u5fd7\u6587\u4ef6", "*.log *.txt *.gz"), ("\u6240\u6709\u6587\u4ef6", "*.*")])
        if selected:
            self.file_path.set(selected)

    def _on_input_mode_changed(self):
        is_image_mode = self.input_mode.get() == "image"
        self.path_label_var.set("\u56fe\u7247\u6587\u4ef6" if is_image_mode else "\u65e5\u5fd7\u6587\u4ef6")
        self.choose_button_text.set("\u9009\u62e9\u56fe\u7247" if is_image_mode else "\u9009\u62e9\u6587\u4ef6")
        self.upload_button.configure(text="\u4e0a\u4f20\u56fe\u7247" if is_image_mode else "\u4e0a\u4f20\u65e5\u5fd7")
        self.date_combo.configure(state="disabled" if is_image_mode else "normal")
        if is_image_mode:
            self.image_tag_label.grid()
            self.image_tag_combo.grid()
            self.image_description_label.grid()
            self.image_description_text.grid()
            self.drop_hint.grid()
            self.image_list_frame.grid()
            self.paste_image_button.grid()
            self.clear_file_button.grid()
        else:
            self.image_tag_label.grid_remove()
            self.image_tag_combo.grid_remove()
            self.image_description_label.grid_remove()
            self.image_description_text.grid_remove()
            self.drop_hint.grid_remove()
            self.image_list_frame.grid_remove()
            self.paste_image_button.grid_remove()
            self.clear_file_button.grid_remove()

    def _get_image_description(self):
        return self.image_description_text.get("1.0", tk.END).strip()

    def clear_selected_input(self):
        self.file_path.set("")
        self.image_paths = []
        self._refresh_image_list()
        self.image_description_text.delete("1.0", tk.END)

    def paste_image(self):
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
        self.image_paths = [item for item in self.image_paths if item != path]
        self._refresh_image_list()

    def _refresh_image_list(self):
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
        if windnd is None:
            return
        for widget in (self.drop_hint, self.log_file_entry):
            try:
                windnd.hook_dropfiles(widget, func=self._handle_drop_files)
            except Exception:
                pass

    def _handle_drop_files(self, files):
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
        self._run_background(self.refresh_products)

    def sync_git_projects_async(self):
        self._run_background(self.sync_git_projects)

    def sync_git_projects(self):
        self._set_status("\u6b63\u5728\u540c\u6b65 Git \u9879\u76ee...")
        result = self._client().sync_git_projects()
        self._write_result("Git \u540c\u6b65\u7ed3\u679c", result)
        self._set_status(f"Git \u9879\u76ee\u540c\u6b65\u5b8c\u6210\uff0c\u5df2\u540c\u6b65 {result.get('synced_projects', 0)} \u4e2a\u4ed3\u5e93")
        self.refresh_products()

    def refresh_products(self):
        self._set_status("\u6b63\u5728\u52a0\u8f7d\u4ea7\u54c1...")
        products = self._client().get_products()

        def update():
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
        product = self.product_by_label.get(self.product_selection.get())
        if not product:
            self.product_id.set("")
            self._clear_module_branch_selection()
            return
        self.product_id.set(str(product.get("id", "")))
        self._run_background(self.load_modules_for_selected_product)

    def load_modules_for_selected_product(self):
        product_id = self.product_id.get()
        if not product_id:
            return
        self._set_status("\u6b63\u5728\u52a0\u8f7d\u6a21\u5757/\u4ed3\u5e93...")
        modules = self._client().get_modules_by_product(product_id)

        def update():
            self.modules = modules
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
        module = self.module_by_label.get(self.module_selection.get())
        if not module:
            self.module_id.set("")
            return
        self.module_id.set(str(module.get("module_id", "")))
        branch = module.get("branch") or {}
        branch_address = branch.get("branch_address")
        tag_version = branch.get("tag_version")
        if branch_address:
            self.branch_address.set(branch_address)
            self._sync_versions_for_branch()
        if tag_version:
            self.tag_version.set(tag_version)
        if self._should_auto_refresh_versions(branch_address):
            self.load_remote_branches_for_selected_repo_async()

    def on_branch_selected(self, event=None):
        self._sync_versions_for_branch()
        if self._should_auto_refresh_versions(self.branch_address.get()):
            self.load_remote_branches_for_selected_repo_async()

    def _has_cached_versions_for_branch(self, branch_address):
        return bool(branch_address and self.branch_versions.get(branch_address))

    def _should_auto_refresh_versions(self, branch_address):
        if not branch_address:
            return False
        versions = self.branch_versions.get(branch_address, [])
        return not versions or (len(versions) <= 1 and branch_address not in self.version_refresh_attempted)

    def refresh_branch_versions_async(self):
        self.load_remote_branches_for_selected_repo_async(force_refresh=True)

    def load_remote_branches_for_selected_repo_async(self, force_refresh=False):
        self._run_background(lambda: self.load_remote_branches_for_selected_repo(force_refresh=force_refresh))

    def load_remote_branches_for_selected_repo(self, force_refresh=False):
        repo_url = self.branch_address.get().strip()
        if not repo_url:
            return
        self._set_status("\u6b63\u5728\u62c9\u53d6 Git \u5206\u652f/Tag...")
        branches = self._client().get_remote_branches(repo_url, force_refresh=force_refresh)
        self.version_refresh_attempted.add(repo_url)

        def update():
            self.branch_versions[repo_url] = branches
            self._set_combobox_values(self.tag_combo, branches)
            self.tag_version.set(branches[0] if branches else "")
            self.status.set("\u7248\u672c/Tag \u5df2\u5237\u65b0" if branches else "\u672a\u83b7\u53d6\u5230\u53ef\u7528\u7248\u672c/Tag")

        self.root.after(0, update)

    def _sync_versions_for_branch(self):
        versions = self.branch_versions.get(self.branch_address.get(), [])
        self._set_combobox_values(self.tag_combo, versions)
        if versions and self.tag_version.get() not in versions:
            self.tag_version.set(versions[0])
        elif not versions:
            self.tag_version.set("")

    def _clear_module_branch_selection(self):
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
        branch_versions = {}
        for module in modules:
            branch = module.get("branch") or {}
            address = branch.get("branch_address")
            version = branch.get("tag_version")
            if not address:
                continue
            branch_versions.setdefault(address, [])
            if version and version not in branch_versions[address]:
                branch_versions[address].append(version)
        return branch_versions

    def _product_label(self, product):
        return f"{product.get('id')} - {product.get('name', '')}"

    def _module_label(self, module):
        return f"{module.get('module_id')} - {module.get('module_name', '')}"

    def upload_async(self):
        self._run_background(self.upload, cancellable=True)

    def analyze_async(self):
        self._run_background(self.analyze, cancellable=True, analysis_action=True)

    def upload_and_analyze_async(self):
        self._run_background(self.upload_and_analyze, cancellable=True, analysis_action=True)

    def analyze_or_cancel(self):
        if self.analysis_running:
            self.cancel_current_operation()
            return
        self.analyze_async()

    def upload(self):
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
        task_result = client.submit_analysis_task(self.product_id.get(), self.module_id.get(), self.branch_address.get(), self.tag_version.get(), self.upload_result["file_path"], self.upload_result.get("log_id"), source_type=self.upload_result.get("source_type", self.input_mode.get()), image_tag=self.upload_result.get("image_tag", ""), image_description=self.upload_result.get("image_description", self._get_image_description()), file_paths=self.upload_result.get("file_paths"), log_ids=self.upload_result.get("log_ids"))
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

    def upload_and_analyze(self):
        self.upload()
        self.analyze()

    def _poll_analysis_task(self, client, task_id):
        return poll_task_until_ready(client, task_id, on_status=self._set_status, on_progress=self._handle_task_progress, should_cancel=lambda: self.cancel_requested)

    def _client(self):
        if self.api_client is not None:
            self.api_client.set_base_url(self.backend_url.get())
            return self.api_client
        return LogAnalyzerApiClient(self.backend_url.get())

    def _validate_common_fields(self, require_file):
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
        if cancellable:
            self.cancel_requested = False
            self._set_cancel_enabled(True)
        if analysis_action:
            self._set_analysis_running(True)
        threading.Thread(target=self._run_action, args=(action, cancellable, analysis_action), daemon=True).start()

    def _run_action(self, action, cancellable=False, analysis_action=False):
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
        if self.last_failed_action:
            self._run_background(self.last_failed_action)

    def _set_retry_enabled(self, enabled):
        if self.retry_button is None:
            return
        state = tk.NORMAL if enabled else tk.DISABLED
        self.root.after(0, lambda: self.retry_button.configure(state=state))

    def _set_cancel_enabled(self, enabled):
        return

    def _set_analysis_running(self, running):
        self.analysis_running = running
        text = "\u4e2d\u65ad\u5206\u6790" if running else "\u5f00\u59cb\u5206\u6790"
        if not running:
            self._stop_progress_animation()
        self.root.after(0, lambda: self.analyze_button.configure(text=text))

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.set(text))

    def _set_progress(self, percent, message):
        safe_percent = max(0, min(100, int(percent)))
        self.root.after(0, lambda: (self.progress_percent.set(safe_percent), self.progress_text.set(message)))

    def _handle_task_progress(self, progress):
        percent = progress.get("percent", self.progress_percent.get())
        default_stage_label = "\u5904\u7406\u4e2d"
        stage_label = progress.get("stage_label", default_stage_label)
        stage_percent = progress.get("stage_percent", percent)
        message = progress.get("message") or f"{stage_label} {stage_percent}%"
        message = repair_mojibake_text(message)
        message = format_progress_message_for_percent(message, percent)
        self._set_progress(percent, message)
        if int(percent or 0) >= 100:
            self._stop_progress_animation()
        else:
            self._start_progress_animation(get_smooth_progress_limit(progress))

    def _start_progress_animation(self, target):
        self.progress_animation_target = max(0, min(99, int(target)))
        if self.progress_animation_job is None:
            self.progress_animation_job = self.root.after(700, self._animate_progress_tick)

    def _stop_progress_animation(self):
        job = self.progress_animation_job
        self.progress_animation_job = None
        self.progress_animation_target = 0
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

    def _animate_progress_tick(self):
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
        if self.cancel_requested:
            raise OperationCancelled("\u64cd\u4f5c\u5df2\u4e2d\u65ad")

    def cancel_current_operation(self):
        self.cancel_requested = True
        self._set_status("\u6b63\u5728\u8bf7\u6c42\u4e2d\u65ad\u5f53\u524d\u4efb\u52a1...")
        self._set_progress(self.progress_percent.get(), "\u6b63\u5728\u4e2d\u65ad")
        if not self.task_id:
            return

        task_id = self.task_id

        def cancel_remote():
            try:
                result = self._client().cancel_task(task_id)
                self._write_result("\u4e2d\u65ad\u7ed3\u679c", result)
            except Exception as exc:
                self._set_status(f"\u4e2d\u65ad\u8bf7\u6c42\u5931\u8d25\uff1a{format_exception_message(exc)}")

        threading.Thread(target=cancel_remote, daemon=True).start()

    def _on_root_destroy(self, event=None):
        if event is None or event.widget is self.root:
            self._stop_progress_animation()

    def _on_close(self):
        self._stop_progress_animation()
        try:
            if self.api_client is not None:
                self.api_client.logout()
        except requests.RequestException:
            pass
        finally:
            self.root.destroy()

    def _write_analysis_summary(self, payload):
        summary = build_analysis_summary(payload)
        self.root.after(0, lambda: (self.result_text.insert(tk.END, summary), self.result_text.see(tk.END)))

    def _show_analysis_result(self, payload):
        self.root.after(0, lambda: AnalysisResultWindow(self.root, payload))

    def _write_result(self, title, payload):
        formatted = format_result_payload(title, payload)
        self.root.after(0, lambda: (self.result_text.insert(tk.END, formatted), self.result_text.see(tk.END)))


class ClientApplication:
    def __init__(self, root):
        self.root = root
        self.main_window = None
        self.login_window = None
        self.client = LogAnalyzerApiClient(
            DEFAULT_BACKEND_URL,
            on_unauthorized=self._handle_unauthorized,
        )
        self.show_login()

    def show_login(self):
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
        self.login_window = None
        if self.main_window is None:
            self.main_window = LogAnalyzerWindow(self.root, api_client=self.client)
        else:
            self.root.deiconify()

    def _handle_unauthorized(self):
        self.root.after(0, self.show_login)


def main():
    root = tk.Tk()
    ClientApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()
