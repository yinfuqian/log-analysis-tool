"""routes 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from flask import Blueprint, current_app, g, jsonify, request

from .account_requests import AccountRequestError


auth_bp = Blueprint("auth", __name__)


def _sessions():
    """处理 _sessions 对应的业务步骤，并向调用方返回所需结果。"""
    return current_app.extensions["auth_sessions"]


def _invalid_credentials(status_code=401):
    """处理 _invalid_credentials 对应的业务步骤，并向调用方返回所需结果。"""
    return jsonify({
        "code": "invalid_credentials",
        "message": "用户名或密码错误",
    }), status_code


@auth_bp.post("/login")
def login():
    """处理 login 对应的业务步骤，并向调用方返回所需结果。"""
    payload = request.get_json(silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    source_ip = request.remote_addr or "unknown"
    sessions = _sessions()
    if not sessions.user_store.available:
        return jsonify({
            "code": "auth_configuration_unavailable",
            "message": "用户配置当前不可用",
        }), 503
    user = sessions.user_store.verify_password(username, password)
    if not user:
        limited = sessions.register_failure(username, source_ip)
        return _invalid_credentials(429 if limited else 401)

    sessions.clear_failures(username, source_ip)
    token = sessions.create(user)
    return jsonify({"token": token, "username": user.username})


@auth_bp.post("/account-requests")
def request_account():
    """提交 request_account 对应的业务数据，保持现有调用约定。"""
    payload = request.get_json(silent=True) or {}
    service = current_app.extensions["account_request_service"]
    try:
        result = service.submit(
            payload.get("username"),
            payload.get("password"),
            payload.get("applicant_name"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except AccountRequestError:
        return jsonify({"error": "账号申请失败，请联系管理员"}), 502
    return jsonify(result), 202


@auth_bp.post("/logout")
def logout():
    """处理 logout 对应的业务步骤，并向调用方返回所需结果。"""
    _sessions().revoke(g.auth_token)
    return jsonify({"message": "已退出登录"})


@auth_bp.get("/me")
def me():
    """处理 me 对应的业务步骤，并向调用方返回所需结果。"""
    return jsonify({"username": g.current_user.username})
