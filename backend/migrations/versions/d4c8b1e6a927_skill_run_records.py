"""Add skill run records for Codex skill execution.

Revision ID: d4c8b1e6a927
Revises: 7c9a4f21d801
Create Date: 2026-09-18 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d4c8b1e6a927"
down_revision = "7c9a4f21d801"
branch_labels = None
depends_on = None


def upgrade():
    """创建技能执行记录表，用于保存技能任务的排队、进度与最终结果。"""
    inspector = sa.inspect(op.get_bind())
    table_exists = inspector.has_table("skill_run_records")

    if not table_exists:
        op.create_table(
            "skill_run_records",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("skill_id", sa.String(length=64), nullable=False),
            sa.Column("jira_url", sa.String(length=500), nullable=True),
            sa.Column("inputs", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("stage", sa.String(length=64), nullable=True),
            sa.Column("progress", sa.Text(), nullable=True),
            sa.Column("result_text", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("codex_session_id", sa.String(length=128), nullable=True),
            sa.Column("workspace_dir", sa.String(length=500), nullable=True),
            sa.Column("requested_by", sa.String(length=255), nullable=True),
            sa.Column("exit_code", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        existing_indexes = set()
    else:
        existing_indexes = {item["name"] for item in inspector.get_indexes("skill_run_records")}

    # task_id 使用唯一索引，保证外部传入的任务标识可以直接用于查询与取消。
    if "ix_skill_run_records_task_id" not in existing_indexes:
        op.create_index("ix_skill_run_records_task_id", "skill_run_records", ["task_id"], unique=True)
    indexes = {
        "ix_skill_run_records_skill_id": "skill_id",
        "ix_skill_run_records_status": "status",
        "ix_skill_run_records_requested_by": "requested_by",
        "ix_skill_run_records_created_at": "created_at",
    }
    for index_name, column_name in indexes.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, "skill_run_records", [column_name])


def downgrade():
    """回滚技能执行记录表及其索引。"""
    op.drop_index("ix_skill_run_records_created_at", table_name="skill_run_records")
    op.drop_index("ix_skill_run_records_requested_by", table_name="skill_run_records")
    op.drop_index("ix_skill_run_records_status", table_name="skill_run_records")
    op.drop_index("ix_skill_run_records_skill_id", table_name="skill_run_records")
    op.drop_index("ix_skill_run_records_task_id", table_name="skill_run_records")
    op.drop_table("skill_run_records")
