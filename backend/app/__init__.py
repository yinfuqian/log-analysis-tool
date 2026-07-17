import logging
import os

from flask import Flask
from flask_cors import CORS

from .config import Config
from .routes import dashboard_bp
from app.analysis.routes.routes import analysis_bp
from app.git.routes import git_bp
from app.logfile.routes.routes import logfile_bp
from app.modules.routes.routes import module_bp
from app.product.routes.routes import product_bp
from app.auth.middleware import install_authentication
from app.auth.account_requests import build_account_request_service
from app.auth.routes import auth_bp
from app.auth.sessions import SessionService
from app.auth.users import UnavailableUserStore, UserStore
from app.health.routes import health_bp
from extensions import db, migrate, init_redis, init_celery


def create_app(config_overrides=None, redis_client=None):
    app = Flask(__name__)
    CORS(app)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    setup_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)

    global redis
    redis = redis_client or init_redis(app)
    init_celery(app)

    try:
        user_store = UserStore(app.config["AUTH_USERS_FILE"])
    except (OSError, ValueError, TypeError) as exc:
        app.logger.error("用户配置初始化失败，业务接口将保持关闭: %s", exc)
        user_store = UnavailableUserStore(exc)
    session_service = SessionService(
        redis,
        user_store,
        max_failures=app.config["AUTH_LOGIN_MAX_FAILURES"],
        failure_window_seconds=app.config["AUTH_LOGIN_WINDOW_SECONDS"],
    )
    app.extensions["auth_users"] = user_store
    app.extensions["auth_sessions"] = session_service
    app.extensions["account_request_service"] = build_account_request_service(app.config)

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(health_bp, url_prefix="/health")
    app.register_blueprint(product_bp, url_prefix="/product")
    app.register_blueprint(module_bp, url_prefix="/module")
    app.register_blueprint(logfile_bp, url_prefix="/logfile")
    app.register_blueprint(analysis_bp, url_prefix="/analysis")
    app.register_blueprint(git_bp, url_prefix="/git")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    install_authentication(app, session_service)

    return app


def setup_logging(app):
    log_dir = app.config["LOG_DIR"]
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    handler = logging.FileHandler(app.config["LOGGING_FILE"], encoding="utf-8")
    handler.setLevel(app.config["LOGGING_LEVEL"])
    handler.setFormatter(logging.Formatter(app.config["LOGGING_FORMAT"]))

    app.logger.addHandler(handler)
    app.logger.setLevel(app.config["LOGGING_LEVEL"])
    app.logger.info("启动日志：应用已启动并初始化完成")
