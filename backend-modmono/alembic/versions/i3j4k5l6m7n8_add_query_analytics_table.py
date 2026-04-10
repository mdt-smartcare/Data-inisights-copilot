"""add query_analytics table

Revision ID: i3j4k5l6m7n8
Revises: h2m3n4o5p6q7
Create Date: 2026-04-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i3j4k5l6m7n8'
down_revision: Union[str, None] = 'h2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create query_analytics table for privacy-safe query metrics."""
    op.create_table(
        'query_analytics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('query_hash', sa.String(64), nullable=True),
        sa.Column('query_category', sa.String(50), nullable=True),
        sa.Column('query_complexity', sa.String(20), nullable=True),
        sa.Column('sql_generated', sa.Boolean(), nullable=False, default=False),
        sa.Column('sql_executed', sa.Boolean(), nullable=False, default=False),
        sa.Column('execution_success', sa.Boolean(), nullable=False, default=False),
        sa.Column('error_type', sa.String(100), nullable=True),
        sa.Column('error_category', sa.String(50), nullable=True),
        sa.Column('generation_time_ms', sa.Integer(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('total_time_ms', sa.Integer(), nullable=True),
        sa.Column('result_row_count', sa.Integer(), nullable=True),
        sa.Column('result_column_count', sa.Integer(), nullable=True),
        sa.Column('data_source_type', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for common queries
    op.create_index('ix_query_analytics_query_hash', 'query_analytics', ['query_hash'])
    op.create_index('ix_query_analytics_query_category', 'query_analytics', ['query_category'])
    op.create_index('ix_query_analytics_error_type', 'query_analytics', ['error_type'])
    op.create_index('ix_query_analytics_created_at', 'query_analytics', ['created_at'])
    op.create_index('ix_query_analytics_category_created', 'query_analytics', ['query_category', 'created_at'])
    op.create_index('ix_query_analytics_error_created', 'query_analytics', ['error_type', 'created_at'])
    op.create_index('ix_query_analytics_success_created', 'query_analytics', ['execution_success', 'created_at'])


def downgrade() -> None:
    """Drop query_analytics table."""
    op.drop_index('ix_query_analytics_success_created', table_name='query_analytics')
    op.drop_index('ix_query_analytics_error_created', table_name='query_analytics')
    op.drop_index('ix_query_analytics_category_created', table_name='query_analytics')
    op.drop_index('ix_query_analytics_created_at', table_name='query_analytics')
    op.drop_index('ix_query_analytics_error_type', table_name='query_analytics')
    op.drop_index('ix_query_analytics_query_category', table_name='query_analytics')
    op.drop_index('ix_query_analytics_query_hash', table_name='query_analytics')
    op.drop_table('query_analytics')
