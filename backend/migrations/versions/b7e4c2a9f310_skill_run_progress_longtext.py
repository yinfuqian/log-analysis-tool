"""Widen skill run progress column to LONGTEXT.

Revision ID: b7e4c2a9f310
Revises: d4c8b1e6a927
Create Date: 2026-09-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "b7e4c2a9f310"
down_revision = "d4c8b1e6a927"
branch_labels = None
depends_on = None


def _progress_type():
    """progress 的目标列类型：MySQL 用 LONGTEXT，其他方言退化成 TEXT，便于本地跑迁移。"""
    return sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade():
    """把 skill_run_records.progress 升级为 LONGTEXT，避免较长的进度被 TEXT 的 64KB 上限截断。"""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("skill_run_records"):
        # 表还不存在时交给 bootstrap_schema 自动建表，这里不重复创建。
        return

    columns = {item["name"]: item for item in inspector.get_columns("skill_run_records")}
    progress = columns.get("progress")
    target_type = _progress_type()
    if progress is None:
        op.add_column("skill_run_records", sa.Column("progress", target_type, nullable=True))
        return
    if isinstance(progress["type"], mysql.LONGTEXT):
        return
    op.alter_column(
        "skill_run_records",
        "progress",
        existing_type=sa.Text(),
        type_=target_type,
        existing_nullable=True,
    )


def downgrade():
    """把 skill_run_records.progress 回退为 TEXT。"""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("skill_run_records"):
        return
    op.alter_column(
        "skill_run_records",
        "progress",
        existing_type=_progress_type(),
        type_=sa.Text(),
        existing_nullable=True,
    )
