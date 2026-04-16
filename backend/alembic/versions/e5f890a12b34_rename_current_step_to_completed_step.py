"""rename_current_step_to_completed_step

Revision ID: e5f890a12b34
Revises: d4c229c08d0e
Create Date: 2026-04-03 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f890a12b34'
down_revision: Union[str, Sequence[str], None] = 'd4c229c08d0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename current_step to completed_step."""
    op.alter_column('agent_configs', 'current_step', new_column_name='completed_step')


def downgrade() -> None:
    """Rename completed_step back to current_step."""
    op.alter_column('agent_configs', 'completed_step', new_column_name='current_step')
