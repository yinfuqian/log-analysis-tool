import secrets
import time

from flask import g, request

from app.auth.users import normalize_username
from extensions import db

from .models import UserOperationLog


def persist_operation_audit(row):
    db.session.add(UserOperationLog(**row))
    db.session.commit()


def install_operation_audit(app, writer=persist_operation_audit):
    @app.before_request
    def begin_operation_audit():
        if request.method == "OPTIONS" or request.path.startswith("/health/") or request.endpoint == "static":
            g.audit_skip = True
            return None
        g.audit_skip = False
        g.audit_started_at = time.perf_counter()
        g.audit_request_id = f"REQ-{secrets.token_hex(12).upper()}"
        g.audit_target_username = None
        if request.path in {"/auth/login", "/auth/account-requests"}:
            payload = request.get_json(silent=True) or {}
            g.audit_target_username = normalize_username(payload.get("username")) or None
        return None

    @app.after_request
    def finish_operation_audit(response):
        if getattr(g, "audit_skip", True):
            return response
        request_id = g.audit_request_id
        response.headers["X-Request-ID"] = request_id
        current_user = getattr(g, "current_user", None)
        username = getattr(current_user, "username", None)
        row = {
            "request_id": request_id,
            "operator_username": username,
            "actor_type": "authenticated" if username else "anonymous",
            "request_method": request.method,
            "request_path": request.path,
            "client_ip": request.remote_addr,
            "user_agent": str(request.user_agent)[:500] or None,
            "status_code": response.status_code,
            "duration_ms": max(0, int((time.perf_counter() - g.audit_started_at) * 1000)),
            "operation_result": "success" if response.status_code < 400 else "failed",
            "target_username": g.audit_target_username,
        }
        try:
            writer(row)
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.exception("写入用户操作日志失败: request_id=%s", request_id)
        return response
