"""
Embeddings module for embedding job management.

Provides:
- Embedding job lifecycle (create, start, cancel)
- Progress tracking
- Checkpoint management for resumable jobs
- Dynamic embedding model selection from ai_models table
"""
from app.modules.embeddings.models import EmbeddingJobModel, EmbeddingCheckpointModel
from app.modules.embeddings.schemas import (
    EmbeddingJobStatus,
    EmbeddingJobCreate,
    EmbeddingJobProgress,
    EmbeddingJobSummary,
    EmbeddingJobResponse,
    ChunkingConfig,
    ParallelizationConfig,
    MedicalContextConfig,
    CheckpointInfo
)
from app.modules.embeddings.repository import EmbeddingJobRepository, EmbeddingCheckpointRepository
from app.modules.embeddings.service import EmbeddingJobService
from app.modules.embeddings.routes import router

__all__ = [
    # Models
    "EmbeddingJobModel",
    "EmbeddingCheckpointModel",
    # Schemas
    "EmbeddingJobStatus",
    "EmbeddingJobCreate",
    "EmbeddingJobProgress",
    "EmbeddingJobSummary",
    "EmbeddingJobResponse",
    "ChunkingConfig",
    "ParallelizationConfig",
    "MedicalContextConfig",
    "CheckpointInfo",
    # Repository
    "EmbeddingJobRepository",
    "EmbeddingCheckpointRepository",
    # Service
    "EmbeddingJobService",
    # Router
    "router",
]
