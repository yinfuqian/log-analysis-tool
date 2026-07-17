"""Add user operation audit logs.

Revision ID: 7c9a4f21d801
Revises: c2b9e3a1d4f6
Create Date: 2026-07-17 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "7c9a4f21d801"
down_revision = "c2b9e3a1d4f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_operation_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("operator_username", sa.String(length=255), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("request_method", sa.String(length=16), nullable=False),
        sa.Column("request_path", sa.String(length=500), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("operation_result", sa.String(length=32), nullable=False),
        sa.Column("target_username", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("ix_user_operation_logs_operator_username", "user_operation_logs", ["operator_username"])
    op.create_index("ix_user_operation_logs_request_path", "user_operation_logs", ["request_path"])
    op.create_index("ix_user_operation_logs_created_at", "user_operation_logs", ["created_at"])


def downgrade():
    op.drop_index("ix_user_operation_logs_created_at", table_name="user_operation_logs")
    op.drop_index("ix_user_operation_logs_request_path", table_name="user_operation_logs")
    op.drop_index("ix_user_operation_logs_operator_username", table_name="user_operation_logs")
    op.drop_table("user_operation_logs")
