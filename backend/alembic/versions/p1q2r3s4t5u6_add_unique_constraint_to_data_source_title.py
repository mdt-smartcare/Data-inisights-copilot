"""Add unique constraint to data_source title

Revision ID: p1q2r3s4t5u6
Revises: j4k5l6m7n8o9
Create Date: 2026-05-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, None] = 'j4k5l6m7n8o9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint to title column
    op.create_unique_constraint(
        'uq_data_sources_title',
        'data_sources',
        ['title']
    )


def downgrade() -> None:
    # Remove unique constraint
    op.drop_constraint('uq_data_sources_title', 'data_sources', type_='unique')
