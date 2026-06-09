"""Add agent_definition + agent_definition_status to agent_configs

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-06-03 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q2r3s4t5u6v7"
down_revision: Union[str, None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("agent_definition", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "agent_definition_status",
            sa.String(),
            nullable=False,
            server_default="not_started",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "agent_definition_status")
    op.drop_column("agent_configs", "agent_definition")
