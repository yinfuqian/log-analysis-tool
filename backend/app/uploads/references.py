"""references 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import os
from pathlib import Path


class AnalysisInputError(ValueError):
    """AnalysisInputError 类封装该领域对象的状态、依赖与相关行为。"""
    pass


def require_path_under(path, upload_root):
    """处理 require_path_under 对应的业务步骤，并向调用方返回所需结果。"""
    try:
        candidate = Path(path).resolve(strict=True)
        root = Path(upload_root).resolve(strict=True)
        if os.path.commonpath([str(candidate), str(root)]) != str(root):
            raise AnalysisInputError("分析文件不在受信任的上传目录中")
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, AnalysisInputError):
            raise
        raise AnalysisInputError("分析文件不存在或不可访问") from exc
    if not candidate.is_file():
        raise AnalysisInputError("分析文件不存在或不可访问")
    return str(candidate)


def resolve_analysis_inputs(data, upload_root, log_lookup):
    """解析并返回 resolve_analysis_inputs 对应的业务数据，保持现有调用约定。"""
    identifiers = data.get("log_ids") or []
    if not identifiers and data.get("log_id") is not None:
        identifiers = [data.get("log_id")]

    records = []
    if identifiers:
        for identifier in identifiers:
            record = log_lookup(identifier)
            if record is None:
                raise AnalysisInputError("找不到对应的上传记录")
            records.append(record)
    else:
        legacy_paths = [path for path in (data.get("file_paths") or []) if path]
        if data.get("file_path") and data.get("file_path") not in legacy_paths:
            legacy_paths.insert(0, data.get("file_path"))
        for path in legacy_paths:
            record = log_lookup(path)
            if record is None:
                raise AnalysisInputError("分析文件必须匹配已有上传记录")
            records.append(record)

    if not records:
        raise AnalysisInputError("缺少有效的上传文件引用")

    paths = [require_path_under(record.log_file_path, upload_root) for record in records]
    data["log_id"] = records[0].id
    data["log_ids"] = [record.id for record in records]
    data["file_path"] = paths[0]
    if len(paths) > 1 or str(data.get("source_type") or "").lower() == "image":
        data["file_paths"] = paths
    else:
        data.pop("file_paths", None)
    return paths
