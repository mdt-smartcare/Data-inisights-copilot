"""Add model ID columns to agent_configs

Revision ID: f1a2b3c4d5e6
Revises: e5f890a12b34
Create Date: 2026-04-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e5f890a12b35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename model ref columns to model_id in agent_configs."""
    from sqlalchemy import inspect
    from sqlalchemy.engine import reflection
    
    # Get connection to check existing columns
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('agent_configs')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('agent_configs')]
    existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('agent_configs')]
    
    # Column rename mapping: old_name -> new_name
    renames = [
        ('llm_model_ref', 'llm_model_id'),
        ('embedding_model_ref', 'embedding_model_id'),
        ('reranker_model_ref', 'reranker_model_id'),
    ]
    
    for old_name, new_name in renames:
        # Drop old indexes if they exist
        old_idx = f'idx_agent_configs_{old_name}'
        if old_idx in existing_indexes:
            op.drop_index(old_idx, table_name='agent_configs')
        
        # Drop old FK if it exists
        old_fk = f'fk_agent_configs_{old_name}'
        if old_fk in existing_fks:
            op.drop_constraint(old_fk, 'agent_configs', type_='foreignkey')
        
        if old_name in existing_columns:
            # Rename existing column
            op.alter_column('agent_configs', old_name, new_column_name=new_name)
        elif new_name not in existing_columns:
            # Add new column if neither old nor new exists
            op.add_column('agent_configs', sa.Column(new_name, sa.Integer(), nullable=True))
        
        # Create new FK and index with new names
        op.create_foreign_key(f'fk_agent_configs_{new_name}', 'agent_configs', 'ai_models', [new_name], ['id'], ondelete='SET NULL')
        op.create_index(f'idx_agent_configs_{new_name}', 'agent_configs', [new_name])


def downgrade() -> None:
    """Remove model ID columns from agent_configs."""
    op.drop_index('idx_agent_configs_reranker_model_id', table_name='agent_configs')
    op.drop_index('idx_agent_configs_embedding_model_id', table_name='agent_configs')
    op.drop_index('idx_agent_configs_llm_model_id', table_name='agent_configs')
    
    op.drop_constraint('fk_agent_configs_reranker_model_id', 'agent_configs', type_='foreignkey')
    op.drop_constraint('fk_agent_configs_embedding_model_id', 'agent_configs', type_='foreignkey')
    op.drop_constraint('fk_agent_configs_llm_model_id', 'agent_configs', type_='foreignkey')
    
    op.drop_column('agent_configs', 'reranker_model_id')
    op.drop_column('agent_configs', 'embedding_model_id')
    op.drop_column('agent_configs', 'llm_model_id')
