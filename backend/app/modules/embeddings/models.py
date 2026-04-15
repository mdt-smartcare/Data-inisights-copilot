"""
SQLAlchemy ORM models for embedding jobs.

Schema:
- embedding_jobs: Track embedding generation jobs with progress

State Machine:
QUEUED -> PREPARING -> EMBEDDING -> VALIDATING -> STORING -> COMPLETED
Any state can transition to FAILED or CANCELLED.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Index, Float,
    Integer, String, Text, JSON
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.connection import Base


class EmbeddingJobModel(Base):
    """
    Embedding job tracking model.
    
    Tracks the lifecycle of embedding generation jobs including
    progress metrics, error handling, and performance stats.
    """
    __tablename__ = "embedding_jobs"
    
    # Primary key is the job_id string (e.g., "emb-job-abc123")
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    
    # Link to agent config (contains embedding_config, data_dictionary, etc.)
    config_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agent_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Status and phase
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="QUEUED",
        index=True
    )
    phase: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Document counts
    total_documents: Mapped[int] = mapped_column(Integer, default=0)
    processed_documents: Mapped[int] = mapped_column(Integer, default=0)
    failed_documents: Mapped[int] = mapped_column(Integer, default=0)
    skipped_documents: Mapped[int] = mapped_column(Integer, default=0)
    
    # Batch tracking
    total_batches: Mapped[int] = mapped_column(Integer, default=0)
    current_batch: Mapped[int] = mapped_column(Integer, default=0)
    batch_size: Mapped[int] = mapped_column(Integer, default=50)
    
    # Vector stats
    total_vectors: Mapped[int] = mapped_column(Integer, default=0)
    
    # Incremental mode
    incremental: Mapped[bool] = mapped_column(Integer, default=False)
    
    # Progress metrics
    progress_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    documents_per_second: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Configuration metadata (JSON blob)
    config_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Error tracking
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # User who started the job
    started_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    embedding_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    estimated_completion_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index("ix_embedding_jobs_status_created", "status", "created_at"),
        Index("ix_embedding_jobs_config_status", "config_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<EmbeddingJob(job_id={self.job_id}, status={self.status}, progress={self.progress_percentage:.1f}%)>"


class EmbeddingCheckpointModel(Base):
    """
    Checkpoint model for resumable embedding jobs.
    
    Stores intermediate state to allow jobs to resume after failures.
    """
    __tablename__ = "embedding_checkpoints"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Link to vector DB (unique per collection)
    vector_db_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    
    # Checkpoint phase
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Checkpoint data (serialized state)
    checkpoint_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<EmbeddingCheckpoint(vector_db={self.vector_db_name}, phase={self.phase})>"
