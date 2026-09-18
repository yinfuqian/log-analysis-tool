"""middleware 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import secrets

from flask import g, jsonify, request


ANONYMOUS_ENDPOINTS = {"auth.login", "auth.request_account", "health.live", "health.ready"}


class ExternalApiPrincipal:
    """外部系统通过接口令牌调用时使用的调用方标识。"""

    def __init__(self, username: str):
        """记录外部调用方在审计日志中显示的用户名。"""
        self.username = username


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


def extract_api_token(headers):
    """从 X-API-Token 或 Authorization 头中提取外部调用令牌。"""
    explicit = str(headers.get("X-API-Token") or "").strip()
    if explicit:
        return explicit
    return extract_bearer_token(headers.get("Authorization"))


def match_api_token(app, path, headers):
    """判断当前请求是否携带了可用于该路径的外部接口令牌。"""
    configured = str(app.config.get("SKILL_API_TOKEN") or "")
    if not configured:
        return False
    raw_paths = str(app.config.get("SKILL_API_TOKEN_PATHS") or "/skill")
    allowed_paths = [item.strip() for item in raw_paths.split(",") if item.strip()]
    if allowed_paths and not any(str(path or "").startswith(prefix) for prefix in allowed_paths):
        return False
    provided = extract_api_token(headers)
    if not provided:
        return False
    return secrets.compare_digest(provided, configured)


def install_authentication(app, session_service):
    """注册或配置 install_authentication 对应的业务数据，保持现有调用约定。"""
    @app.before_request
    def require_authenticated_session():
        """处理 require_authenticated_session 对应的业务步骤，并向调用方返回所需结果。"""
        if request.method == "OPTIONS" or request.endpoint in ANONYMOUS_ENDPOINTS:
            return None
        if app.testing and app.config.get("AUTH_TEST_BYPASS"):
            return None

        # 外部系统可使用独立接口令牌调用技能接口，避免与登录会话令牌混用。
        if match_api_token(app, request.path, request.headers):
            g.current_user = ExternalApiPrincipal(str(app.config.get("SKILL_API_USERNAME") or "external-api"))
            g.auth_token = None
            return None

        raw_token = extract_bearer_token(request.headers.get("Authorization"))
        user = session_service.authenticate(raw_token)
        if not user:
            return _authentication_error()

        g.current_user = user
        g.auth_token = raw_token
        return None
