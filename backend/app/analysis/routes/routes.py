import base64
import hashlib
import json
import os
import re,subprocess
import logging
from flask import Blueprint, request, jsonify, current_app as app
from openai import OpenAI
from celery.result import AsyncResult
from extensions import celery
from app.analysis.routes.tasks import analyze_log_task
from app.logfile.models.model import AnalysisKnowledgeCase, QueryRecord
from datetime import datetime
from extensions import db


ISSUE_CATEGORY_LABELS = {
    "code_issue": "\u4ee3\u7801\u95ee\u9898",
    "data_issue": "\u6570\u636e\u95ee\u9898",
    "config_issue": "\u914d\u7f6e\u95ee\u9898",
    "network_issue": "\u7f51\u7edc\u95ee\u9898",
    "dependency_issue": "\u4f9d\u8d56/\u7b2c\u4e09\u65b9\u670d\u52a1\u95ee\u9898",
    "resource_issue": "\u8d44\u6e90\u95ee\u9898",
    "unknown": "\u672a\u77e5",
}

POSSIBLE_CAUSE_KEYS = (
    "code_issue",
    "config_issue",
    "network_issue",
    "data_issue",
    "dependency_issue",
    "resource_issue",
)

DEFAULT_POSSIBLE_CAUSE = {
    "possible": False,
    "confidence": 0,
    "reason": "",
}


def normalize_command_list(value):
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []

    normalized = []
    for item in items:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized

LOG_ERROR_CONTEXT_LINES = 10
LOG_CONTEXT_MAX_CHARS = 30000

COMPONENT_USAGE_PATTERNS = {
    "redis": [
        "redis",
        "redistemplate",
        "stringredistemplate",
        "jedis",
        "lettuce",
        "redisson",
        "@cacheable",
        "@cacheput",
        "@cacheevict",
    ],
    "flyway": [
        "flyway",
        "flywaymigration",
        "db/migration",
        "baselineonmigrate",
        "locations(",
    ],
}

SOURCE_CODE_SUFFIXES = {
    ".java",
    ".kt",
    ".groovy",
    ".xml",
    ".yml",
    ".yaml",
    ".properties",
    ".gradle",
}

SKIP_CODE_SEARCH_DIRS = {
    ".git",
    ".idea",
    ".gradle",
    "build",
    "target",
    "out",
    "dist",
    "node_modules",
    "logs",
}


# 配置 Flask Blueprint 和日志格式
analysis_bp = Blueprint("analysis", __name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

@analysis_bp.route("/branch_get", methods=["POST"])
def get_branch_info():
    """\u83b7\u53d6\u4ed3\u5e93\u7684\u8fdc\u7a0b\u5206\u652f\u4fe1\u606f\u3002"""
    data = request.json
    address = data.get("branchAddress")
    tag_version = data.get("tagVersion")
    if not address or not tag_version:
        logging.error("\u83b7\u53d6\u5206\u652f\u4fe1\u606f\u5931\u8d25\uff1a\u7f3a\u5c11\u5fc5\u8981\u5b57\u6bb5 branchAddress \u6216 tagVersion")
        return jsonify({"error": "\u7f3a\u5c11\u5fc5\u8981\u5b57\u6bb5\uff1abranchAddress, tagVersion"}), 400

    repo_path = clone_git_repo(address, tag_version)
    if not repo_path:
        logging.error("\u83b7\u53d6\u5206\u652f\u4fe1\u606f\u5931\u8d25\uff1a\u514b\u9686 Git \u4ed3\u5e93\u5931\u8d25")
        return jsonify({"error": "\u514b\u9686 Git \u4ed3\u5e93\u5931\u8d25"}), 500

    try:
        logging.info("\u5f00\u59cb\u8bfb\u53d6 Git \u8fdc\u7a0b\u5206\u652f\uff1arepo_path=%s", repo_path)
        result = subprocess.run(
            ["git", "branch", "-r"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        branches = result.stdout.decode("utf-8").splitlines()
        logging.info("\u8bfb\u53d6\u8fdc\u7a0b\u5206\u652f\u6210\u529f\uff1acount=%s", len(branches))
    except subprocess.CalledProcessError as e:
        logging.error("\u8bfb\u53d6\u8fdc\u7a0b\u5206\u652f\u5931\u8d25\uff1a%s", e)
        return jsonify({"error": "\u83b7\u53d6\u5206\u652f\u4fe1\u606f\u5931\u8d25"}), 500

    return jsonify({
        "branches": branches,
        "repo_path": repo_path,
    })


def clone_git_repo(address, tag_version, workspace_id=None):
    """\u514b\u9686\u6307\u5b9a Git \u4ed3\u5e93\u5230\u672c\u5730\u5de5\u4f5c\u76ee\u5f55\u3002"""
    GIT_USER = app.config.get("GIT_USER")
    GIT_PASSWORD = app.config.get("GIT_PASSWORD")

    repo_name = address.split("/")[-1].replace(".git", "")
    safe_tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", tag_version or "default")
    safe_workspace = re.sub(r"[^A-Za-z0-9_.-]+", "_", workspace_id or "shared")
    repo_dir = os.path.join("/tmp/log-analyzer-repos", safe_workspace, f"{repo_name}-{safe_tag}")

    if os.path.exists(repo_dir):
        logging.info("Git \u4ed3\u5e93\u5df2\u5b58\u5728\uff0c\u590d\u7528\u672c\u5730\u76ee\u5f55\uff1arepo_dir=%s", repo_dir)
        return repo_dir

    repo_address = address.replace("https://", f"https://{GIT_USER}:{GIT_PASSWORD}@")
    try:
        os.makedirs(os.path.dirname(repo_dir), exist_ok=True)
        logging.info(
            "\u5f00\u59cb\u514b\u9686 Git \u4ed3\u5e93\uff1arepo=%s, version=%s, workspace=%s",
            address,
            tag_version,
            workspace_id or "shared",
        )
        subprocess.run(
            ["git", "clone", "-b", tag_version, repo_address, repo_dir],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logging.info("Git \u4ed3\u5e93\u514b\u9686\u6210\u529f\uff1arepo_dir=%s", repo_dir)
        return repo_dir
    except subprocess.CalledProcessError as e:
        logging.error("Git \u514b\u9686\u5931\u8d25\uff1arepo=%s, version=%s, error=%s", address, tag_version, e)
        return None


@analysis_bp.route("/submit_async", methods=["POST"])
def submit_async_analysis():
    data = request.json or {}
    source_type = str(data.get("source_type") or "file").lower()
    if source_type == "image" and not data.get("image_tag"):
        return jsonify({"error": "\u7f3a\u5c11\u5fc5\u8981\u5b57\u6bb5", "missing_fields": ["image_tag"]}), 400
    if source_type == "image" and data.get("file_paths") and not data.get("file_path"):
        data["file_path"] = data.get("file_paths")[0]
    required_fields = ["productId", "moduleId", "branchAddress", "tagVersion", "file_path"]
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return jsonify({"error": "\u7f3a\u5c11\u5fc5\u8981\u5b57\u6bb5", "missing_fields": missing_fields}), 400

    task = analyze_log_task.delay(data)
    return jsonify({
        "task_id": task.id,
        "state": task.state,
        "status_url": f"/analysis/task/{task.id}",
    }), 202


@analysis_bp.route("/task/<task_id>", methods=["GET"])
def get_analysis_task(task_id):
    task = AsyncResult(task_id, app=celery)
    payload = {
        "task_id": task_id,
        "state": task.state,
        "ready": task.ready(),
        "successful": task.successful() if task.ready() else False,
    }
    progress = task.info if isinstance(task.info, dict) else None
    if progress:
        payload["progress"] = progress

    if task.ready():
        if task.successful():
            payload["result"] = task.result
        else:
            payload["error"] = str(task.result)

    return jsonify(payload)


@analysis_bp.route("/task/<task_id>/cancel", methods=["POST"])
def cancel_analysis_task(task_id):
    celery.control.revoke(task_id, terminate=True, signal="SIGTERM")
    return jsonify({
        "task_id": task_id,
        "state": "REVOKED",
        "message": "\u4efb\u52a1\u5df2\u8bf7\u6c42\u53d6\u6d88",
    }), 202

@analysis_bp.route("/log_analysis", methods=["POST"])
def analyze_log_and_code():
    logging.info("==> \u8fdb\u5165 analyze_log_and_code")
    data = request.json
    logging.info("\u6536\u5230\u540c\u6b65\u5206\u6790\u8bf7\u6c42\uff1a%s", data)
    log_file_path = data.get("file_path")
    repo_path = data.get("repo_path")

    logging.info("\u65e5\u5fd7\u6587\u4ef6\u8def\u5f84\uff1a%s", log_file_path)
    logging.info("\u4ee3\u7801\u4ed3\u5e93\u8def\u5f84\uff1a%s", repo_path)

    if not log_file_path or not os.path.exists(log_file_path):
        logging.error("\u65e5\u5fd7\u6587\u4ef6\u8def\u5f84\u65e0\u6548\u6216\u6587\u4ef6\u4e0d\u5b58\u5728\uff1a%s", log_file_path)
        return jsonify({"error": "\u65e5\u5fd7\u6587\u4ef6\u8def\u5f84\u65e0\u6548\u6216\u6587\u4ef6\u4e0d\u5b58\u5728"}), 400
    if not repo_path or not os.path.exists(repo_path):
        logging.error("\u4ed3\u5e93\u8def\u5f84\u65e0\u6548\u6216\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a%s", repo_path)
        return jsonify({"error": "\u4ed3\u5e93\u8def\u5f84\u65e0\u6548\u6216\u76ee\u5f55\u4e0d\u5b58\u5728"}), 400

    try:
        with open(log_file_path, "r", encoding="utf-8") as file_obj:
            log_content = file_obj.read()
        logging.info("\u65e5\u5fd7\u6587\u4ef6\u8bfb\u53d6\u6210\u529f\uff1apath=%s, chars=%s", log_file_path, len(log_content))
    except Exception as exc:
        logging.exception("\u8bfb\u53d6\u65e5\u5fd7\u5931\u8d25\uff1a%s", exc)
        return jsonify({"error": "\u8bfb\u53d6\u65e5\u5fd7\u5931\u8d25"}), 500

    logging.info("\u5f00\u59cb\u6267\u884c\u65e5\u5fd7\u521d\u6b65\u5206\u6790")
    log_analysis = analyze_log_with_deepseek(log_content)
    if not log_analysis:
        logging.error("\u65e5\u5fd7\u521d\u6b65\u5206\u6790\u8fd4\u56de\u4e3a\u7a7a")
        insert_query_record(data, 1)
        return jsonify({"error": "\u65e5\u5fd7\u5206\u6790\u5931\u8d25"}), 500
    logging.info("\u65e5\u5fd7\u521d\u6b65\u5206\u6790\u5b8c\u6210")

    logging.info("\u5f00\u59cb\u4ece\u65e5\u5fd7\u4e2d\u63d0\u53d6\u9519\u8bef\u5806\u6808\u548c\u5f02\u5e38\u4fe1\u606f")
    error_info = extract_error_info_from_log(log_content)
    if not error_info:
        logging.error("\u672a\u80fd\u4ece\u65e5\u5fd7\u4e2d\u63d0\u53d6\u5230\u9519\u8bef\u4fe1\u606f")
        return jsonify({"error": "\u65e0\u6cd5\u4ece\u65e5\u5fd7\u4e2d\u63d0\u53d6\u9519\u8bef\u4fe1\u606f"}), 400
    logging.info("\u9519\u8bef\u4fe1\u606f\u63d0\u53d6\u5b8c\u6210\uff1acount=%s", len(error_info))

    logging.info("\u5f00\u59cb\u89e3\u6790\u4ed3\u5e93\u4e2d\u7684\u5b9e\u9645\u4ee3\u7801\u6587\u4ef6\u8def\u5f84")
    resolved_errors = resolve_file_paths(repo_path, error_info)
    logging.info("\u4ee3\u7801\u6587\u4ef6\u8def\u5f84\u89e3\u6790\u5b8c\u6210\uff1acount=%s", len(resolved_errors))

    logging.info("\u5f00\u59cb\u63d0\u53d6\u76f8\u5173\u4ee3\u7801\u7247\u6bb5")
    stack_snippets = extract_code_snippets(resolved_errors)
    components = detect_error_components(log_content)
    component_snippets = find_component_code_usages(repo_path, components)
    code_snippets = merge_code_snippets(stack_snippets, component_snippets)
    code_findings = build_code_findings(code_snippets)
    logging.info(
        "\u4ee3\u7801\u7247\u6bb5\u63d0\u53d6\u5b8c\u6210\uff1astack_snippets=%s, component_snippets=%s, merged_snippets=%s",
        len(stack_snippets),
        len(component_snippets),
        len(code_snippets),
    )

    logging.info("\u5f00\u59cb\u6267\u884c\u4ee3\u7801\u4e0e\u65e5\u5fd7\u7684\u7efc\u5408\u5206\u6790")
    code_analysis = analyze_code_with_deepseek(log_content, log_analysis, code_snippets)
    if code_analysis:
        insert_query_record(data, 0)
        logging.info("\u7efc\u5408\u5206\u6790\u6210\u529f")
    else:
        logging.error("\u7efc\u5408\u5206\u6790\u5931\u8d25")
        insert_query_record(data, 1)
    logging.info("\u540c\u6b65\u5206\u6790\u5b8c\u6210\uff0c\u51c6\u5907\u8fd4\u56de\u7ed3\u679c")
    response_payload = {
        "log_analysis": log_analysis,
        "code_snippets": code_snippets,
        "code_findings": code_findings,
        "code_analysis": code_analysis
    }
    return jsonify(response_payload)


def normalize_error_message(message):
    text = str(message or "").lower()
    text = re.sub(r"\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?", "<timestamp>", text)
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", text)
    text = re.sub(r"\b[a-z0-9_-]*id\s*[:=]\s*[a-z0-9_.:-]+\b", "id=<id>", text)
    text = re.sub(r"\b\d+\b", "<num>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_error_fingerprint(product_id, module_id, error_info, branch_url=None, branch_version=None, fallback_text=None):
    first_error = (error_info or [{}])[0] or {}
    raw_error = first_error.get("error") or ""
    if not raw_error and fallback_text:
        raw_error = str(fallback_text)
    error_type = extract_error_type(raw_error)
    normalized_message = normalize_error_message(raw_error)
    file_name = first_error.get("file") or ""
    seed = "|".join([
        str(product_id or ""),
        str(module_id or ""),
        str(branch_url or ""),
        str(branch_version or ""),
        str(error_type or ""),
        str(file_name or ""),
        normalized_message,
    ])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def extract_error_type(error_message):
    match = re.search(r"([A-Za-z_][\w\.]*(?:Exception|Error))", str(error_message or ""))
    return match.group(1) if match else None


def clamp_confidence(value):
    try:
        confidence = float(value or 0)
    except (TypeError, ValueError):
        confidence = 0
    return max(0, min(1, confidence))


def normalize_possible_causes(value):
    normalized = {}
    source = value if isinstance(value, dict) else {}
    for key in POSSIBLE_CAUSE_KEYS:
        item = source.get(key) if isinstance(source.get(key), dict) else {}
        normalized[key] = {
            "possible": bool(item.get("possible", DEFAULT_POSSIBLE_CAUSE["possible"])),
            "confidence": clamp_confidence(item.get("confidence", DEFAULT_POSSIBLE_CAUSE["confidence"])),
            "reason": str(item.get("reason", DEFAULT_POSSIBLE_CAUSE["reason"]) or "").strip(),
        }
    return normalized


def parse_issue_conclusion(ai_text):
    raw_text = str(ai_text or "").strip()
    payload = extract_json_object(raw_text)
    if not isinstance(payload, dict):
        return {
            "issue_category": "unknown",
            "issue_category_label": ISSUE_CATEGORY_LABELS["unknown"],
            "conclusion_summary": "",
            "root_cause": "",
            "solution": "",
            "confidence": 0,
            "possible_causes": normalize_possible_causes(None),
            "query_commands": [],
            "fix_commands": [],
            "evidence": [],
            "raw_analysis": raw_text,
        }

    issue_category = payload.get("issue_category") or "unknown"
    if issue_category not in ISSUE_CATEGORY_LABELS:
        issue_category = "unknown"
    confidence = clamp_confidence(payload.get("confidence"))
    evidence = payload.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    elif not isinstance(evidence, list):
        evidence = []

    return {
        "issue_category": issue_category,
        "issue_category_label": ISSUE_CATEGORY_LABELS[issue_category],
        "conclusion_summary": str(payload.get("conclusion_summary") or "").strip(),
        "root_cause": str(payload.get("root_cause") or "").strip(),
        "solution": str(payload.get("solution") or "").strip(),
        "confidence": confidence,
        "possible_causes": normalize_possible_causes(payload.get("possible_causes")),
        "query_commands": normalize_command_list(payload.get("query_commands")),
        "fix_commands": normalize_command_list(payload.get("fix_commands")),
        "evidence": [str(item) for item in evidence],
        "raw_analysis": raw_text,
    }


def extract_json_object(text):
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            continue
    return None


def find_knowledge_case(product_id, module_id, error_fingerprint):
    if not all([product_id, module_id, error_fingerprint]):
        return None
    return AnalysisKnowledgeCase.query.filter_by(
        product_id=int(product_id),
        module_id=int(module_id),
        error_fingerprint=error_fingerprint,
    ).first()


def build_cached_analysis_payload(case, task_id=None, repo_path=None):
    case.hit_count = (case.hit_count or 0) + 1
    case.last_hit_at = datetime.utcnow()
    db.session.commit()

    code_snippets = safe_json_loads(case.code_snippets, [])
    code_findings = build_code_findings(code_snippets)
    evidence = safe_json_loads(case.evidence, [])
    cached_payload = extract_json_object(case.ai_analysis or "") or {}
    issue_conclusion = {
        "issue_category": case.issue_category,
        "issue_category_label": ISSUE_CATEGORY_LABELS.get(case.issue_category, ISSUE_CATEGORY_LABELS["unknown"]),
        "conclusion_summary": case.conclusion_summary or "",
        "root_cause": case.root_cause or "",
        "solution": case.solution or "",
        "confidence": float(case.confidence or 0),
        "possible_causes": normalize_possible_causes(cached_payload.get("possible_causes")),
        "query_commands": normalize_command_list(cached_payload.get("query_commands")),
        "fix_commands": normalize_command_list(cached_payload.get("fix_commands")),
        "evidence": evidence,
        "raw_analysis": case.ai_analysis or "",
    }
    return {
        "task_id": task_id,
        "repo_path": repo_path,
        "knowledge_hit": True,
        "knowledge_case_id": case.id,
        "knowledge_hit_count": case.hit_count,
        "error_fingerprint": case.error_fingerprint,
        "log_analysis": case.log_excerpt or "",
        "code_snippets": code_snippets,
        "code_findings": code_findings,
        "analysis_evidence": {
            "used_code_context": bool(code_snippets),
            "error_info_count": 1 if case.error_message else 0,
            "resolved_file_count": len(safe_json_loads(case.code_files, [])),
            "code_snippet_count": len(code_snippets),
            "code_snippet_files": safe_json_loads(case.code_files, []),
        },
        "issue_conclusion": issue_conclusion,
        "code_analysis": case.ai_analysis or case.conclusion_summary or "",
    }


def safe_json_dumps(value):
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def safe_json_loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def upsert_knowledge_case(data, error_fingerprint, error_info, log_content, code_snippets, code_analysis, issue_conclusion):
    if not error_fingerprint or not code_analysis:
        return None
    product_id = int(data.get("productId"))
    module_id = int(data.get("moduleId"))
    case = find_knowledge_case(product_id, module_id, error_fingerprint)
    first_error = (error_info or [{}])[0] or {}
    code_files = []
    for snippet in code_snippets or []:
        file_path = snippet.get("file") if isinstance(snippet, dict) else None
        if file_path and file_path not in code_files:
            code_files.append(file_path)
    if not case:
        case = AnalysisKnowledgeCase(
            product_id=product_id,
            module_id=module_id,
            error_fingerprint=error_fingerprint,
            hit_count=0,
        )
        db.session.add(case)

    case.error_type = extract_error_type(first_error.get("error"))
    case.error_message = first_error.get("error")
    case.stack_top_file = first_error.get("file")
    case.stack_top_line = first_error.get("line")
    case.branch_url = data.get("branchAddress")
    case.branch_version = data.get("tagVersion")
    case.log_excerpt = (log_content or "")[:4000]
    case.code_files = safe_json_dumps(code_files)
    case.code_snippets = safe_json_dumps(code_snippets or [])
    case.issue_category = issue_conclusion.get("issue_category") or "unknown"
    case.conclusion_summary = issue_conclusion.get("conclusion_summary")
    case.root_cause = issue_conclusion.get("root_cause")
    case.solution = issue_conclusion.get("solution")
    case.ai_analysis = code_analysis
    case.evidence = safe_json_dumps(issue_conclusion.get("evidence") or [])
    case.confidence = issue_conclusion.get("confidence") or 0
    case.updated_at = datetime.utcnow()
    db.session.commit()
    return case


def get_int_config(name, default):
    try:
        return int(app.config.get(name, default))
    except (TypeError, ValueError):
        return default


def get_error_context_settings():
    context_lines = get_int_config("LOG_ERROR_CONTEXT_LINES", LOG_ERROR_CONTEXT_LINES)
    max_chars = get_int_config("LOG_CONTEXT_MAX_CHARS", LOG_CONTEXT_MAX_CHARS)
    return max(0, context_lines), max(1000, max_chars)


def extract_relevant_log_context(log_content, context_lines=None, max_chars=None):
    text = str(log_content or "")
    if not text:
        return ""

    lines = text.splitlines()
    if not lines:
        return text

    if context_lines is None or max_chars is None:
        default_context_lines, default_max_chars = get_error_context_settings()
        context_lines = default_context_lines if context_lines is None else context_lines
        max_chars = default_max_chars if max_chars is None else max_chars

    context_lines = max(0, int(context_lines))
    max_chars = max(1000, int(max_chars))
    critical_re = re.compile(
        r"(error|exception|traceback|caused by|failed|failure|timeout|reset by peer|connection reset|refused|unavailable|nullpointer|broken pipe)",
        re.IGNORECASE,
    )
    stack_re = re.compile(r"^\s+(at\s+[\w.$]+\(|File\s+\"|\.\.\.\s+\d+\s+more)")

    selected_indexes = set()
    anchor_indexes = [index for index, line in enumerate(lines) if critical_re.search(line)]
    for index in anchor_indexes:
        for nearby in range(max(0, index - context_lines), min(len(lines), index + context_lines + 1)):
            selected_indexes.add(nearby)

    # Keep stack continuation lines following selected error ranges, even if they exceed the fixed window a little.
    for index in list(selected_indexes):
        cursor = index + 1
        while cursor < len(lines) and stack_re.search(lines[cursor]):
            selected_indexes.add(cursor)
            cursor += 1

    if not selected_indexes:
        warning_indexes = [index for index, line in enumerate(lines) if re.search(r"\bwarn(?:ing)?\b", line, re.IGNORECASE)]
        for index in warning_indexes[:5]:
            for nearby in range(max(0, index - context_lines), min(len(lines), index + context_lines + 1)):
                selected_indexes.add(nearby)

    if not selected_indexes:
        selected_indexes.update(range(min(len(lines), context_lines * 2 + 1 or 20)))

    excerpt_lines = []
    current_len = 0
    previous_index = None
    for index in sorted(selected_indexes):
        if previous_index is not None and index > previous_index + 1:
            separator = f"... skipped {index - previous_index - 1} lines ..."
            if current_len + len(separator) + 1 <= max_chars:
                excerpt_lines.append(separator)
                current_len += len(separator) + 1
        numbered_line = f"{index + 1}: {lines[index]}"
        if current_len + len(numbered_line) + 1 > max_chars and excerpt_lines:
            excerpt_lines.append("... truncated by LOG_CONTEXT_MAX_CHARS ...")
            break
        excerpt_lines.append(numbered_line)
        current_len += len(numbered_line) + 1
        previous_index = index

    return "\n".join(excerpt_lines)


def build_log_analysis_prompt(log_content):
    context_lines, max_chars = get_error_context_settings()
    relevant_context = extract_relevant_log_context(log_content, context_lines, max_chars)
    return (
        "\u8bf7\u57fa\u4e8e\u3010\u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u53ca\u4e0a\u4e0b\u6587\u3011\u505a\u521d\u6b65\u5206\u6790\uff0c\u4e0d\u8981\u53ea\u6839\u636e ERROR \u5355\u884c\u4e0b\u7ed3\u8bba\u3002\n"
        f"\u540e\u7aef\u5df2\u4ece\u5b8c\u6574\u65e5\u5fd7\u4e0a\u4e0b\u6587\u4e2d\u63d0\u53d6\u9519\u8bef/\u5f02\u5e38\u5173\u952e\u884c\u53ca\u524d\u540e\u7ea6 {context_lines} \u884c\u4e0a\u4e0b\u6587\uff0c\u4ee5\u4fbf\u7ed3\u5408\u65f6\u5e8f\u548c\u8bf7\u6c42\u94fe\u8def\u5224\u65ad\u3002\n"
        "\u5206\u6790\u65f6\u9700\u8981\u540c\u65f6\u5173\u6ce8 INFO\u3001WARN\u3001DEBUG\u3001ERROR \u4ee5\u53ca\u9519\u8bef\u524d\u540e\u7684\u8bf7\u6c42\u94fe\u8def\u3001\u72b6\u6001\u53d8\u5316\u3001\u8017\u65f6\u3001\u91cd\u8bd5\u3001\u8fde\u63a5\u3001\u914d\u7f6e\u52a0\u8f7d\u7b49\u4e0a\u4e0b\u6587\u3002\n"
        "\u8bf7\u5224\u65ad\u95ee\u9898\u53ef\u80fd\u6765\u81ea\u4ee3\u7801\u3001\u914d\u7f6e\u3001\u7f51\u7edc\u3001\u6570\u636e\u3001\u4f9d\u8d56/\u7b2c\u4e09\u65b9\u670d\u52a1\u3001\u8d44\u6e90\u6216\u672a\u77e5\u3002\n\n"
        f"\u3010\u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u53ca\u4e0a\u4e0b\u6587\u3011\n{relevant_context}"
    )


def build_compact_log_context(log_content, max_chars=None):
    context_lines, default_max_chars = get_error_context_settings()
    max_chars = max_chars or default_max_chars
    relevant_context = extract_relevant_log_context(log_content, context_lines, max_chars)
    return (
        "\u3010\u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u53ca\u4e0a\u4e0b\u6587\u3011\n"
        "\u4ee5\u4e0b\u4e3a\u4ece\u5b8c\u6574\u65e5\u5fd7\u4e2d\u63d0\u53d6\u7684\u9519\u8bef/\u5f02\u5e38\u5173\u952e\u6bb5\u548c\u524d\u540e\u4e0a\u4e0b\u6587\uff0c\u7528\u4e8e\u7ed3\u5408\u4ee3\u7801\u5feb\u901f\u5b9a\u4f4d\u3002\n"
        f"{relevant_context}"
    )

def analyze_log_with_deepseek(log_content):
    logging.info("==> \u8fdb\u5165 analyze_log_with_AI")
    try:
        logging.info("\u8c03\u7528 AI API \u8fdb\u884c\u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u5206\u6790")
        system_prompt = "\u4f60\u662f\u4e00\u4e2a\u65e5\u5fd7\u5206\u6790\u4e13\u5bb6\uff0c\u64c5\u957f\u7ed3\u5408\u5b8c\u6574\u4e0a\u4e0b\u6587\u8bc6\u522b\u6545\u969c\u94fe\u8def\uff0c\u800c\u4e0d\u662f\u53ea\u770b\u5355\u4e2a\u9519\u8bef\u884c\u3002"
        result = call_ai_model(system_prompt, build_log_analysis_prompt(log_content))
        logging.info("AI \u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u5206\u6790\u6210\u529f")
        return result
    except Exception as e:
        logging.exception(f"\u8c03\u7528 AI \u65e5\u5fd7\u5206\u6790\u5931\u8d25: {e}")
        return None


def guess_image_mime_type(image_path):
    suffix = os.path.splitext(str(image_path or ""))[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "image/png")


def build_image_data_url(image_path):
    with open(image_path, "rb") as file_obj:
        encoded = base64.b64encode(file_obj.read()).decode("ascii")
    return f"data:{guess_image_mime_type(image_path)};base64,{encoded}"


def call_ai_multimodal_model(system_prompt, user_prompt, image_data_url):
    api_key = app.config.get("OPENAI_KEY")
    base_url = app.config.get("OPENAI_URL")
    model = app.config.get("OPENAI_MODEL", "deepseek-chat")
    api_style = str(app.config.get("OPENAI_API_STYLE", "chat") or "chat").lower()
    if not api_key or not base_url:
        raise ValueError("API Key \u6216 Base URL \u672a\u914d\u7f6e")

    image_data_urls = image_data_url if isinstance(image_data_url, list) else [image_data_url]
    image_data_urls = [item for item in image_data_urls if item]
    logging.info("\u5f00\u59cb\u8c03\u7528\u591a\u6a21\u6001 AI\uff1amodel=%s, style=%s", model, api_style)
    client = OpenAI(api_key=api_key, base_url=base_url)
    if api_style in ("response", "responses"):
        content = [{"type": "input_text", "text": user_prompt}]
        content.extend({"type": "input_image", "image_url": image_url} for image_url in image_data_urls)
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": content,
                },
            ],
        )
        return extract_responses_text(response)

    content = [{"type": "text", "text": user_prompt}]
    content.extend({"type": "image_url", "image_url": {"url": image_url}} for image_url in image_data_urls)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": content,
            },
        ],
        stream=False,
    )
    return response.choices[0].message.content


def normalize_image_analysis(image_tag, payload, image_description=""):
    data = payload if isinstance(payload, dict) else {}
    text_candidates = [
        data.get("extracted_text"),
        data.get("ocr_text"),
        data.get("text"),
    ]
    extracted_text = next((str(item).strip() for item in text_candidates if str(item or "").strip()), "")
    summary = str(data.get("summary") or data.get("screen_summary") or data.get("error_summary") or "").strip()
    keywords = data.get("keywords") if isinstance(data.get("keywords"), list) else []
    components = data.get("components") if isinstance(data.get("components"), list) else []
    business_context = data.get("business_context") if isinstance(data.get("business_context"), dict) else {}
    missing_context = data.get("missing_context") if isinstance(data.get("missing_context"), list) else []
    scene_summary = str(data.get("scene_summary") or business_context.get("scene_summary") or "").strip()
    business_domain = str(data.get("business_domain") or business_context.get("business_domain") or "").strip()
    page_name = str(data.get("page_name") or business_context.get("page_name") or "").strip()
    user_action = str(data.get("user_action") or business_context.get("user_action") or "").strip()
    error_message = str(data.get("error_message") or business_context.get("error_message") or "").strip()
    visible_fields = data.get("visible_fields") if isinstance(data.get("visible_fields"), list) else []
    candidate_apis = data.get("candidate_apis") if isinstance(data.get("candidate_apis"), list) else []
    candidate_code_keywords = (
        data.get("candidate_code_keywords") if isinstance(data.get("candidate_code_keywords"), list) else []
    )
    if image_tag == "business_image":
        keywords = [
            *keywords,
            business_domain,
            page_name,
            user_action,
            error_message,
            *visible_fields,
            *candidate_apis,
            *candidate_code_keywords,
        ]
    analysis_text = build_image_analysis_context(
        {
            "image_tag": image_tag,
            "summary": summary,
            "extracted_text": extracted_text,
            "keywords": keywords,
            "components": components,
            "scene_summary": scene_summary,
            "business_domain": business_domain,
            "page_name": page_name,
            "user_action": user_action,
            "error_message": error_message,
            "visible_fields": visible_fields,
            "candidate_apis": candidate_apis,
            "candidate_code_keywords": candidate_code_keywords,
            "missing_context": missing_context,
        },
        image_description,
    )
    detected_components = detect_error_components(
        "\n".join([summary, extracted_text, " ".join(str(item) for item in keywords), image_description])
    )
    merged_components = []
    for item in [*components, *detected_components]:
        normalized = str(item or "").strip().lower()
        if normalized and normalized not in merged_components:
            merged_components.append(normalized)
    return {
        "image_tag": image_tag,
        "image_description": image_description,
        "summary": summary,
        "extracted_text": extracted_text,
        "keywords": [str(item).strip() for item in keywords if str(item).strip()],
        "components": merged_components,
        "scene_summary": scene_summary,
        "business_domain": business_domain,
        "page_name": page_name,
        "user_action": user_action,
        "error_message": error_message,
        "visible_fields": [str(item).strip() for item in visible_fields if str(item).strip()],
        "candidate_apis": [str(item).strip() for item in candidate_apis if str(item).strip()],
        "candidate_code_keywords": [str(item).strip() for item in candidate_code_keywords if str(item).strip()],
        "missing_context": missing_context,
        "analysis_text": analysis_text,
    }


def analyze_uploaded_image(image_path, image_tag, image_description=""):
    image_paths = image_path if isinstance(image_path, list) else [image_path]
    image_paths = [path for path in image_paths if path]
    image_data_url = [build_image_data_url(path) for path in image_paths]
    image_type_label = "\u65e5\u5fd7\u622a\u56fe" if image_tag == "log_image" else "\u4e1a\u52a1\u622a\u56fe"
    business_schema = ""
    if image_tag == "business_image":
        business_schema = (
            "业务截图必须额外识别业务场景，并返回字段：scene_summary、business_domain、page_name、"
            "user_action、error_message、visible_fields、candidate_apis、candidate_code_keywords、missing_context。\n"
            "missing_context 用于提醒用户补充上下游信息；如果截图无法确认请求参数、业务ID、服务日志、"
            "DB/Redis/ES/Kafka/RPC 下游返回，就必须列出 direction(upstream/downstream/current)、"
            "title、reason、needed、how_to_get。\n"
            "多张图片需要按上传顺序理解成同一个业务流程，不要只分析第一张。\n"
        )
    image_description_text = image_description or "\u65e0"
    prompt = (
        f"\u8bf7\u8bc6\u522b\u8fd9\u5f20{image_type_label}\uff0c\u5e76\u4e14\u53ea\u8fd4\u56de JSON\u3002\n"
        "JSON \u5fc5\u987b\u5305\u542b\uff1asummary\u3001extracted_text\u3001keywords\u3001components\u3002\n"
        "\u5982\u679c\u662f\u65e5\u5fd7\u622a\u56fe\uff0c\u8bf7\u5c3d\u91cf\u63d0\u53d6\u9519\u8bef\u65e5\u5fd7\u3001\u5f02\u5e38\u5806\u6808\u3001\u9519\u8bef\u5173\u952e\u5b57\u3002\n"
        "\u5982\u679c\u662f\u4e1a\u52a1\u622a\u56fe\uff0c\u8bf7\u63d0\u53d6\u9875\u9762\u63d0\u793a\u3001\u5173\u952e\u4e1a\u52a1\u72b6\u6001\u3001\u62a5\u9519\u6587\u6848\uff0c\u4ee5\u53ca\u53ef\u7528\u4e8e\u4ee3\u7801\u6392\u67e5\u7684\u5173\u952e\u5b57\u3002\n"
        f"{business_schema}"
        f"\u7528\u6237\u8865\u5145\u63cf\u8ff0\uff1a{image_description_text}"
    )
    logging.info("\u5f00\u59cb\u8bc6\u522b\u4e0a\u4f20\u56fe\u7247\uff1apath=%s, image_tag=%s", image_paths, image_tag)
    result = call_ai_multimodal_model("\u4f60\u662f\u4e00\u4e2a\u56fe\u7247\u6545\u969c\u8bc6\u522b\u4e13\u5bb6\u3002", prompt, image_data_url)
    payload = extract_json_object(result)
    logging.info("\u56fe\u7247\u8bc6\u522b\u5b8c\u6210\uff1apayload_keys=%s", list(payload.keys()) if isinstance(payload, dict) else [])
    return normalize_image_analysis(image_tag, payload, image_description=image_description)


def build_image_analysis_context(image_analysis, image_description=""):
    image_tag = str((image_analysis or {}).get("image_tag") or "").strip().lower()
    image_type_label = "\u65e5\u5fd7\u622a\u56fe" if image_tag == "log_image" else "\u4e1a\u52a1\u622a\u56fe"
    summary = str((image_analysis or {}).get("summary") or "").strip()
    extracted_text = str((image_analysis or {}).get("extracted_text") or "").strip()
    keywords = image_analysis.get("keywords") or []
    components = image_analysis.get("components") or []
    business_fields = [
        ("业务场景", image_analysis.get("scene_summary")),
        ("业务域", image_analysis.get("business_domain")),
        ("页面名称", image_analysis.get("page_name")),
        ("用户动作", image_analysis.get("user_action")),
        ("页面报错", image_analysis.get("error_message")),
    ]
    lines = [f"\u56fe\u7247\u7c7b\u578b: {image_type_label}"]
    if image_description:
        lines.append(f"\u7528\u6237\u63cf\u8ff0: {image_description}")
    for label, value in business_fields:
        value = str(value or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    if summary:
        lines.append(f"\u56fe\u7247\u6458\u8981: {summary}")
    if extracted_text:
        lines.append(f"\u8bc6\u522b\u6587\u672c: {extracted_text}")
    if image_analysis.get("visible_fields"):
        lines.append("页面字段: " + ", ".join(str(item) for item in image_analysis.get("visible_fields") or []))
    if image_analysis.get("candidate_apis"):
        lines.append("候选接口: " + ", ".join(str(item) for item in image_analysis.get("candidate_apis") or []))
    if image_analysis.get("candidate_code_keywords"):
        lines.append("候选代码关键词: " + ", ".join(str(item) for item in image_analysis.get("candidate_code_keywords") or []))
    if keywords:
        lines.append("\u5173\u952e\u8bcd: " + ", ".join(str(item) for item in keywords))
    if components:
        lines.append("\u7591\u4f3c\u7ec4\u4ef6: " + ", ".join(str(item) for item in components))
    missing_context = image_analysis.get("missing_context") or []
    if missing_context:
        lines.append("需要补充的信息:")
        for item in missing_context:
            if not isinstance(item, dict):
                continue
            direction = item.get("direction") or "unknown"
            title = item.get("title") or "未命名信息缺口"
            needed = item.get("needed") or []
            how_to_get = item.get("how_to_get") or []
            lines.append(f"- {direction}: {title}")
            if item.get("reason"):
                lines.append(f"  原因: {item.get('reason')}")
            if needed:
                lines.append("  需要: " + ", ".join(str(value) for value in needed))
            if how_to_get:
                lines.append("  获取方式: " + ", ".join(str(value) for value in how_to_get))
    return "\n".join(lines)


def call_ai_model(system_prompt, user_prompt):
    api_key = app.config.get("OPENAI_KEY")
    base_url = app.config.get("OPENAI_URL")
    model = app.config.get("OPENAI_MODEL", "deepseek-chat")
    api_style = app.config.get("OPENAI_API_STYLE", "chat")
    api_style = str(api_style or "chat").lower()
    logging.info(
        "AI \u914d\u7f6e\u68c0\u67e5 - API_KEY: %s, BASE_URL: %s, MODEL: %s, STYLE: %s",
        "\u5b58\u5728" if api_key else "\u7f3a\u5931",
        base_url,
        model,
        api_style,
    )

    if not api_key or not base_url:
        raise ValueError("API Key \u6216 Base URL \u672a\u914d\u7f6e")

    client = OpenAI(api_key=api_key, base_url=base_url)
    if api_style in ("response", "responses"):
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return extract_responses_text(response)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        stream=False,
    )
    return response.choices[0].message.content


def extract_responses_text(response):
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    if isinstance(response, dict):
        output_text = response.get("output_text")
        if output_text:
            return output_text
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    text_parts = []
    for item in output or []:
        content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
        for block in content or []:
            if isinstance(block, dict):
                text = block.get("text")
            else:
                text = getattr(block, "text", None)
            if text:
                text_parts.append(text)
    return "\n".join(text_parts).strip()

def extract_error_info_from_log(log_content):
    logging.info("==> \u8fdb\u5165 extract_error_info_from_log")
    error_info = []
    error_matches = re.findall(
        r'(?:^|\n)\s*([A-Za-z_][\w\.]*(?:Exception|Error):\s*.*)',
        log_content,
    )
    if error_matches:
        error_message = error_matches[-1].strip()
    else:
        error_line = re.search(r'(Exception|Error):\s*(.*)', log_content)
        error_message = error_line.group(0).strip() if error_line else "\u672a\u77e5\u9519\u8bef"
    logging.info("\u5339\u914d\u5230\u7684\u9519\u8bef\u63cf\u8ff0\uff1a%s", error_message)

    python_frames = re.findall(
        r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+[^\n]+)?',
        log_content,
    )
    if python_frames:
        for file_name, line_str in python_frames:
            error_info.append({
                "file": os.path.basename(file_name),
                "line": int(line_str),
                "error": error_message,
            })
        logging.info("\u63d0\u53d6\u5230 Python \u5806\u6808\u4fe1\u606f\uff1acount=%s", len(error_info))
        return error_info

    stack_match = re.search(r'\s+at\s+[\w\.]+\(([\w\.]+):(\d+)\)', log_content)
    if stack_match:
        file_name = stack_match.group(1)
        line_str = stack_match.group(2)
        try:
            line_number = int(line_str)
        except ValueError:
            logging.warning("\u5806\u6808\u884c\u53f7\u8f6c\u6362\u5931\u8d25\uff0c\u9ed8\u8ba4\u4f7f\u7528 1")
            line_number = 1
        logging.info("\u63d0\u53d6\u5230\u5806\u6808\u4fe1\u606f\uff1a\u6587\u4ef6 %s, \u884c\u53f7 %s", file_name, line_number)
        error_info.append({
            "file": file_name,
            "line": line_number,
            "error": error_message
        })
    else:
        logging.info("\u672a\u5339\u914d\u5230\u5806\u6808\u4fe1\u606f\uff0c\u4ec5\u4fdd\u7559\u9519\u8bef\u63cf\u8ff0")
        error_info.append({
            "file": None,
            "line": None,
            "error": error_message
        })
    return error_info


def resolve_file_paths(repo_path, error_info):
    logging.info("==> \u8fdb\u5165 resolve_file_paths")
    resolved = []
    for err in error_info:
        target = err["file"]
        found_path = None
        logging.info("\u5f00\u59cb\u5728\u4ed3\u5e93\u4e2d\u67e5\u627e\u76ee\u6807\u6587\u4ef6\uff1arepo=%s, target=%s", repo_path, target)
        for root, _, files in os.walk(repo_path):
            if target in files:
                found_path = os.path.join(root, target)
                logging.info("\u627e\u5230\u76ee\u6807\u6587\u4ef6\uff1a%s", found_path)
                break
        if found_path:
            resolved.append({
                "file": found_path,
                "line": err["line"],
                "error": err["error"]
            })
        else:
            logging.warning("\u76ee\u6807\u6587\u4ef6\u672a\u5728\u4ed3\u5e93\u4e2d\u627e\u5230\uff1arepo=%s, target=%s", repo_path, target)
    return resolved


def extract_code_snippets(resolved_errors):
    logging.info("==> \u8fdb\u5165 extract_code_snippets")
    code_snippets = []
    for err in resolved_errors:
        file_path = err.get("file")
        line_number = err.get("line")
        logging.info("\u51c6\u5907\u63d0\u53d6\u4ee3\u7801\u7247\u6bb5\uff1afile=%s, line=%s", file_path, line_number)
        if not file_path or not os.path.exists(file_path):
            logging.warning("\u4ee3\u7801\u6587\u4ef6\u4e0d\u5b58\u5728\uff0c\u8df3\u8fc7\u63d0\u53d6\uff1a%s", file_path)
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as file_obj:
                lines = file_obj.readlines()
            start_line = max(1, line_number - 5)
            end_line = min(len(lines), line_number + 4)
            snippet_lines = lines[start_line - 1:end_line]
            snippet = "".join(snippet_lines)
            numbered_snippet = format_numbered_snippet(snippet_lines, start_line, line_number)
            try:
                display_file = os.path.relpath(file_path)
            except ValueError:
                display_file = file_path
            logging.info(
                "\u4ee3\u7801\u7247\u6bb5\u63d0\u53d6\u6210\u529f\uff1afile=%s, target_line=%s, range=%s-%s",
                file_path,
                line_number,
                start_line,
                end_line,
            )
            code_snippets.append({
                "file": display_file,
                "line": line_number,
                "start_line": start_line,
                "end_line": end_line,
                "snippet": snippet,
                "numbered_snippet": numbered_snippet,
                "reason": err.get("reason"),
                "component": err.get("component"),
            })
        except Exception as exc:
            logging.warning("\u8bfb\u53d6\u4ee3\u7801\u6587\u4ef6\u5931\u8d25\uff1afile=%s, error=%s", file_path, exc)
    return code_snippets


def detect_error_components(log_content):
    text = str(log_content or "").lower()
    components = []
    for component, patterns in COMPONENT_USAGE_PATTERNS.items():
        if any(pattern in text for pattern in patterns):
            components.append(component)
    return components


def find_component_code_usages(repo_path, components, max_matches=8):
    if not repo_path or not os.path.exists(repo_path) or not components:
        return []

    matches = []
    seen = set()
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [name for name in dirs if name not in SKIP_CODE_SEARCH_DIRS]
        for filename in files:
            suffix = os.path.splitext(filename)[1].lower()
            if suffix not in SOURCE_CODE_SUFFIXES:
                continue

            file_path = os.path.join(root, filename)
            lines = read_text_lines(file_path)
            if not lines:
                continue

            for line_index, line in enumerate(lines, start=1):
                lowered_line = line.lower()
                for component in components:
                    patterns = COMPONENT_USAGE_PATTERNS.get(component, [])
                    if not any(pattern in lowered_line for pattern in patterns):
                        continue

                    key = (file_path, line_index, component)
                    if key in seen:
                        continue
                    seen.add(key)
                    matches.append({
                        "file": file_path,
                        "line": line_index,
                        "error": f"{component} \u8c03\u7528\u4f4d\u7f6e",
                        "component": component,
                        "reason": f"\u65e5\u5fd7\u4e2d\u51fa\u73b0 {component.upper()} \u76f8\u5173\u62a5\u9519\uff0c\u5df2\u5728\u4ee3\u7801\u4ed3\u5e93\u4e2d\u5b9a\u4f4d\u5230\u8be5\u7ec4\u4ef6\u7684\u8c03\u7528\u4f4d\u7f6e\u3002",
                    })
                    if len(matches) >= max_matches:
                        return extract_code_snippets(matches)
    return extract_code_snippets(matches)


def read_text_lines(file_path):
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            with open(file_path, "r", encoding=encoding) as file_obj:
                return file_obj.readlines()
        except UnicodeDecodeError:
            continue
        except OSError:
            return []
    return []


def merge_code_snippets(*snippet_groups):
    merged = []
    seen = set()
    for snippets in snippet_groups:
        for snippet in snippets or []:
            key = (snippet.get("file"), snippet.get("line"), snippet.get("component"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(snippet)
    return merged


def format_numbered_snippet(snippet_lines, start_line, target_line):
    formatted_lines = []
    for offset, raw_line in enumerate(snippet_lines):
        line_number = start_line + offset
        marker = ">>" if line_number == target_line else "  "
        formatted_lines.append(f"{marker} {line_number:4d} | {raw_line.rstrip()}")
    return "\n".join(formatted_lines)


def build_code_findings(code_snippets):
    findings = []
    for snippet in code_snippets or []:
        if not isinstance(snippet, dict):
            continue
        file_path = snippet.get("file") or "\u672a\u77e5\u6587\u4ef6"
        line = snippet.get("line")
        code = snippet.get("numbered_snippet") or snippet.get("snippet") or ""
        if not code:
            continue
        reason = snippet.get("reason") or f"\u65e5\u5fd7\u5806\u6808\u5b9a\u4f4d\u5230 {file_path} \u7b2c {line} \u884c\uff0c\u9700\u4f18\u5148\u68c0\u67e5\u8be5\u884c\u9644\u8fd1\u4ee3\u7801\u3002"
        findings.append({
            "file": file_path,
            "line": line,
            "reason": reason,
            "code": code,
            "component": snippet.get("component"),
        })
    return findings


def analyze_code_with_deepseek(log_content, log_analysis, code_snippets, image_analysis=None):
    logging.info("==> \u8fdb\u5165 analyze_code_with_deepseek")
    context_lines = []
    for snippet in code_snippets:
        context_lines.append(
            f"\u6587\u4ef6\uff1a{snippet['file']} \u7b2c {snippet['line']} \u884c\u9644\u8fd1\n```\n{snippet.get('numbered_snippet') or snippet['snippet']}\n```"
        )
    context = "\n".join(context_lines)
    fallback_context = "\u672a\u5b9a\u4f4d\u5230\u76f8\u5173\u4ee3\u7801\u7247\u6bb5"
    log_context = build_compact_log_context(log_content)
    image_context = ""
    if image_analysis:
        image_context = f"\n\n\u3010\u56fe\u7247\u8bc6\u522b\u6458\u8981\u3011\n{build_image_analysis_context(image_analysis, image_analysis.get('image_description', ''))}"

    prompt = (
        "\u8bf7\u57fa\u4e8e\u3010\u5b8c\u6574\u65e5\u5fd7\u4e0a\u4e0b\u6587\u3011\u3001\u3010\u65e5\u5fd7\u521d\u6b65\u5206\u6790\u3011\u548c\u3010\u76f8\u5173\u4ee3\u7801\u7247\u6bb5\u3011\u505a\u6700\u7ec8\u7ed3\u8bba\u3002\n"
        "\u91cd\u8981\u539f\u5219\uff1a\u4e0d\u8981\u53ea\u6839\u636e ERROR \u884c\u5224\u65ad\uff1b\u5fc5\u987b\u7ed3\u5408\u9519\u8bef\u524d\u540e\u7684 INFO/WARN/DEBUG\u3001\u8bf7\u6c42\u94fe\u8def\u3001\u914d\u7f6e\u52a0\u8f7d\u3001\u8fde\u63a5\u72b6\u6001\u3001\u91cd\u8bd5\u3001\u8017\u65f6\u548c\u8d44\u6e90\u53d8\u5316\u3002\n"
        "\u4ee3\u7801\u7247\u6bb5\u662f\u5173\u952e\u8bc1\u636e\uff0c\u4f46\u6ca1\u6709\u4ee3\u7801\u8bc1\u636e\u5e76\u4e0d\u4ee3\u8868\u4e00\u5b9a\u4e0d\u662f\u914d\u7f6e\u3001\u7f51\u7edc\u3001\u6570\u636e\u3001\u4f9d\u8d56\u6216\u8d44\u6e90\u95ee\u9898\u3002\n"
        "\u5982\u679c\u5224\u65ad\u4e3a\u4ee3\u7801\u95ee\u9898\uff0c\u5fc5\u987b\u6307\u51fa\u5177\u4f53\u6587\u4ef6\u3001\u884c\u53f7\u3001\u76f8\u5173\u4ee3\u7801\u5757\u548c\u4e3a\u4ec0\u4e48\u8fd9\u6bb5\u4ee3\u7801\u4f1a\u89e6\u53d1\u65e5\u5fd7\u4e2d\u7684\u73b0\u8c61\u3002\n"
        "\u5982\u679c\u5224\u65ad\u53ef\u80fd\u662f\u914d\u7f6e/\u7f51\u7edc/\u6570\u636e/\u4f9d\u8d56/\u8d44\u6e90\u95ee\u9898\uff0c\u4e5f\u8981\u8bf4\u660e\u65e5\u5fd7\u4f9d\u636e\u4ee5\u53ca\u9700\u8981\u8865\u5145\u68c0\u67e5\u7684\u914d\u7f6e\u9879\u3001\u7f51\u7edc\u94fe\u8def\u3001\u6570\u636e\u6837\u672c\u6216\u5916\u90e8\u670d\u52a1\u3002\n"
        "\u8bf7\u53ea\u8fd4\u56de JSON\uff0c\u4e0d\u8981\u8fd4\u56de Markdown\u3002JSON \u5b57\u6bb5\u5fc5\u987b\u5305\u542b\uff1a\n"
        "- issue_category: code_issue/data_issue/config_issue/network_issue/dependency_issue/resource_issue/unknown \u4e4b\u4e00\n"
        "- conclusion_summary: \u4e00\u53e5\u8bdd\u7ed3\u8bba\n"
        "- root_cause: \u6839\u56e0\u8bf4\u660e\uff0c\u5fc5\u987b\u8bf4\u660e\u7ed3\u8bba\u662f\u5426\u7531\u4ee3\u7801\u7247\u6bb5\u652f\u6491\n"
        "- solution: \u5904\u7406\u5efa\u8bae\n"
        "- confidence: 0 \u5230 1 \u7684\u6570\u5b57\n"
        "- possible_causes: \u5bf9\u8c61\uff0c\u5fc5\u987b\u5305\u542b code_issue/config_issue/network_issue/data_issue/dependency_issue/resource_issue \u516d\u4e2a\u952e\uff1b\u6bcf\u4e2a\u952e\u7684\u503c\u90fd\u662f {possible: boolean, confidence: 0\u52301, reason: string}\n"
        "- query_commands: \u5b57\u7b26\u4e32\u6570\u7ec4\uff0c\u7ed9\u51fa\u53ef\u76f4\u63a5\u6267\u884c\u7684\u6392\u67e5/\u67e5\u8be2\u547d\u4ee4\uff0c\u6bd4\u5982 grep\u3001redis-cli\u3001mysql\u3001curl\u3001kubectl \u7b49\n"
        "- fix_commands: \u5b57\u7b26\u4e32\u6570\u7ec4\uff0c\u7ed9\u51fa\u53ef\u76f4\u63a5\u6267\u884c\u7684\u4fee\u590d/\u7f13\u89e3\u547d\u4ee4\uff0c\u5982\u679c\u4e0d\u5e94\u76f4\u63a5\u6267\u884c\u5219\u7ed9\u51fa\u5b89\u5168\u66ff\u4ee3\u65b9\u6848\n"
        "- evidence: \u5b57\u7b26\u4e32\u6570\u7ec4\uff0c\u5217\u51fa\u5224\u65ad\u4f9d\u636e\uff0c\u4f18\u5148\u5305\u542b\u65e5\u5fd7\u4e0a\u4e0b\u6587\u3001\u4ee3\u7801\u6587\u4ef6\u3001\u884c\u53f7\u3001\u4ee3\u7801\u7247\u6bb5\u8bf4\u660e\n\n"
        f"{log_context}\n\n"
        f"\u3010\u65e5\u5fd7\u521d\u6b65\u5206\u6790\u3011\n{log_analysis}"
        f"{image_context}\n\n"
        f"\u3010\u76f8\u5173\u4ee3\u7801\u7247\u6bb5\u3011\n{context or fallback_context}"
    )
    logging.info(
        "\u7efc\u5408\u5206\u6790\u63d0\u793a\u8bcd\u5df2\u751f\u6210\uff1acode_snippet_count=%s, has_image_context=%s, log_context_chars=%s",
        len(code_snippets),
        bool(image_analysis),
        len(log_context),
    )

    try:
        logging.info("\u8c03\u7528 AI \u6267\u884c\u4ee3\u7801\u4e0e\u65e5\u5fd7\u7684\u7efc\u5408\u5206\u6790")
        result = call_ai_model("\u4f60\u662f\u4e00\u4e2a\u7ecf\u9a8c\u4e30\u5bcc\u7684\u540e\u7aef\u6545\u969c\u5b9a\u4f4d\u4e13\u5bb6\u3002", prompt)
        logging.info("AI \u7efc\u5408\u5206\u6790\u6210\u529f")
        return result
    except Exception as exc:
        logging.exception("\u8c03\u7528 AI \u8fdb\u884c\u4ee3\u7801\u5206\u6790\u5931\u8d25\uff1a%s", exc)
        return "\u4ee3\u7801\u5206\u6790\u5931\u8d25\uff0c\u65e0\u6cd5\u5b9a\u4f4d\u5177\u4f53\u9519\u8bef"


def insert_query_record(data, answer_status, **extra):
    try:
        query_record = QueryRecord(
            product_id=data.get("productId"),
            module_id=data.get("moduleId"),
            log_id=data.get("log_id") or data.get("logId"),
            log_file_path=data.get("file_path"),
            branch_url=data.get("branchAddress"),
            branch_version=data.get("tagVersion"),
            created_at=datetime.utcnow(),
            answer=answer_status,
            status=extra.get("status") or ("success" if answer_status == 0 else "failed"),
            log_hash=extra.get("log_hash"),
            error_fingerprint=extra.get("error_fingerprint"),
            duration_ms=extra.get("duration_ms"),
            model_name=app.config.get("OPENAI_MODEL"),
            hit_cache=bool(extra.get("hit_cache", False)),
            knowledge_case_id=extra.get("knowledge_case_id"),
        )
        db.session.add(query_record)
        db.session.commit()
        logging.info("\u67e5\u8be2\u8bb0\u5f55\u5199\u5165\u6210\u529f\uff1a%s", query_record)
    except Exception as exc:
        logging.exception("\u63d2\u5165\u67e5\u8be2\u8bb0\u5f55\u5931\u8d25\uff1a%s", exc)
        db.session.rollback()
