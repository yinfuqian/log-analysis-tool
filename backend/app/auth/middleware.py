"""middleware 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from flask import g, jsonify, request


ANONYMOUS_ENDPOINTS = {"auth.login", "auth.request_account", "health.live", "health.ready"}


def extract_bearer_token(header_value):
    """解析或提取并返回 extract_bearer_token 对应的业务数据，保持现有调用约定。"""
    scheme, separator, token = str(header_value or "").partition(" ")
    if separator and scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def _authentication_error():
    """处理 _authentication_error 对应的业务步骤，并向调用方返回所需结果。"""
    return jsonify({
        "code": "authentication_required",
        "message": "请先登录或重新登录",
    }), 401


def install_authentication(app, session_service):
    """注册或配置 install_authentication 对应的业务数据，保持现有调用约定。"""
    @app.before_request
    def require_authenticated_session():
        """处理 require_authenticated_session 对应的业务步骤，并向调用方返回所需结果。"""
        if request.method == "OPTIONS" or request.endpoint in ANONYMOUS_ENDPOINTS:
            return None
        if app.testing and app.config.get("AUTH_TEST_BYPASS"):
            return None

        raw_token = extract_bearer_token(request.headers.get("Authorization"))
        user = session_service.authenticate(raw_token)
        if not user:
            return _authentication_error()

        g.current_user = user
        g.auth_token = raw_token
        return None
