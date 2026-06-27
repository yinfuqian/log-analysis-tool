"""Add analysis knowledge base

Revision ID: 9d7f0b2c4a11
Revises: 5eea6fadcd32
Create Date: 2026-06-13 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9d7f0b2c4a11'
down_revision = '5eea6fadcd32'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'analysis_knowledge_cases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('module_id', sa.Integer(), nullable=False),
        sa.Column('error_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('error_type', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stack_top_file', sa.String(length=500), nullable=True),
        sa.Column('stack_top_line', sa.Integer(), nullable=True),
        sa.Column('branch_url', sa.String(length=500), nullable=True),
        sa.Column('branch_version', sa.String(length=100), nullable=True),
        sa.Column('log_excerpt', sa.Text(), nullable=True),
        sa.Column('code_files', sa.Text(), nullable=True),
        sa.Column('code_snippets', sa.Text(), nullable=True),
        sa.Column('issue_category', sa.String(length=64), nullable=False, server_default='unknown'),
        sa.Column('conclusion_summary', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('solution', sa.Text(), nullable=True),
        sa.Column('ai_analysis', sa.Text(), nullable=True),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_hit_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['module_id'], ['modules.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'module_id', 'error_fingerprint', name='uq_knowledge_case_scope_fingerprint'),
    )
    op.create_index('ix_analysis_knowledge_cases_error_fingerprint', 'analysis_knowledge_cases', ['error_fingerprint'])

    op.add_column('query_records', sa.Column('log_id', sa.Integer(), nullable=True))
    op.add_column('query_records', sa.Column('status', sa.String(length=32), nullable=True))
    op.add_column('query_records', sa.Column('log_hash', sa.String(length=64), nullable=True))
    op.add_column('query_records', sa.Column('error_fingerprint', sa.String(length=64), nullable=True))
    op.add_column('query_records', sa.Column('duration_ms', sa.Integer(), nullable=True))
    op.add_column('query_records', sa.Column('model_name', sa.String(length=128), nullable=True))
    op.add_column('query_records', sa.Column('hit_cache', sa.Boolean(), nullable=True, server_default=sa.false()))
    op.add_column('query_records', sa.Column('knowledge_case_id', sa.Integer(), nullable=True))
    op.create_index('ix_query_records_error_fingerprint', 'query_records', ['error_fingerprint'])

    op.drop_constraint('query_records_ibfk_1', 'query_records', type_='foreignkey')
    op.create_foreign_key('fk_query_records_product_id_products', 'query_records', 'products', ['product_id'], ['id'])
    op.create_foreign_key('fk_query_records_module_id_modules', 'query_records', 'modules', ['module_id'], ['id'])
    op.create_foreign_key('fk_query_records_log_id_logs', 'query_records', 'logs', ['log_id'], ['id'])
    op.create_foreign_key(
        'fk_query_records_knowledge_case_id',
        'query_records',
        'analysis_knowledge_cases',
        ['knowledge_case_id'],
        ['id'],
    )


def downgrade():
    op.drop_constraint('fk_query_records_knowledge_case_id', 'query_records', type_='foreignkey')
    op.drop_constraint('fk_query_records_log_id_logs', 'query_records', type_='foreignkey')
    op.drop_constraint('fk_query_records_module_id_modules', 'query_records', type_='foreignkey')
    op.drop_constraint('fk_query_records_product_id_products', 'query_records', type_='foreignkey')
    op.create_foreign_key('query_records_ibfk_1', 'query_records', 'logs', ['module_id'], ['id'])
    op.drop_index('ix_query_records_error_fingerprint', table_name='query_records')
    op.drop_column('query_records', 'knowledge_case_id')
    op.drop_column('query_records', 'hit_cache')
    op.drop_column('query_records', 'model_name')
    op.drop_column('query_records', 'duration_ms')
    op.drop_column('query_records', 'error_fingerprint')
    op.drop_column('query_records', 'log_hash')
    op.drop_column('query_records', 'status')
    op.drop_column('query_records', 'log_id')
    op.drop_index('ix_analysis_knowledge_cases_error_fingerprint', table_name='analysis_knowledge_cases')
    op.drop_table('analysis_knowledge_cases')
