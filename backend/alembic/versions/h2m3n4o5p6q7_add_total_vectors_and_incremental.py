"""add_total_vectors_and_incremental_to_embedding_jobs

Revision ID: h2m3n4o5p6q7
Revises: g7h8i9j0k1l2
Create Date: 2025-06-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h2m3n4o5p6q7'
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    No-op: total_vectors and incremental columns are already created 
    in the g7h8i9j0k1l2 migration when the embedding_jobs table is created.
    """
    pass


def downgrade() -> None:
    """No-op: columns are managed by the table creation migration."""
    pass
