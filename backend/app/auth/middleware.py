from flask import g, jsonify, request


ANONYMOUS_ENDPOINTS = {"auth.login", "auth.request_account", "health.live", "health.ready"}


def extract_bearer_token(header_value):
    scheme, separator, token = str(header_value or "").partition(" ")
    if separator and scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def _authentication_error():
    return jsonify({
        "code": "authentication_required",
        "message": "请先登录或重新登录",
    }), 401


def install_authentication(app, session_service):
    @app.before_request
    def require_authenticated_session():
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
