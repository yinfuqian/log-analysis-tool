from flask import Blueprint, current_app, g, jsonify, request


auth_bp = Blueprint("auth", __name__)


def _sessions():
    return current_app.extensions["auth_sessions"]


def _invalid_credentials(status_code=401):
    return jsonify({
        "code": "invalid_credentials",
        "message": "用户名或密码错误",
    }), status_code


@auth_bp.post("/login")
def login():
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


@auth_bp.post("/logout")
def logout():
    _sessions().revoke(g.auth_token)
    return jsonify({"message": "已退出登录"})


@auth_bp.get("/me")
def me():
    return jsonify({"username": g.current_user.username})
