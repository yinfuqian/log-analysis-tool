"""models 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
from datetime import datetime

from extensions import db


class UserOperationLog(db.Model):
    """UserOperationLog 类封装该领域对象的状态、依赖与相关行为。"""
    __tablename__ = "user_operation_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    request_id = db.Column(db.String(64), nullable=False, unique=True)
    operator_username = db.Column(db.String(255), nullable=True, index=True)
    actor_type = db.Column(db.String(32), nullable=False)
    request_method = db.Column(db.String(16), nullable=False)
    request_path = db.Column(db.String(500), nullable=False, index=True)
    client_ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    status_code = db.Column(db.Integer, nullable=False)
    duration_ms = db.Column(db.Integer, nullable=False)
    operation_result = db.Column(db.String(32), nullable=False)
    target_username = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
