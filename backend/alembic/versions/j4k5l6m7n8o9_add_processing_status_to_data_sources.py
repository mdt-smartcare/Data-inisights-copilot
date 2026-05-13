"""add processing_status to data_sources

Revision ID: j4k5l6m7n8o9
Revises: f0a1b2c3d4e5
Create Date: 2026-05-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j4k5l6m7n8o9'
down_revision: Union[str, None] = 'f0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add processing_status, processing_progress, and processing_error columns to data_sources."""
    # Add processing_status with default 'completed' for existing rows
    op.add_column(
        'data_sources',
        sa.Column('processing_status', sa.String(), nullable=True, server_default='completed')
    )
    op.add_column(
        'data_sources',
        sa.Column('processing_progress', sa.BigInteger(), nullable=True, server_default='0')
    )
    op.add_column(
        'data_sources',
        sa.Column('processing_error', sa.Text(), nullable=True)
    )
    
    # Remove server defaults after migration
    op.alter_column('data_sources', 'processing_status', server_default=None)
    op.alter_column('data_sources', 'processing_progress', server_default=None)


def downgrade() -> None:
    """Remove processing_status, processing_progress, and processing_error columns."""
    op.drop_column('data_sources', 'processing_error')
    op.drop_column('data_sources', 'processing_progress')
    op.drop_column('data_sources', 'processing_status')
