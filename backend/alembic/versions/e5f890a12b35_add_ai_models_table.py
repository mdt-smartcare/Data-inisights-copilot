"""Add ai_models table

Revision ID: e5f890a12b35
Revises: e5f890a12b34
Create Date: 2026-04-06 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f890a12b35'
down_revision: Union[str, None] = 'e5f890a12b34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ai_models table."""
    op.create_table('ai_models',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('model_id', sa.String(500), nullable=False),
        sa.Column('display_name', sa.String(200), nullable=False),
        sa.Column('model_type', sa.String(50), nullable=False),
        sa.Column('provider_name', sa.String(100), nullable=False),
        sa.Column('deployment_type', sa.String(50), nullable=False),
        sa.Column('api_base_url', sa.Text(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('api_key_env_var', sa.String(100), nullable=True),
        sa.Column('local_path', sa.Text(), nullable=True),
        sa.Column('download_status', sa.String(50), nullable=False, server_default='not_downloaded'),
        sa.Column('download_progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('download_error', sa.Text(), nullable=True),
        sa.Column('context_length', sa.Integer(), nullable=True),
        sa.Column('max_input_tokens', sa.Integer(), nullable=True),
        sa.Column('dimensions', sa.Integer(), nullable=True),
        sa.Column('recommended_chunk_size', sa.Integer(), nullable=True),
        sa.Column('compatibility_notes', sa.Text(), nullable=True),
        sa.Column('hf_model_id', sa.String(500), nullable=True),
        sa.Column('hf_revision', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("model_type IN ('llm', 'embedding', 'reranker')", name='ck_ai_models_model_type'),
        sa.CheckConstraint("deployment_type IN ('cloud', 'local')", name='ck_ai_models_deployment_type'),
        sa.CheckConstraint("download_status IN ('not_downloaded', 'pending', 'downloading', 'ready', 'error')", name='ck_ai_models_download_status'),
    )
    op.create_index('ix_ai_models_model_id', 'ai_models', ['model_id'], unique=True)
    op.create_index('ix_ai_models_model_type', 'ai_models', ['model_type'], unique=False)
    op.create_index('ix_ai_models_provider_name', 'ai_models', ['provider_name'], unique=False)
    op.create_index('ix_ai_models_deployment_type', 'ai_models', ['deployment_type'], unique=False)
    op.create_index('ix_ai_models_is_active', 'ai_models', ['is_active'], unique=False)


def downgrade() -> None:
    """Drop ai_models table."""
    op.drop_index('ix_ai_models_is_active', table_name='ai_models')
    op.drop_index('ix_ai_models_deployment_type', table_name='ai_models')
    op.drop_index('ix_ai_models_provider_name', table_name='ai_models')
    op.drop_index('ix_ai_models_model_type', table_name='ai_models')
    op.drop_index('ix_ai_models_model_id', table_name='ai_models')
    op.drop_table('ai_models')
