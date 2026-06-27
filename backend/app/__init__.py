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
from extensions import db, migrate, init_redis, init_celery


def create_app():
    app = Flask(__name__)
    CORS(app)
    app.config.from_object(Config)

    setup_logging(app)

    db.init_app(app)
    migrate.init_app(app, db)

    global redis
    redis = init_redis(app)
    init_celery(app)

    app.register_blueprint(product_bp, url_prefix="/product")
    app.register_blueprint(module_bp, url_prefix="/module")
    app.register_blueprint(logfile_bp, url_prefix="/logfile")
    app.register_blueprint(analysis_bp, url_prefix="/analysis")
    app.register_blueprint(git_bp, url_prefix="/git")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

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
