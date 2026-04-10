"""
API routes for embedding job management.

Provides endpoints for:
- Starting embedding jobs
- Tracking progress
- Cancelling jobs
- Managing checkpoints
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import get_current_user, require_admin
from app.core.models.common import BaseResponse
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User
from app.modules.embeddings.service import EmbeddingJobService
from app.modules.embeddings.schemas import (
    EmbeddingJobCreate, EmbeddingJobProgress, EmbeddingJobSummary,
    EmbeddingJobResponse, CheckpointInfo
)

logger = get_logger(__name__)

router = APIRouter(prefix="/embedding-jobs", tags=["Embedding Jobs"])


def get_embedding_service(db: AsyncSession = Depends(get_db)) -> EmbeddingJobService:
    """Dependency to get embedding service."""
    return EmbeddingJobService(db)


# ============================================
# Job Management Endpoints
# ============================================

@router.post("", response_model=EmbeddingJobResponse, dependencies=[Depends(require_admin)])
async def start_embedding_job(
    request: EmbeddingJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Start a new embedding generation job.
    
    Only config_id is required - all settings are read from agent_config table.
    
    Requires Admin role or above.
    
    The embedding model is dynamically selected from the agent_config:
    - If embedding_model_id is set, uses the model from ai_models table
    - Otherwise falls back to embedding_config.model
    """
    try:
        # Create job record
        job_id = await service.create_job(request, current_user.id)
        
        # Start background job - pass batch_size and chunking from request
        chunking_override = None
        if request.chunking:
            chunking_override = {
                'parent_chunk_size': request.chunking.parent_chunk_size,
                'parent_chunk_overlap': request.chunking.parent_chunk_overlap,
                'child_chunk_size': request.chunking.child_chunk_size,
                'child_chunk_overlap': request.chunking.child_chunk_overlap,
            }
        
        await service.start_job_background(
            job_id=job_id,
            config_id=request.config_id,
            user_id=current_user.id,
            incremental=request.incremental,
            batch_size=request.batch_size,
            max_concurrent=request.max_concurrent,
            chunking_override=chunking_override
        )
        
        logger.info(f"Started embedding job {job_id} for config {request.config_id}")
        
        return EmbeddingJobResponse(
            status="started",
            job_id=job_id,
            message="Embedding generation started in background"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start embedding job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start embedding job: {str(e)}"
        )


@router.get("/{job_id}/progress", response_model=EmbeddingJobProgress)
async def get_job_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Get the current progress of an embedding job.
    
    Returns real-time progress including:
    - Current status and phase
    - Documents processed/failed
    - Processing speed
    - ETA
    """
    progress = await service.get_progress(job_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    return progress


@router.get("/{job_id}/summary", response_model=EmbeddingJobSummary)
async def get_job_summary(
    job_id: str,
    current_user: User = Depends(get_current_user),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Get the summary of a completed embedding job.
    
    Returns final statistics including:
    - Total duration
    - Documents processed/failed
    - Average processing speed
    - Validation status
    """
    summary = await service.get_summary(job_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    return summary


@router.post("/{job_id}/cancel", response_model=EmbeddingJobResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(require_admin),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Cancel a running embedding job.
    
    Requires Admin role or above.
    """
    try:
        success = await service.cancel_job(job_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
        return EmbeddingJobResponse(
            status="cancelled",
            job_id=job_id,
            message="Embedding job cancelled"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[EmbeddingJobProgress])
async def list_jobs(
    config_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    List embedding jobs with optional filtering.
    
    Args:
        config_id: Filter by configuration ID
        status: Filter by job status (QUEUED, PREPARING, EMBEDDING, etc.)
        limit: Maximum number of jobs to return
    """
    return await service.list_jobs(config_id=config_id, status=status, limit=limit)


# ============================================
# Checkpoint Endpoints
# ============================================

@router.get("/checkpoint/{vector_db_name}", response_model=CheckpointInfo)
async def get_checkpoint(
    vector_db_name: str,
    current_user: User = Depends(get_current_user),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Get checkpoint information for a vector database.
    
    Checkpoints allow resuming embedding jobs after failures.
    """
    checkpoint = await service.get_checkpoint(vector_db_name)
    if not checkpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint found for vector DB: {vector_db_name}"
        )
    return checkpoint


@router.delete("/checkpoint/{vector_db_name}", response_model=dict)
async def delete_checkpoint(
    vector_db_name: str,
    current_user: User = Depends(require_admin),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Delete checkpoint for a vector database.
    
    This clears the checkpoint, so the next embedding job will start fresh.
    Requires Admin role.
    """
    success = await service.delete_checkpoint(vector_db_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint found for vector DB: {vector_db_name}"
        )
    return {
        "status": "deleted",
        "vector_db_name": vector_db_name,
        "message": "Checkpoint deleted successfully"
    }


# ============================================
# Vector DB Status Endpoints
# ============================================

from app.modules.embeddings.schemas import VectorDbStatusResponse, DiagnosticItem

@router.get("/status/config/{config_id}", response_model=VectorDbStatusResponse)
async def get_vector_db_status_by_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    service: EmbeddingJobService = Depends(get_embedding_service)
):
    """
    Get vector database status for a specific agent configuration.
    
    Returns embedding job stats, document counts, and diagnostic info.
    """
    result = await service.get_vector_db_status(config_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration {config_id} not found"
        )
    return result
