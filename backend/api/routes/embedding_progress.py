"""
API routes for embedding job management and progress tracking.
Requires SuperAdmin role for all operations.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

from backend.models.schemas import User
from backend.models.rag_models import (
    EmbeddingJobCreate, EmbeddingJobProgress, EmbeddingJobSummary,
    EmbeddingJobStatus, RAGAuditAction
)
from backend.services.embedding_job_service import get_embedding_job_service, EmbeddingJobService
from backend.services.authorization_service import get_authorization_service, AuthorizationService
from backend.services.notification_service import get_notification_service, NotificationService
from backend.services.embedding_batch_processor import EmbeddingBatchProcessor, BatchConfig
from backend.services.embedding_document_generator import get_document_generator
from backend.core.permissions import require_super_admin, get_current_user
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/embedding-jobs", tags=["Embedding Jobs"])


@router.post("", response_model=dict, dependencies=[Depends(require_super_admin)])
async def start_embedding_job(
    request: EmbeddingJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_super_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service),
    auth_service: AuthorizationService = Depends(get_authorization_service)
):
    """
    Start a new embedding generation job.
    
    This kicks off async embedding generation and returns immediately
    with a job ID that can be used to track progress.
    
    Requires SuperAdmin role.
    """
    try:
        # Get document count (simplified - in reality would query schema)
        # TODO: Get actual document count from config
        total_documents = 100  # Placeholder
        
        # Create job
        job_id = job_service.create_job(
            config_id=request.config_id,
            total_documents=total_documents,
            user=current_user,
            batch_size=request.batch_size,
            max_concurrent=request.max_concurrent
        )
        
        # Log the action
        auth_service.log_rag_action(
            user=current_user,
            action=RAGAuditAction.EMBEDDING_STARTED,
            config_id=request.config_id,
            changes={
                "job_id": job_id,
                "total_documents": total_documents,
                "batch_size": request.batch_size
            }
        )
        
        # Start async background task
        background_tasks.add_task(
            _run_embedding_job,
            job_id=job_id,
            config_id=request.config_id,
            user_id=current_user.id
        )
        
        logger.info(f"Started embedding job {job_id} for config {request.config_id}")
        
        return {
            "status": "started",
            "job_id": job_id,
            "message": "Embedding generation started in background"
        }
        
    except Exception as e:
        logger.error(f"Failed to start embedding job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start embedding job: {str(e)}"
        )


from backend.services.sql_service import get_sql_service
from backend.sqliteDb.db import get_db_service
import json

async def _run_embedding_job(job_id: str, config_id: int, user_id: int):
    """Background task to run embedding generation."""
    job_service = get_embedding_job_service()
    notification_service = get_notification_service()
    db_service = get_db_service()
    sql_service = get_sql_service()
    
    try:
        # Start the job
        job_service.start_job(job_id)
        
        # 1. Fetch Configuration
        config = db_service.get_config_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration {config_id} not found")
            
        connection_id = config.get('connection_id')
        if not connection_id:
            raise ValueError("Configuration missing connection_id")
            
        # 2. Fetch Connection Details
        connection_info = db_service.get_db_connection_by_id(connection_id)
        if not connection_info:
            raise ValueError(f"Connection {connection_id} not found")
            
        # 3. Determine Selected Tables
        # schema_snapshot is stored as JSON string in rag_configurations
        schema_snapshot_raw = config.get('schema_snapshot', '{}')
        try:
            schema_selection = json.loads(schema_snapshot_raw)
            # If selection format is {'table': ['col']}, keys are tables
            # If selection format is just list ['table'], handle that too
            if isinstance(schema_selection, dict):
                target_tables = list(schema_selection.keys())
            elif isinstance(schema_selection, list):
                target_tables = schema_selection
            else:
                target_tables = []
        except:
            target_tables = []
            
        if not target_tables:
            raise ValueError("No tables selected in configuration")

        # 4. Fetch Live Schema Metadata
        # We need rich metadata (types, nullable, etc) which might not be in the snapshot
        schema_info = sql_service.get_schema_info_for_connection(
            connection_info['uri'], 
            table_names=target_tables
        )
        
        # 5. Transform for Document Generator
        # Generator expects {'tables': {'t1': {'columns': {'c1': {...}}}}}
        generator_schema = {'tables': {}}
        for table, cols in schema_info.get('details', {}).items():
            # Transform list of col dicts to dict of col dicts keyed by name
            col_dict = {}
            for col in cols:
                col_name = col['name']
                col_dict[col_name] = col
                
            generator_schema['tables'][table] = {'columns': col_dict}

        # 6. Generate Documents
        document_generator = get_document_generator()
        data_dictionary = config.get('data_dictionary', '')
        
        documents = document_generator.generate_all(
            generator_schema, 
            dictionary_content=data_dictionary
        )
        
        # Update job with accurate document count
        total_docs = len(documents)
        # We can update total_documents in the job record here if needed
        # But for now, we just proceed. Ideally we'd update the DB record.
        
        # Transition to embedding phase
        job_service.transition_to_embedding(job_id)
        
        # Process with batch processor
        # Max concurrent and batch size are stored in the job, but processor takes config
        # We'll use defaults or fetch from job metadata if we extended job service to return it
        processor = EmbeddingBatchProcessor(BatchConfig(
            batch_size=50,
            max_concurrent=5
        ))
        
        async def on_progress(processed: int, failed: int, total: int):
            current_batch = (processed // 50) + 1
            job_service.update_progress(job_id, processed, current_batch, failed)
        
        doc_contents = [d.content for d in documents]
        result = await processor.process_documents(
            doc_contents,
            on_progress=on_progress
        )
        
        if result["cancelled"]:
            return
        
        # Transition to validation
        job_service.transition_to_validating(job_id)
        
        # Simple validation
        validation_passed = result["failed_documents"] == 0
        
        # Transition to storing
        job_service.transition_to_storing(job_id)
        
        # TODO: Store actual vectors to vector database
        # For now we simulate storage success
        
        # Complete the job
        job_service.complete_job(job_id, validation_passed=validation_passed)
        
        # Send completion notification
        await notification_service.create_notification(
            user_id=user_id,
            notification_type="embedding_complete",
            title="Embedding Generation Complete",
            message=f"Successfully generated {result['processed_documents']} embeddings for v{config.get('version', 'unknown')}.",
            priority="medium",
            action_url=f"/config",
            action_label="View Configuration",
            related_entity_type="embedding_job",
            related_entity_id=0
        )
        
    except Exception as e:
        logger.error(f"Embedding job {job_id} failed: {e}")
        job_service.fail_job(job_id, str(e))
        
        # Send failure notification
        await notification_service.create_notification(
            user_id=user_id,
            notification_type="embedding_failed",
            title="Embedding Generation Failed",
            message=str(e),
            priority="high"
        )


@router.get("/{job_id}/progress", response_model=EmbeddingJobProgress)
async def get_embedding_progress(
    job_id: str,
    current_user: User = Depends(require_super_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service)
):
    """
    Get current progress of an embedding job.
    
    Use this for polling-based progress updates.
    For real-time updates, use the WebSocket endpoint.
    
    Requires SuperAdmin role.
    """
    progress = job_service.get_job_progress(job_id)
    
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    return progress


@router.get("/{job_id}/summary", response_model=EmbeddingJobSummary)
async def get_embedding_summary(
    job_id: str,
    current_user: User = Depends(require_super_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service)
):
    """
    Get summary of a completed embedding job.
    
    Requires SuperAdmin role.
    """
    summary = job_service.get_job_summary(job_id)
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    return summary


@router.post("/{job_id}/cancel", response_model=dict)
async def cancel_embedding_job(
    job_id: str,
    current_user: User = Depends(require_super_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service),
    auth_service: AuthorizationService = Depends(get_authorization_service)
):
    """
    Cancel a running embedding job.
    
    Only jobs in QUEUED, PREPARING, or EMBEDDING status can be cancelled.
    
    Requires SuperAdmin role.
    """
    success = job_service.cancel_job(job_id, current_user)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job cannot be cancelled (may be already completed or not found)"
        )
    
    # Log the cancellation
    auth_service.log_rag_action(
        user=current_user,
        action=RAGAuditAction.EMBEDDING_CANCELLED,
        changes={"job_id": job_id}
    )
    
    return {
        "status": "cancelled",
        "job_id": job_id,
        "message": "Embedding job cancelled successfully"
    }


@router.get("", response_model=List[EmbeddingJobProgress])
async def list_embedding_jobs(
    status_filter: Optional[EmbeddingJobStatus] = None,
    limit: int = 10,
    offset: int = 0,
    current_user: User = Depends(require_super_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service)
):
    """
    List all embedding jobs with optional filtering.
    
    Requires SuperAdmin role.
    """
    jobs = job_service.list_jobs(
        status=status_filter,
        limit=limit,
        offset=offset
    )
    
    return jobs
