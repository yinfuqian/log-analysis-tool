import datetime
import logging
import os
import re
import uuid
from dataclasses import dataclass

from flask import Blueprint, current_app as app, jsonify, request

from app.logfile.models import Log
from extensions import db

from .log_processing import (
    LogProcessingError,
    filter_lines_by_date,
    read_uploaded_log_lines,
    resolve_target_date,
)
from .utils import (
    get_branch_address_by_name,
    get_module_name_by_id,
    get_product_name_by_id,
    sanitize_filename,
    save_binary_upload_file,
    save_processed_log_file,
)


logfile_bp = Blueprint("logfile", __name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@dataclass
class PreparedUpload:
    output_filename: str
    lines_to_save: list[str]
    metadata: dict


def build_upload_log_name(product_name, module_name, address, tag_version, original_filename):
    original_extension = os.path.splitext(original_filename)[1] or ".log"
    repo_name = os.path.splitext(os.path.basename((address or "repo").rstrip("/")))[0] or "repo"
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    unique_suffix = uuid.uuid4().hex[:8]
    return (
        f"{product_name}-{module_name}-{repo_name}-{tag_version}-"
        f"{timestamp}-{unique_suffix}{original_extension}"
    )


def build_upload_image_name(product_name, module_name, address, tag_version, original_filename):
    return build_upload_log_name(product_name, module_name, address, tag_version, original_filename)


def is_supported_image_filename(filename):
    suffix = os.path.splitext(str(filename or ""))[1].lower()
    return suffix in SUPPORTED_IMAGE_EXTENSIONS


def get_uploaded_image_files(files):
    uploaded_files = []
    if hasattr(files, "getlist"):
        uploaded_files = files.getlist("files") or files.getlist("file")
    if not uploaded_files and "file" in files:
        uploaded_files = [files["file"]]
    return [item for item in uploaded_files if item]


def prepare_uploaded_images(uploaded_files, product_name, module_name, address, tag_version):
    prepared_images = []
    for index, uploaded_file in enumerate(uploaded_files or [], start=1):
        original_filename = uploaded_file.filename or ""
        if not original_filename:
            raise LogProcessingError("图片文件名不能为空")
        if not is_supported_image_filename(original_filename):
            raise LogProcessingError("仅支持 png/jpg/jpeg 图片")

        image_name = sanitize_filename(
            build_upload_image_name(product_name, module_name, address, tag_version, original_filename)
        )
        file_bytes = uploaded_file.read()
        if not file_bytes:
            raise LogProcessingError("图片内容为空")

        prepared_images.append(
            {
                "sequence": index,
                "log_name": image_name,
                "file_path": save_binary_upload_file(file_bytes, image_name),
                "original_filename": original_filename,
            }
        )
    return prepared_images


def prepare_uploaded_log(uploaded_file, original_filename, log_name, date_filter=None):
    raw_lines = read_uploaded_log_lines(uploaded_file, original_filename)
    target_date = resolve_target_date(date_filter)
    filter_result = filter_lines_by_date(raw_lines, target_date)

    output_filename = log_name
    if original_filename.lower().endswith(".gz") or log_name.lower().endswith(".gz"):
        output_filename = re.sub(r"\.gz$", ".log", log_name, flags=re.IGNORECASE)

    metadata = {
        "date_filter_applied": filter_result.date_filter_applied,
        "target_date": filter_result.target_date.isoformat() if filter_result.target_date else None,
        "original_line_count": filter_result.original_line_count,
        "filtered_line_count": filter_result.filtered_line_count,
        "matched_line_count": filter_result.matched_line_count,
    }
    if filter_result.warning:
        metadata["warning"] = filter_result.warning

    return PreparedUpload(
        output_filename=output_filename,
        lines_to_save=filter_result.filtered_lines,
        metadata=metadata,
    )


def _resolve_upload_scope(form_data):
    product_id = form_data.get("product_id")
    module_id = form_data.get("module_id")
    address = form_data.get("address")
    tag_version = form_data.get("tag_version")
    return product_id, module_id, address, tag_version


def _validate_common_upload_fields(product_id, module_id, address, tag_version):
    return all([product_id, module_id, address, tag_version])


def _resolve_domain_names(product_id, module_id, address, tag_version):
    product_name = get_product_name_by_id(product_id)
    module_name = get_module_name_by_id(module_id)
    branch_address, branch_version = get_branch_address_by_name(address, tag_version)
    return product_name, module_name, branch_address, branch_version


@logfile_bp.route("/upload", methods=["POST"])
def upload_log():
    app.logger.debug("开始处理日志上传请求")
    if "file" not in request.files:
        app.logger.error("文件上传失败: 没有文件字段")
        return jsonify({"error": "请提供文件"}), 400

    uploaded_file = request.files["file"]
    original_filename = uploaded_file.filename or ""
    product_id, module_id, address, tag_version = _resolve_upload_scope(request.form)
    date_filter = request.form.get("date_filter", None)

    if not _validate_common_upload_fields(product_id, module_id, address, tag_version):
        return jsonify({"error": "缺少必要的字段: 产品ID、模块ID、分支地址、分支版本"}), 400

    product_name, module_name, address, tag_version = _resolve_domain_names(
        product_id, module_id, address, tag_version
    )
    if not all([product_name, module_name, address, tag_version]):
        return jsonify({"error": "数据库中存在无效的 ID，请检查输入"}), 400

    log_name = sanitize_filename(
        build_upload_log_name(product_name, module_name, address, tag_version, original_filename)
    )

    try:
        prepared_upload = prepare_uploaded_log(uploaded_file, original_filename, log_name, date_filter)
    except LogProcessingError as exc:
        app.logger.error(f"日志文件处理失败: {exc}")
        return jsonify({"error": str(exc)}), 400

    output_name = prepared_upload.output_filename
    processed_file_path = save_processed_log_file(prepared_upload.lines_to_save, output_name)

    log_entry = Log.query.filter_by(log_name=output_name).first()
    if log_entry:
        log_entry.count += 1
        log_entry.log_file_path = processed_file_path
    else:
        log_entry = Log(
            log_file_path=processed_file_path,
            log_name=output_name,
            count=1,
        )
        db.session.add(log_entry)
    db.session.commit()

    return jsonify(
        {
            "message": "文件上传并处理成功",
            "log_id": log_entry.id,
            "file_path": processed_file_path,
            "upload_count": log_entry.count,
            **prepared_upload.metadata,
        }
    ), 200


@logfile_bp.route("/upload_image", methods=["POST"])
def upload_image():
    app.logger.debug("\u5f00\u59cb\u5904\u7406\u56fe\u7247\u4e0a\u4f20\u8bf7\u6c42")
    uploaded_files = get_uploaded_image_files(request.files)
    if not uploaded_files:
        return jsonify({"error": "\u8bf7\u63d0\u4f9b\u56fe\u7247\u6587\u4ef6"}), 400

    product_id, module_id, address, tag_version = _resolve_upload_scope(request.form)
    image_tag = request.form.get("image_tag")
    image_description = request.form.get("image_description", "").strip()

    if not _validate_common_upload_fields(product_id, module_id, address, tag_version) or not image_tag:
        return jsonify({"error": "\u7f3a\u5c11\u5fc5\u8981\u7684\u5b57\u6bb5: \u4ea7\u54c1ID\u3001\u6a21\u5757ID\u3001\u5206\u652f\u5730\u5740\u3001\u5206\u652f\u7248\u672c\u3001\u56fe\u7247\u6807\u7b7e"}), 400

    product_name, module_name, address, tag_version = _resolve_domain_names(
        product_id, module_id, address, tag_version
    )
    if not all([product_name, module_name, address, tag_version]):
        return jsonify({"error": "\u6570\u636e\u5e93\u4e2d\u5b58\u5728\u65e0\u6548\u7684 ID\uff0c\u8bf7\u68c0\u67e5\u8f93\u5165"}), 400

    try:
        prepared_images = prepare_uploaded_images(
            uploaded_files,
            product_name=product_name,
            module_name=module_name,
            address=address,
            tag_version=tag_version,
        )
    except LogProcessingError as exc:
        return jsonify({"error": str(exc)}), 400

    uploaded_images = []
    for prepared_image in prepared_images:
        log_entry = Log.query.filter_by(log_name=prepared_image["log_name"]).first()
        if log_entry:
            log_entry.count += 1
            log_entry.log_file_path = prepared_image["file_path"]
        else:
            log_entry = Log(
                log_file_path=prepared_image["file_path"],
                log_name=prepared_image["log_name"],
                count=1,
            )
            db.session.add(log_entry)
        if hasattr(db.session, "flush"):
            db.session.flush()
        uploaded_images.append({**prepared_image, "log_id": log_entry.id, "upload_count": log_entry.count})
    db.session.commit()
    first_image = uploaded_images[0]

    return jsonify(
        {
            "message": "\u56fe\u7247\u4e0a\u4f20\u6210\u529f",
            "log_id": first_image["log_id"],
            "file_path": first_image["file_path"],
            "upload_count": first_image["upload_count"],
            "source_type": "image",
            "image_tag": image_tag,
            "image_description": image_description,
            "original_filename": first_image["original_filename"],
            "image_count": len(uploaded_images),
            "images": uploaded_images,
            "log_ids": [item["log_id"] for item in uploaded_images],
            "file_paths": [item["file_path"] for item in uploaded_images],
        }
    ), 200
