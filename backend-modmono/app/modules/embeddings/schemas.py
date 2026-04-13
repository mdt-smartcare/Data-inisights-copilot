"""
Pydantic schemas for embedding jobs.

Provides request/response DTOs for:
- Job creation and configuration
- Progress tracking
- Job summaries
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Enums
# ============================================

class EmbeddingJobStatus(str, Enum):
    """Status states for embedding jobs (state machine)."""
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    EMBEDDING = "EMBEDDING"
    VALIDATING = "VALIDATING"
    STORING = "STORING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ============================================
# Configuration DTOs
# ============================================

class ChunkingConfig(BaseModel):
    """Configuration for parent-child chunking strategy."""
    parent_chunk_size: int = Field(default=512, ge=100, le=2000, description="Parent chunk size in tokens")
    parent_chunk_overlap: int = Field(default=100, ge=0, le=500, description="Parent chunk overlap in tokens")
    child_chunk_size: int = Field(default=128, ge=50, le=500, description="Child chunk size in tokens")
    child_chunk_overlap: int = Field(default=25, ge=0, le=100, description="Child chunk overlap in tokens")


class ParallelizationConfig(BaseModel):
    """Configuration for parallel processing."""
    num_workers: Optional[int] = Field(default=None, ge=1, le=16, description="Number of worker processes. None = auto")
    chunking_batch_size: Optional[int] = Field(default=None, ge=100, le=50000, description="Documents per chunking batch")
    delta_check_batch_size: int = Field(default=50000, ge=1000, le=100000, description="Documents per delta check batch")


class MedicalContextConfig(BaseModel):
    """
    Configuration for medical terminology enrichment.
    Improves embedding quality by expanding clinical abbreviations.
    """
    medical_context: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of column names to human-readable medical terms"
    )
    clinical_flag_prefixes: List[str] = Field(
        default_factory=lambda: ["is_", "has_", "was_", "history_of_", "flag_", "confirmed_", "requires_", "on_"],
        description="Column prefixes indicating clinical boolean flags"
    )
    use_yaml_defaults: bool = Field(
        default=True,
        description="Merge with default mappings from embedding_config.yaml"
    )


# ============================================
# Job Request/Response DTOs
# ============================================

class EmbeddingJobCreate(BaseModel):
    """Request model for starting a new embedding job.
    
    config_id is required. Other settings override the defaults from agent_config table.
    """
    config_id: int = Field(..., description="Agent configuration ID to generate embeddings for")
    incremental: bool = Field(default=False, description="Whether to run incrementally (skip existing)")
    
    # Optional overrides from frontend
    batch_size: Optional[int] = Field(default=None, ge=1, le=1000, description="Batch size for embedding generation")
    max_concurrent: Optional[int] = Field(default=None, ge=1, le=10, description="Max concurrent batches")
    chunking: Optional[ChunkingConfig] = Field(default=None, description="Chunking configuration override")
    parallelization: Optional[ParallelizationConfig] = Field(default=None, description="Parallelization config")


class EmbeddingJobProgress(BaseModel):
    """Real-time progress information for an embedding job."""
    job_id: str = Field(..., description="Unique job identifier")
    status: EmbeddingJobStatus = Field(..., description="Current job status")
    phase: Optional[str] = Field(None, description="Current phase description")
    
    # Document Progress
    total_documents: int = Field(..., description="Total documents to process")
    processed_documents: int = Field(default=0, description="Documents processed so far")
    failed_documents: int = Field(default=0, description="Documents that failed processing")
    progress_percentage: float = Field(default=0.0, ge=0, le=100, description="Progress percentage")
    
    # Batch Progress
    current_batch: int = Field(default=0, description="Current batch being processed")
    total_batches: int = Field(..., description="Total number of batches")
    
    # Performance Metrics
    documents_per_second: Optional[float] = Field(None, description="Processing speed")
    estimated_time_remaining_seconds: Optional[int] = Field(None, description="ETA in seconds")
    elapsed_seconds: Optional[int] = Field(None, description="Time elapsed since start")
    
    # Errors
    errors_count: int = Field(default=0, description="Number of errors encountered")
    recent_errors: List[str] = Field(default_factory=list, description="Recent error messages")
    
    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class EmbeddingJobSummary(BaseModel):
    """Summary of a completed embedding job."""
    job_id: str
    status: EmbeddingJobStatus
    total_documents: int
    processed_documents: int
    failed_documents: int
    duration_seconds: Optional[float] = None
    average_speed: Optional[float] = None
    validation_passed: bool = False
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class EmbeddingJobResponse(BaseModel):
    """Response for job creation/status operations."""
    status: str = Field(..., description="Operation status")
    job_id: str = Field(..., description="Job identifier")
    message: str = Field(..., description="Human-readable message")


class CheckpointInfo(BaseModel):
    """Information about an embedding checkpoint."""
    vector_db_name: str
    phase: str
    created_at: datetime
    updated_at: datetime
    checkpoint_data: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True)


# ============================================
# Vector DB Status DTOs
# ============================================

class DiagnosticItem(BaseModel):
    """A diagnostic message about vector db health."""
    level: str  # "info", "warning", "error"
    message: str


class VectorDbStatusResponse(BaseModel):
    """Response schema for vector database status (derived from embedding jobs)."""
    name: str
    exists: bool
    total_documents_indexed: int = 0
    total_vectors: int = 0
    last_updated_at: Optional[datetime] = None
    embedding_model: Optional[str] = None
    llm: Optional[str] = None
    last_full_run: Optional[datetime] = None
    last_incremental_run: Optional[datetime] = None
    version: str = "1.0.0"
    diagnostics: List[DiagnosticItem] = Field(default_factory=list)
    schedule: Optional[Dict[str, Any]] = None
    
    # Additional info from embedding jobs
    embedding_status: Optional[str] = None
    last_job_id: Optional[str] = None
    last_job_status: Optional[str] = None
    
    # Vector store type (qdrant or chroma)
    vector_db_type: Optional[str] = Field(default="qdrant", description="Vector database type: 'qdrant' or 'chroma'")
