import hashlib
import logging
import os
import shutil

from extensions import celery


def report_progress(task, stage, stage_label, stage_percent, percent, message=None):
    meta = {
        "stage": stage,
        "stage_label": stage_label,
        "stage_percent": int(stage_percent),
        "percent": int(percent),
        "message": message or f"{stage_label} {int(stage_percent)}%",
    }
    task.update_state(state="PROGRESS", meta=meta)
    return meta


def build_analysis_evidence(error_info, resolved_errors, code_snippets):
    snippet_files = []
    for snippet in code_snippets or []:
        file_path = snippet.get("file") if isinstance(snippet, dict) else None
        if file_path and file_path not in snippet_files:
            snippet_files.append(file_path)

    return {
        "used_code_context": bool(code_snippets),
        "error_info_count": len(error_info or []),
        "resolved_file_count": len(resolved_errors or []),
        "code_snippet_count": len(code_snippets or []),
        "code_snippet_files": snippet_files,
    }


def merge_component_candidates(*groups):
    items = []
    for group in groups:
        for item in group or []:
            normalized = str(item or "").strip().lower()
            if normalized and normalized not in items:
                items.append(normalized)
    return items


def _path_is_under(path, directory):
    if not path or not directory:
        return False
    try:
        real_path = os.path.realpath(path)
        real_directory = os.path.realpath(directory)
        return os.path.commonpath([real_path, real_directory]) == real_directory
    except (OSError, ValueError):
        return False


def _default_upload_dir():
    try:
        from flask import current_app

        return current_app.config.get("LOCAL_STORAGE_DIR", "/data/upload")
    except RuntimeError:
        return "/data/upload"


def cleanup_analysis_files(data, repo_path=None, task_id=None, upload_dir=None, repo_base_dir="/tmp/log-analyzer-repos"):
    upload_dir = upload_dir or _default_upload_dir()
    uploaded_files = []
    if isinstance(data, dict):
        uploaded_files = [path for path in (data.get("file_paths") or []) if path]
        if data.get("file_path") and data.get("file_path") not in uploaded_files:
            uploaded_files.insert(0, data.get("file_path"))

    result = {
        "uploaded_file_removed": False,
        "uploaded_file_removed_count": 0,
        "repo_workspace_removed": False,
        "uploaded_file_path": data.get("file_path") if isinstance(data, dict) else None,
        "uploaded_file_paths": uploaded_files,
        "repo_workspace_path": None,
    }

    for uploaded_file in uploaded_files:
        if not (uploaded_file and _path_is_under(uploaded_file, upload_dir) and os.path.isfile(uploaded_file)):
            continue
        try:
            os.remove(uploaded_file)
            result["uploaded_file_removed"] = True
            result["uploaded_file_removed_count"] += 1
        except OSError:
            logging.exception("?????????%s", uploaded_file)

    if repo_path and task_id:
        real_repo_path = os.path.realpath(repo_path)
        real_repo_base = os.path.realpath(repo_base_dir)
        task_workspace = os.path.realpath(os.path.join(real_repo_base, str(task_id)))
        result["repo_workspace_path"] = task_workspace

        if (
            os.path.basename(task_workspace) == str(task_id)
            and _path_is_under(task_workspace, real_repo_base)
            and _path_is_under(real_repo_path, task_workspace)
            and os.path.isdir(task_workspace)
        ):
            try:
                shutil.rmtree(task_workspace)
                result["repo_workspace_removed"] = True
            except OSError:
                logging.exception("?? Git ?????????%s", task_workspace)

    return result


@celery.task(bind=True, name="analysis.analyze_log_task")
def analyze_log_task(self, data):
    from app.analysis.routes.routes import (
        analyze_uploaded_image,
        analyze_code_with_deepseek,
        analyze_log_with_deepseek,
        build_cached_analysis_payload,
        build_code_findings,
        build_error_fingerprint,
        clone_git_repo,
        detect_error_components,
        extract_code_snippets,
        extract_error_info_from_log,
        find_component_code_usages,
        find_knowledge_case,
        insert_query_record,
        merge_code_snippets,
        parse_issue_conclusion,
        resolve_file_paths,
        upsert_knowledge_case,
    )

    task_id = self.request.id
    repo_path = None
    try:
        report_progress(self, "clone_repo_started", "代码拉取", 0, 25, "开始拉取代码 0%")
        repo_path = clone_git_repo(
            data.get("branchAddress"),
            data.get("tagVersion"),
            workspace_id=task_id,
        )
        if not repo_path:
            report_progress(self, "clone_repo_failed", "代码拉取", 100, 45, "代码拉取失败")
            insert_query_record(data, 1)
            raise RuntimeError("克隆 Git 仓库失败")
        report_progress(self, "clone_repo_done", "代码拉取", 100, 45, "代码拉取 100%")

        source_type = str(data.get("source_type") or "file").lower()
        input_path = data.get("file_path")
        input_paths = [path for path in (data.get("file_paths") or []) if path]
        if input_path and input_path not in input_paths:
            input_paths.insert(0, input_path)
        image_analysis = None
        components = []

        if source_type == "image":
            report_progress(self, "read_image_started", "图片识别", 0, 45, "开始识别图片 0%")
            if not input_paths or any(not os.path.exists(path) for path in input_paths):
                report_progress(self, "read_image_failed", "图片识别", 100, 75, "图片识别失败")
                insert_query_record(data, 1)
                raise RuntimeError("图片文件路径无效或文件不存在")
            try:
                image_analysis = analyze_uploaded_image(
                    input_paths,
                    data.get("image_tag"),
                    data.get("image_description", ""),
                )
                log_content = image_analysis.get("analysis_text") or ""
                components = merge_component_candidates(
                    image_analysis.get("components"),
                    image_analysis.get("candidate_apis"),
                    image_analysis.get("candidate_code_keywords"),
                    [
                        image_analysis.get("business_domain"),
                        image_analysis.get("page_name"),
                        image_analysis.get("user_action"),
                        image_analysis.get("error_message"),
                    ],
                    detect_error_components(log_content),
                )
            except Exception as exc:
                report_progress(self, "read_image_failed", "图片识别", 100, 75, "图片识别失败")
                insert_query_record(data, 1)
                raise RuntimeError("图片识别失败") from exc
            report_progress(self, "read_image_done", "图片识别", 100, 75, "图片识别 100%")
        else:
            report_progress(self, "read_log_started", "日志读取", 0, 55, "开始读取日志 0%")
            if not input_path or not os.path.exists(input_path):
                report_progress(self, "read_log_failed", "日志读取", 100, 60, "日志读取失败")
                insert_query_record(data, 1)
                raise RuntimeError("日志文件路径无效或文件不存在")

            try:
                with open(input_path, "r", encoding="utf-8") as file_obj:
                    log_content = file_obj.read()
            except Exception as exc:
                report_progress(self, "read_log_failed", "日志读取", 100, 60, "日志读取失败")
                insert_query_record(data, 1)
                raise RuntimeError("读取日志失败") from exc
            report_progress(self, "read_log_done", "日志读取", 100, 60, "日志读取 100%")
            components = detect_error_components(log_content)

        error_info = extract_error_info_from_log(log_content)
        error_fingerprint = build_error_fingerprint(
            data.get("productId"),
            data.get("moduleId"),
            error_info,
            data.get("branchAddress"),
            data.get("tagVersion"),
            fallback_text=log_content,
        )
        log_hash = hashlib.sha256(log_content.encode("utf-8")).hexdigest()

        knowledge_case = find_knowledge_case(data.get("productId"), data.get("moduleId"), error_fingerprint)
        if knowledge_case:
            report_progress(self, "knowledge_hit", "知识库命中", 100, 95, "命中历史知识库 100%")
            payload = build_cached_analysis_payload(knowledge_case, task_id=task_id, repo_path=repo_path)
            insert_query_record(
                data,
                0,
                status="cache_hit",
                log_hash=log_hash,
                error_fingerprint=error_fingerprint,
                hit_cache=True,
                knowledge_case_id=knowledge_case.id,
            )
            report_progress(self, "completed", "任务完成", 100, 100, "全部阶段完成 100%")
            return payload

        report_progress(self, "analyze_log_started", "日志分析", 0, 70, "开始分析日志 0%")
        log_analysis = analyze_log_with_deepseek(log_content)
        if not log_analysis:
            report_progress(self, "analyze_log_failed", "日志分析", 100, 75, "日志分析失败")
            insert_query_record(data, 1, log_hash=log_hash, error_fingerprint=error_fingerprint)
            raise RuntimeError("日志分析失败")
        report_progress(self, "analyze_log_done", "日志分析", 100, 75, "日志分析 100%")

        report_progress(self, "extract_code_started", "代码定位", 0, 85, "开始定位相关代码 0%")
        resolved_errors = resolve_file_paths(repo_path, error_info) if error_info else []
        stack_snippets = extract_code_snippets(resolved_errors)
        component_snippets = find_component_code_usages(repo_path, components)
        code_snippets = merge_code_snippets(stack_snippets, component_snippets)
        code_findings = build_code_findings(code_snippets)
        analysis_evidence = build_analysis_evidence(error_info, resolved_errors, code_snippets)
        report_progress(
            self,
            "extract_code_done",
            "代码定位",
            100,
            89,
            f"代码定位 100%，找到 {analysis_evidence['code_snippet_count']} 个代码片段",
        )

        report_progress(self, "analyze_code_started", "综合分析", 0, 95, "开始综合分析 0%")
        code_analysis = analyze_code_with_deepseek(
            log_content,
            log_analysis,
            code_snippets,
            image_analysis=image_analysis,
        )
        report_progress(self, "analyze_code_done", "综合分析", 100, 98, "综合分析 100%")

        issue_conclusion = parse_issue_conclusion(code_analysis)
        knowledge_case = None
        if code_analysis:
            knowledge_case = upsert_knowledge_case(
                data,
                error_fingerprint,
                error_info,
                log_content,
                code_snippets,
                code_analysis,
                issue_conclusion,
            )

        insert_query_record(
            data,
            0 if code_analysis else 1,
            log_hash=log_hash,
            error_fingerprint=error_fingerprint,
            hit_cache=False,
            knowledge_case_id=knowledge_case.id if knowledge_case else None,
        )
        logging.info("异步分析任务完成：%s", task_id)
        report_progress(self, "completed", "任务完成", 100, 100, "全部阶段完成 100%")

        return {
            "task_id": task_id,
            "repo_path": repo_path,
            "knowledge_hit": False,
            "knowledge_case_id": knowledge_case.id if knowledge_case else None,
            "error_fingerprint": error_fingerprint,
            "source_type": source_type,
            "image_tag": data.get("image_tag"),
            "file_paths": input_paths if source_type == "image" else None,
            "log_ids": data.get("log_ids"),
            "image_analysis": image_analysis,
            "log_analysis": log_analysis,
            "code_snippets": code_snippets,
            "code_findings": code_findings,
            "analysis_evidence": analysis_evidence,
            "issue_conclusion": issue_conclusion,
            "code_analysis": code_analysis,
        }
    finally:
        cleanup_result = cleanup_analysis_files(data, repo_path=repo_path, task_id=task_id)
        if cleanup_result.get("uploaded_file_removed") or cleanup_result.get("repo_workspace_removed"):
            logging.info("分析临时文件清理完成：%s", cleanup_result)
