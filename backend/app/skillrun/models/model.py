"""model 模块负责技能执行记录的数据表定义与序列化。"""
import json
from datetime import datetime

from extensions import db


class SkillRunRecord(db.Model):
    """SkillRunRecord 记录一次技能执行的任务标识、状态流转、进度与最终结果。"""

    __tablename__ = "skill_run_records"

    # 任务状态：排队、执行中、成功、失败、超时、已取消。
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"
    STATUS_CANCELLED = "cancelled"
    TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_TIMEOUT, STATUS_CANCELLED)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    skill_id = db.Column(db.String(64), nullable=False, index=True)
    jira_url = db.Column(db.String(500), nullable=True)
    inputs = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default=STATUS_QUEUED, index=True)
    stage = db.Column(db.String(64), nullable=True)
    progress = db.Column(db.Text, nullable=True)
    result_text = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    codex_session_id = db.Column(db.String(128), nullable=True)
    workspace_dir = db.Column(db.String(500), nullable=True)
    requested_by = db.Column(db.String(255), nullable=True, index=True)
    exit_code = db.Column(db.Integer, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self, include_result: bool = True) -> dict:
        """转换为接口返回用的字典结构，列表场景可关闭大字段输出。"""
        payload = {
            "record_id": self.id,
            "task_id": self.task_id,
            "skill_id": self.skill_id,
            "jira_url": self.jira_url,
            "status": self.status,
            "stage": self.stage,
            "requested_by": self.requested_by,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "codex_session_id": self.codex_session_id,
            "created_at": _format_time(self.created_at),
            "started_at": _format_time(self.started_at),
            "finished_at": _format_time(self.finished_at),
        }
        if include_result:
            payload["inputs"] = _parse_json_text(self.inputs, {})
            payload["progress"] = _parse_json_text(self.progress, None)
            payload["result"] = self.result_text
            payload["error"] = self.error_message
        return payload


def _format_time(value):
    """把数据库时间格式化为便于外部系统解析的 UTC 字符串。"""
    return value.isoformat() + "Z" if value else None


def _parse_json_text(value, default):
    """把数据库中的 JSON 文本安全地还原为对象，解析失败时返回默认值。"""
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
