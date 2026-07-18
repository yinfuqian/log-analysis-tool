"""routes 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from flask import Blueprint, jsonify

from app.runtime_checks import run_readiness_checks


health_bp = Blueprint("health", __name__)


@health_bp.get("/live")
def live():
    """处理 live 对应的业务步骤，并向调用方返回所需结果。"""
    return jsonify({"status": "ok"})


@health_bp.get("/ready")
def ready():
    """处理 ready 对应的业务步骤，并向调用方返回所需结果。"""
    result = run_readiness_checks()
    status = "ready" if result["ready"] else "unavailable"
    return jsonify({"status": status, "checks": result["checks"]}), 200 if result["ready"] else 503
