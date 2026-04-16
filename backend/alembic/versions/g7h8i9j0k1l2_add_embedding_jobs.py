"""Add embedding jobs and checkpoints tables

Revision ID: g7h8i9j0k1l2
Revises: f1a2b3c4d5e6
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'g7h8i9j0k1l2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    # Create embedding_jobs table
    op.create_table(
        'embedding_jobs',
        sa.Column('job_id', sa.String(64), primary_key=True),
        sa.Column('config_id', sa.Integer(), sa.ForeignKey('agent_configs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='QUEUED'),
        sa.Column('phase', sa.String(255), nullable=True),
        
        # Document counts
        sa.Column('total_documents', sa.Integer(), default=0),
        sa.Column('processed_documents', sa.Integer(), default=0),
        sa.Column('failed_documents', sa.Integer(), default=0),
        sa.Column('skipped_documents', sa.Integer(), default=0),
        
        # Batch tracking
        sa.Column('total_batches', sa.Integer(), default=0),
        sa.Column('current_batch', sa.Integer(), default=0),
        sa.Column('batch_size', sa.Integer(), default=50),
        
        # Vector stats
        sa.Column('total_vectors', sa.Integer(), default=0),
        
        # Incremental mode
        sa.Column('incremental', sa.Integer(), default=0),
        
        # Progress metrics
        sa.Column('progress_percentage', sa.Float(), default=0.0),
        sa.Column('documents_per_second', sa.Float(), nullable=True),
        
        # Configuration metadata (JSON)
        sa.Column('config_metadata', postgresql.JSON(), nullable=True),
        
        # Error tracking
        sa.Column('errors_count', sa.Integer(), default=0),
        sa.Column('recent_errors', postgresql.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        
        # User who started the job
        sa.Column('started_by', sa.String(36), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('embedding_started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('estimated_completion_at', sa.DateTime(), nullable=True),
    )
    
    # Create indexes
    op.create_index('ix_embedding_jobs_config_id', 'embedding_jobs', ['config_id'])
    op.create_index('ix_embedding_jobs_status', 'embedding_jobs', ['status'])
    op.create_index('ix_embedding_jobs_status_created', 'embedding_jobs', ['status', 'created_at'])
    op.create_index('ix_embedding_jobs_config_status', 'embedding_jobs', ['config_id', 'status'])
    
    # Create embedding_checkpoints table
    op.create_table(
        'embedding_checkpoints',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('vector_db_name', sa.String(255), unique=True, nullable=False),
        sa.Column('phase', sa.String(50), nullable=False),
        sa.Column('checkpoint_data', postgresql.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    
    # Create index for vector_db_name
    op.create_index('ix_embedding_checkpoints_vector_db_name', 'embedding_checkpoints', ['vector_db_name'])


def downgrade():
    op.drop_index('ix_embedding_checkpoints_vector_db_name', 'embedding_checkpoints')
    op.drop_table('embedding_checkpoints')
    
    op.drop_index('ix_embedding_jobs_config_status', 'embedding_jobs')
    op.drop_index('ix_embedding_jobs_status_created', 'embedding_jobs')
    op.drop_index('ix_embedding_jobs_status', 'embedding_jobs')
    op.drop_index('ix_embedding_jobs_config_id', 'embedding_jobs')
    op.drop_table('embedding_jobs')
