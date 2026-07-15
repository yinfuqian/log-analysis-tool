from flask import Blueprint, current_app, jsonify


health_bp = Blueprint("health", __name__)


@health_bp.get("/live")
def live():
    return jsonify({"status": "ok"})


@health_bp.get("/ready")
def ready():
    sessions = current_app.extensions.get("auth_sessions")
    try:
        if sessions is not None:
            if not sessions.user_store.available:
                return jsonify({"status": "unavailable"}), 503
            sessions.redis.ping()
    except Exception:
        return jsonify({"status": "unavailable"}), 503
    return jsonify({"status": "ready"})
