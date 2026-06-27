"""Add git ref cache

Revision ID: c2b9e3a1d4f6
Revises: 9d7f0b2c4a11
Create Date: 2026-06-15 19:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c2b9e3a1d4f6"
down_revision = "9d7f0b2c4a11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "git_refs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ref_key", sa.String(length=64), nullable=False),
        sa.Column("repo_url", sa.String(length=500), nullable=False),
        sa.Column("ref_name", sa.String(length=255), nullable=False),
        sa.Column("ref_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref_key", name="uq_git_refs_ref_key"),
    )
    op.create_index("ix_git_refs_repo_url", "git_refs", ["repo_url"])


def downgrade():
    op.drop_index("ix_git_refs_repo_url", table_name="git_refs")
    op.drop_table("git_refs")
