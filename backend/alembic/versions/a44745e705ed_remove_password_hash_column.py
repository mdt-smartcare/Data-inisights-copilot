"""remove_password_hash_column

Revision ID: a44745e705ed
Revises: 19285e5bed16
Create Date: 2026-04-03 18:52:46.735320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a44745e705ed'
down_revision: Union[str, Sequence[str], None] = '19285e5bed16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('users', 'password_hash')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('password_hash', sa.Text(), nullable=True))
