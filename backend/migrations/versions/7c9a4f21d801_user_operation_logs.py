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
    inspector = sa.inspect(op.get_bind())
    table_exists = inspector.has_table("user_operation_logs")

    if not table_exists:
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
        existing_indexes = set()
    else:
        existing_indexes = {item["name"] for item in inspector.get_indexes("user_operation_logs")}

    indexes = {
        "ix_user_operation_logs_operator_username": "operator_username",
        "ix_user_operation_logs_request_path": "request_path",
        "ix_user_operation_logs_created_at": "created_at",
    }
    for index_name, column_name in indexes.items():
        if index_name not in existing_indexes:
            op.create_index(index_name, "user_operation_logs", [column_name])


def downgrade():
    op.drop_index("ix_user_operation_logs_created_at", table_name="user_operation_logs")
    op.drop_index("ix_user_operation_logs_request_path", table_name="user_operation_logs")
    op.drop_index("ix_user_operation_logs_operator_username", table_name="user_operation_logs")
    op.drop_table("user_operation_logs")
