"""
Embedding job service for managing embedding generation lifecycle.

Provides:
- Job creation with dynamic embedding model from agent_config
- Progress tracking
- Background job execution
- Checkpoint management
"""
import os
import sys
import json
import uuid
import math
import time
import asyncio
import threading
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.utils.logging import get_logger
from app.core.utils.exceptions import AppException, ErrorCode
from app.modules.embeddings.repository import EmbeddingJobRepository, EmbeddingCheckpointRepository
from app.modules.embeddings.schemas import (
    EmbeddingJobStatus, EmbeddingJobCreate, EmbeddingJobProgress,
    EmbeddingJobSummary, CheckpointInfo
)
from app.modules.embeddings.models import EmbeddingJobModel
from app.modules.agents.models import AgentConfigModel
from app.modules.ai_models.models import AIModel

logger = get_logger(__name__)

# Thread pool for running embedding jobs without blocking the event loop
_embedding_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedding_job_")


class EmbeddingJobService:
    """
    Service for managing embedding job lifecycle and progress tracking.
    
    State Machine:
    QUEUED -> PREPARING -> EMBEDDING -> VALIDATING -> STORING -> COMPLETED
    
    Any state can transition to FAILED or CANCELLED.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.jobs = EmbeddingJobRepository(db)
        self.checkpoints = EmbeddingCheckpointRepository(db)
    
    async def create_job(
        self,
        request: EmbeddingJobCreate,
        user_id: str
    ) -> str:
        """
        Create a new embedding job.
        
        All settings are read from agent_config table - only config_id is required.
        """
        # Get agent config
        stmt = select(AgentConfigModel).where(AgentConfigModel.id == request.config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            raise AppException(
                message=f"Configuration {request.config_id} not found",
                status_code=404,
                error_code=ErrorCode.RESOURCE_NOT_FOUND
            )
        
        # Get embedding model from ai_models table via FK
        embedding_model = None
        model_name = None
        if config.embedding_model_id:
            stmt = select(AIModel).where(AIModel.id == config.embedding_model_id)
            result = await self.db.execute(stmt)
            embedding_model = result.scalar_one_or_none()
            if embedding_model:
                model_name = embedding_model.model_id
                logger.info(f"Using embedding model from ai_models: {model_name}")
        
        # Fallback to embedding_config if no FK set
        emb_config = config.embedding_config or {}
        if isinstance(emb_config, str):
            emb_config = json.loads(emb_config)
        
        if not model_name:
            model_name = emb_config.get('model')
            if not model_name:
                raise AppException(
                    message="No embedding model configured. Please set embedding_model_id or embedding_config.model",
                    status_code=400,
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        # Get chunking config from agent_config
        chunking_config = config.chunking_config or {}
        if isinstance(chunking_config, str):
            chunking_config = json.loads(chunking_config)
        
        # Extract batch settings from embedding_config or use defaults
        # Default to 256 for faster processing
        batch_size = emb_config.get('batch_size', 256)
        max_concurrent = emb_config.get('max_concurrent', 5)
        
        # Generate job ID
        job_id = f"emb-job-{uuid.uuid4().hex[:12]}"
        
        # Estimate documents (will be updated when job starts)
        total_documents = 100  # Placeholder
        total_batches = math.ceil(total_documents / batch_size)
        
        # Build config metadata from agent_config
        config_metadata = {
            "batch_size": batch_size,
            "max_concurrent": max_concurrent,
            "incremental": request.incremental,
            "embedding_model": model_name,
            "embedding_model_id": config.embedding_model_id,
            "chunking": chunking_config,
        }
        
        # Create job record
        job = await self.jobs.create(
            job_id=job_id,
            config_id=request.config_id,
            total_documents=total_documents,
            total_batches=total_batches,
            batch_size=batch_size,
            started_by=user_id,
            config_metadata=config_metadata,
            incremental=request.incremental
        )
        
        logger.info(f"Created embedding job {job_id} for config {request.config_id}")
        return job_id
    
    async def start_job_background(
        self,
        job_id: str,
        config_id: int,
        user_id: str,
        incremental: bool = False
    ) -> None:
        """
        Start embedding job in background thread.
        
        All settings are read from agent_config table.
        """
        # Get config data needed for embedding
        stmt = select(AgentConfigModel).where(AgentConfigModel.id == config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            await self.jobs.update_status(
                job_id,
                EmbeddingJobStatus.FAILED,
                error_message=f"Configuration {config_id} not found"
            )
            return
        
        # Get embedding model info
        embedding_model_id = config.embedding_model_id
        emb_config = config.embedding_config or {}
        if isinstance(emb_config, str):
            emb_config = json.loads(emb_config)
        
        # Get chunking config
        chunking_config = config.chunking_config or {}
        if isinstance(chunking_config, str):
            chunking_config = json.loads(chunking_config)
        
        # Get rag config
        rag_config = config.rag_config or {}
        if isinstance(rag_config, str):
            rag_config = json.loads(rag_config)
        
        # Get model name from FK or config
        model_name = None
        api_key = None
        api_base_url = None
        
        if embedding_model_id:
            stmt = select(AIModel).where(AIModel.id == embedding_model_id)
            result = await self.db.execute(stmt)
            ai_model = result.scalar_one_or_none()
            if ai_model:
                model_name = ai_model.model_id
                api_base_url = ai_model.api_base_url
                # Get API key from ai_model
                if ai_model.api_key_env_var:
                    api_key = os.environ.get(ai_model.api_key_env_var)
                if not api_key and ai_model.api_key_encrypted:
                    from app.core.encryption import decrypt_value
                    api_key = decrypt_value(ai_model.api_key_encrypted)
        
        if not model_name:
            model_name = emb_config.get('model', 'huggingface/BAAI/bge-large-en-v1.5')
        
        # Extract batch settings from embedding_config or use defaults
        # Default to 256 for faster processing
        batch_size = emb_config.get('batch_size', 256)
        max_concurrent = emb_config.get('max_concurrent', 5)
        
        # Build config dict for background task - all from agent_config
        job_config = {
            "job_id": job_id,
            "config_id": config_id,
            "user_id": user_id,
            "agent_id": str(config.agent_id) if config.agent_id else None,
            "data_source_id": str(config.data_source_id) if config.data_source_id else None,
            "embedding_model": model_name,
            "embedding_model_id": embedding_model_id,
            "api_key": api_key,
            "api_base_url": api_base_url,
            "embedding_config": emb_config,
            "chunking_config": chunking_config,
            "rag_config": rag_config,
            "data_dictionary": config.data_dictionary,
            "selected_columns": config.selected_columns,
            "incremental": incremental,
            "batch_size": batch_size,
            "max_concurrent": max_concurrent,
        }
        
        # Submit to thread pool
        _embedding_executor.submit(
            _run_embedding_job_sync_wrapper,
            job_config
        )
        
        logger.info(f"Submitted embedding job {job_id} to background executor")
    
    async def get_progress(self, job_id: str) -> Optional[EmbeddingJobProgress]:
        """Get current progress of an embedding job."""
        job = await self.jobs.get_by_id(job_id)
        if not job:
            return None
        
        return self._job_to_progress(job)
    
    async def get_summary(self, job_id: str) -> Optional[EmbeddingJobSummary]:
        """Get summary of a completed embedding job."""
        job = await self.jobs.get_by_id(job_id)
        if not job:
            return None
        
        # Calculate duration
        duration = None
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
        
        # Calculate average speed
        avg_speed = None
        if duration and duration > 0 and job.processed_documents > 0:
            avg_speed = job.processed_documents / duration
        
        return EmbeddingJobSummary(
            job_id=job.job_id,
            status=EmbeddingJobStatus(job.status),
            total_documents=job.total_documents,
            processed_documents=job.processed_documents,
            failed_documents=job.failed_documents,
            duration_seconds=duration,
            average_speed=avg_speed,
            validation_passed=job.status == EmbeddingJobStatus.COMPLETED.value,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at
        )
    
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running embedding job."""
        job = await self.jobs.get_by_id(job_id)
        if not job:
            return False
        
        # Can only cancel if not already in final state
        if job.status in (EmbeddingJobStatus.COMPLETED.value, EmbeddingJobStatus.FAILED.value, EmbeddingJobStatus.CANCELLED.value):
            raise AppException(
                message=f"Job {job_id} is already in final state: {job.status}",
                status_code=400,
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        await self.jobs.update_status(
            job_id,
            EmbeddingJobStatus.CANCELLED,
            phase="Job cancelled by user"
        )
        
        logger.info(f"Cancelled embedding job {job_id}")
        return True
    
    async def list_jobs(
        self,
        config_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[EmbeddingJobProgress]:
        """
        List embedding jobs with optional filters.
        
        Automatically detects and marks stale jobs (in active status but no progress for 10+ min).
        """
        jobs = await self.jobs.list_jobs(config_id=config_id, status=status, limit=limit)
        
        # Check for stale jobs and mark them as failed
        active_statuses = ['QUEUED', 'PREPARING', 'EMBEDDING', 'VALIDATING', 'STORING']
        stale_threshold_minutes = 10  # Jobs with no progress for 10 minutes are considered stale
        now = datetime.utcnow()
        
        result = []
        for job in jobs:
            # Check if this job is potentially stale
            if job.status in active_statuses:
                last_update = getattr(job, 'updated_at', None) or job.created_at
                minutes_since_update = (now - last_update).total_seconds() / 60
                
                if minutes_since_update > stale_threshold_minutes:
                    # Mark job as failed due to stale state
                    logger.warning(f"Job {job.job_id} is stale (no update for {minutes_since_update:.1f} min), marking as FAILED")
                    await self.jobs.update_status(
                        job.job_id,
                        EmbeddingJobStatus.FAILED,
                        phase="Job stale - no progress detected",
                        error_message=f"Job became unresponsive (no progress for {minutes_since_update:.0f} minutes). This may happen if the server was restarted."
                    )
                    # Refresh the job data to get updated status
                    job = await self.jobs.get_by_id(job.job_id)
            
            if job:
                result.append(self._job_to_progress(job))
        
        return result
    
    async def get_checkpoint(self, vector_db_name: str) -> Optional[CheckpointInfo]:
        """Get checkpoint for a vector DB."""
        checkpoint = await self.checkpoints.get_by_vector_db(vector_db_name)
        if not checkpoint:
            return None
        
        return CheckpointInfo(
            vector_db_name=checkpoint.vector_db_name,
            phase=checkpoint.phase,
            created_at=checkpoint.created_at,
            updated_at=checkpoint.updated_at,
            checkpoint_data=checkpoint.checkpoint_data
        )
    
    async def delete_checkpoint(self, vector_db_name: str) -> bool:
        """Delete checkpoint for a vector DB."""
        return await self.checkpoints.delete(vector_db_name)
    
    async def get_vector_db_status(self, config_id: int) -> Optional[Dict[str, Any]]:
        """
        Get vector db status for a config, derived from embedding jobs.
        
        Returns status info including document counts, model names, and diagnostics.
        """
        from app.modules.embeddings.schemas import VectorDbStatusResponse, DiagnosticItem
        from sqlalchemy import desc
        
        logger.info(f"get_vector_db_status called for config_id={config_id}")
        
        # Get agent config
        stmt = select(AgentConfigModel).where(AgentConfigModel.id == config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            return None
        
        collection_name = config.vector_collection_name or f"config_{config_id}"
        
        # Get latest embedding job directly from the model (not DTO) to access total_vectors
        stmt = select(EmbeddingJobModel).where(
            EmbeddingJobModel.config_id == config_id
        ).order_by(desc(EmbeddingJobModel.created_at)).limit(1)
        result = await self.db.execute(stmt)
        latest_job = result.scalar_one_or_none()
        
        if latest_job:
            logger.info(f"Latest job found: job_id={latest_job.job_id}, status={latest_job.status}, docs={latest_job.processed_documents}, vectors={latest_job.total_vectors}")
        else:
            logger.info(f"No jobs found for config_id={config_id}")
        
        # Get last completed full and incremental jobs
        stmt = select(EmbeddingJobModel).where(
            EmbeddingJobModel.config_id == config_id,
            EmbeddingJobModel.status == "COMPLETED"
        ).order_by(desc(EmbeddingJobModel.created_at)).limit(20)
        result = await self.db.execute(stmt)
        completed_jobs = result.scalars().all()
        
        last_full_job = None
        last_incremental_job = None
        for job in completed_jobs:
            is_incremental = job.incremental if hasattr(job, 'incremental') else False
            if is_incremental and not last_incremental_job:
                last_incremental_job = job
            elif not is_incremental and not last_full_job:
                last_full_job = job
            if last_full_job and last_incremental_job:
                break
        
        # Get model names
        embedding_model_name = None
        if config.embedding_model_id:
            model_stmt = select(AIModel).where(AIModel.id == config.embedding_model_id)
            model_result = await self.db.execute(model_stmt)
            model = model_result.scalar_one_or_none()
            if model:
                embedding_model_name = model.display_name
        
        llm_model_name = None
        if config.llm_model_id:
            model_stmt = select(AIModel).where(AIModel.id == config.llm_model_id)
            model_result = await self.db.execute(model_stmt)
            model = model_result.scalar_one_or_none()
            if model:
                llm_model_name = model.display_name
        
        # Calculate totals - use the job model directly to get total_vectors
        total_docs = 0
        total_vectors = 0
        if latest_job and latest_job.status == "COMPLETED":
            total_docs = latest_job.processed_documents or 0
            total_vectors = latest_job.total_vectors or 0
        elif last_full_job:
            total_docs = last_full_job.processed_documents or 0
            total_vectors = last_full_job.total_vectors or 0
        
        # Build diagnostics
        diagnostics = []
        embedding_status = config.embedding_status
        
        if embedding_status == "not_started":
            diagnostics.append(DiagnosticItem(
                level="info",
                message="Embedding has not been started yet. Run an embedding job to index documents."
            ))
        elif embedding_status == "in_progress":
            diagnostics.append(DiagnosticItem(
                level="info",
                message="Embedding job is currently in progress."
            ))
        elif embedding_status == "failed":
            error_msg = latest_job.error_message if latest_job else "Unknown error"
            diagnostics.append(DiagnosticItem(
                level="error",
                message=f"Last embedding job failed: {error_msg}"
            ))
        
        # Determine last updated
        last_updated = config.updated_at
        if latest_job and latest_job.completed_at:
            last_updated = latest_job.completed_at
        
        exists = embedding_status == "completed" or total_vectors > 0
        
        # Get vector store type from factory
        from app.modules.embeddings.vector_stores.factory import get_vector_store_type
        vector_db_type = get_vector_store_type()
        
        logger.info(f"Returning VectorDbStatusResponse: docs={total_docs}, vectors={total_vectors}, vector_db_type={vector_db_type}")
        
        return VectorDbStatusResponse(
            name=collection_name,
            exists=exists,
            total_documents_indexed=total_docs,
            total_vectors=total_vectors,
            last_updated_at=last_updated,
            embedding_model=embedding_model_name,
            llm=llm_model_name,
            last_full_run=last_full_job.completed_at if last_full_job else None,
            last_incremental_run=last_incremental_job.completed_at if last_incremental_job else None,
            version="1.0.0",
            diagnostics=diagnostics,
            embedding_status=embedding_status,
            last_job_id=latest_job.job_id if latest_job else None,
            last_job_status=latest_job.status if latest_job else None,
            vector_db_type=vector_db_type
        )
    
    def _job_to_progress(self, job: EmbeddingJobModel) -> EmbeddingJobProgress:
        """Convert job model to progress DTO."""
        # Calculate elapsed and ETA
        elapsed_seconds = None
        eta_seconds = None
        
        if job.started_at:
            elapsed_seconds = int((datetime.utcnow() - job.started_at).total_seconds())
            
            if job.estimated_completion_at:
                eta_seconds = int((job.estimated_completion_at - datetime.utcnow()).total_seconds())
                if eta_seconds < 0:
                    eta_seconds = 0
        
        return EmbeddingJobProgress(
            job_id=job.job_id,
            status=EmbeddingJobStatus(job.status),
            phase=job.phase,
            total_documents=job.total_documents,
            processed_documents=job.processed_documents,
            failed_documents=job.failed_documents,
            progress_percentage=job.progress_percentage,
            current_batch=job.current_batch,
            total_batches=job.total_batches,
            documents_per_second=job.documents_per_second,
            estimated_time_remaining_seconds=eta_seconds,
            elapsed_seconds=elapsed_seconds,
            errors_count=job.errors_count,
            recent_errors=job.recent_errors or [],
            started_at=job.started_at,
            completed_at=job.completed_at
        )


def _run_embedding_job_sync_wrapper(job_config: Dict[str, Any]):
    """
    Synchronous wrapper that creates a new event loop for the async embedding job.
    This runs in a separate thread to avoid blocking the main FastAPI event loop.
    """
    job_id = job_config.get('job_id', 'unknown')
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Reset the background engine for this new event loop
        # This is critical - the old engine was bound to a different event loop
        _reset_background_engine()
        
        try:
            loop.run_until_complete(_run_embedding_job(job_config))
        finally:
            # Clean up properly before closing the loop
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # Give tasks a chance to clean up
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                
                # Dispose of the engine before closing the loop
                _dispose_background_engine_sync(loop)
            except Exception as cleanup_error:
                logger.warning(f"Cleanup warning for job {job_id}: {cleanup_error}")
            finally:
                loop.close()
                
    except Exception as e:
        logger.error(f"Embedding job {job_id} thread failed: {e}")
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(error_traceback)
        
        # Try to update job status to FAILED using a new event loop
        try:
            update_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(update_loop)
            _reset_background_engine()  # Reset for new loop
            try:
                update_loop.run_until_complete(
                    _update_job_status(
                        job_id,
                        EmbeddingJobStatus.FAILED,
                        phase="Job failed (sync wrapper)",
                        error_message=f"{str(e)[:500]}... (see logs for full traceback)"
                    )
                )
                _dispose_background_engine_sync(update_loop)
            finally:
                update_loop.close()
        except Exception as update_error:
            logger.error(f"Failed to update job {job_id} status after error: {update_error}")


# Thread-local storage for background engine to avoid event loop conflicts
_background_engine_local = threading.local()


def _reset_background_engine():
    """Reset the background engine for a new event loop."""
    global _background_engine_local
    _background_engine_local.engine = None
    _background_engine_local.session_factory = None


def _dispose_background_engine_sync(loop):
    """Dispose of the background engine before closing the event loop."""
    global _background_engine_local
    engine = getattr(_background_engine_local, 'engine', None)
    if engine is not None:
        try:
            loop.run_until_complete(engine.dispose())
        except Exception as e:
            logger.debug(f"Engine dispose warning: {e}")
        finally:
            _background_engine_local.engine = None
            _background_engine_local.session_factory = None


def _get_background_engine():
    """Get or create a thread-local engine for background tasks."""
    global _background_engine_local
    
    engine = getattr(_background_engine_local, 'engine', None)
    session_factory = getattr(_background_engine_local, 'session_factory', None)
    
    if engine is None:
        from app.core.config import get_settings
        settings = get_settings()
        
        db_url = f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        
        # Create a thread-local engine 
        engine = create_async_engine(
            db_url, 
            echo=False,
            pool_size=3,  # Smaller pool for background jobs
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=300  # Recycle connections every 5 minutes
        )
        session_factory = async_sessionmaker(
            engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
        
        _background_engine_local.engine = engine
        _background_engine_local.session_factory = session_factory
        logger.info("Created thread-local background database engine")
    
    return engine, session_factory


@asynccontextmanager
async def _get_background_db_session():
    """
    Get a database session from the shared background engine.
    
    PERFORMANCE FIX: Reuses a shared engine with connection pooling instead of
    creating a new engine for every call (which was causing massive overhead!).
    """
    _, session_factory = _get_background_engine()
    
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Background session error: {e}")
            await session.rollback()
            raise


async def _update_job_status(job_id: str, status: EmbeddingJobStatus, phase: str = None, error_message: str = None):
    """Helper to update job status using a new database session."""
    async with _get_background_db_session() as session:
        repo = EmbeddingJobRepository(session)
        await repo.update_status(job_id, status, phase=phase, error_message=error_message)


async def _update_job_progress(job_id: str, processed: int, current_batch: int, total: int, phase: str, elapsed_seconds: float = 0):
    """Helper to update job progress using a new database session."""
    async with _get_background_db_session() as session:
        repo = EmbeddingJobRepository(session)
        progress_pct = (processed / total * 100) if total > 0 else 0
        
        # Calculate speed and ETA
        docs_per_second = None
        estimated_completion = None
        
        if elapsed_seconds > 0 and processed > 0:
            docs_per_second = processed / elapsed_seconds
            remaining_docs = total - processed
            if docs_per_second > 0:
                remaining_seconds = remaining_docs / docs_per_second
                from datetime import datetime, timedelta
                estimated_completion = datetime.utcnow() + timedelta(seconds=remaining_seconds)
        
        await repo.update_progress(
            job_id=job_id,
            processed_documents=processed,
            current_batch=current_batch,
            progress_percentage=progress_pct,
            documents_per_second=docs_per_second,
            estimated_completion_at=estimated_completion,
            phase=phase
        )


# Module-level cache for embedding models to avoid reloading for each job
# Key: model_name, Value: (model_instance, embed_function)
_EMBEDDING_MODEL_CACHE: Dict[str, Any] = {}


async def _get_embedding_provider(model_name: str, api_key: str = None, api_base_url: str = None):
    """
    Get an embedding provider based on model configuration.
    
    Uses caching to avoid reloading large models like BGE-M3 (~2.2GB) for each job.
    
    Supports:
    - OpenAI: openai/text-embedding-3-small, openai/text-embedding-3-large
    - HuggingFace local: huggingface/BAAI/bge-large-en-v1.5
    - Azure: azure/text-embedding-ada-002
    """
    global _EMBEDDING_MODEL_CACHE
    import os
    
    provider_name = model_name.split('/')[0].lower() if '/' in model_name else 'openai'
    
    if provider_name == 'openai':
        # Use OpenAI embeddings
        from openai import AsyncOpenAI
        
        actual_model = model_name.replace('openai/', '') if model_name.startswith('openai/') else model_name
        key = api_key or os.environ.get('OPENAI_API_KEY')
        
        if not key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY or configure in AI Models.")
        
        client = AsyncOpenAI(api_key=key, base_url=api_base_url)
        
        async def embed_texts(texts: List[str]) -> List[List[float]]:
            response = await client.embeddings.create(
                model=actual_model,
                input=texts
            )
            return [item.embedding for item in response.data]
        
        return embed_texts
    
    elif provider_name == 'huggingface':
        # Use local HuggingFace model with sentence-transformers
        # Uses caching to avoid reloading large models for each job
        import torch
        import os as _os
        
        # Enable tokenizer parallelism for faster preprocessing (critical for CPU performance!)
        _os.environ["TOKENIZERS_PARALLELISM"] = "true"
        
        actual_model = model_name.replace('huggingface/', '') if model_name.startswith('huggingface/') else model_name
        cache_key = f"huggingface:{actual_model}"
        
        # Check if model is already cached
        if cache_key in _EMBEDDING_MODEL_CACHE:
            logger.info(f"Using cached embedding model: {actual_model}")
            model, embed_fn = _EMBEDDING_MODEL_CACHE[cache_key]
            return embed_fn
        
        # Try multiple local paths
        from app.core.config import get_settings
        settings = get_settings()
        
        # Model name like "BAAI/bge-m3" -> check paths:
        model_parts = actual_model.split('/')
        possible_paths = [
            settings.data_dir / "models" / actual_model,  # data/models/BAAI/bge-m3
            Path(f"./models/{model_parts[-1]}"),  # models/bge-m3
            Path(f"./data/models/{actual_model}"),  # data/models/BAAI/bge-m3
            Path(f"../backend/models/{model_parts[-1]}"),  # ../backend/models/bge-m3
        ]
        
        local_path = None
        for path in possible_paths:
            if path.exists():
                local_path = str(path)
                logger.info(f"Found embedding model at: {local_path}")
                break
        
        # Auto-detect best device (GPU acceleration)
        device = "cpu"
        if torch.cuda.is_available():
            device = "cuda"
            logger.info("CUDA GPU detected, using GPU acceleration")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            try:
                # Test MPS functionality
                test_tensor = torch.zeros(1, device="mps")
                del test_tensor
                device = "mps"
                logger.info("Apple MPS detected, using GPU acceleration")
            except Exception:
                logger.warning("MPS available but not functional, using CPU")
        else:
            logger.info("No GPU detected, using CPU (this will be slow for large models)")
        
        # Load model in a thread to avoid blocking
        logger.info(f"Loading embedding model '{actual_model}' on {device} (first load may take 1-2 min)...")
        
        def _load_model():
            from sentence_transformers import SentenceTransformer
            if local_path:
                m = SentenceTransformer(local_path, device=device)
                logger.info(f"Loaded embedding model from local path: {local_path} on {device}")
            else:
                logger.info(f"Model not found locally, downloading from HuggingFace: {actual_model}")
                m = SentenceTransformer(actual_model, device=device)
                logger.info(f"Loaded embedding model from HuggingFace: {actual_model} on {device}")
            
            # Pre-warm the model with a test embedding
            logger.info("Pre-warming embedding model...")
            _ = m.encode(["test"], convert_to_numpy=True)
            logger.info("Embedding model ready!")
            return m
        
        # Load model in executor - get loop fresh to avoid stale reference issues
        loop = asyncio.get_event_loop()
        model = await loop.run_in_executor(None, _load_model)
        
        # Track embedding calls for MPS cache management
        _embed_call_count = [0]
        _MPS_CACHE_CLEAR_INTERVAL = 50
        
        # CRITICAL: Do NOT capture `loop` in the closure! Get it fresh each time.
        # The cached function may be called from a different thread/event loop,
        # and using a stale loop reference causes massive slowdowns or hangs.
        
        # PERFORMANCE FIX: Return a sync function instead of async
        # The old backend uses sync embedding wrapped in executor at a higher level
        # Wrapping each call in executor per-batch adds significant overhead
        
        def embed_texts_sync(texts: List[str]) -> List[List[float]]:
            """
            Synchronous embedding function - much faster than per-batch async!
            
            The caller should wrap this in run_in_executor if needed.
            """
            nonlocal _embed_call_count
            _embed_call_count[0] += 1
            
            # Use optimized encoding settings (matching old backend BGEProvider)
            embeddings = model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=128,  # Internal batch size for model
                convert_to_numpy=True  # Efficient GPU→CPU transfer
            )
            
            # Clear GPU cache periodically to prevent MPS memory leak
            if _embed_call_count[0] % _MPS_CACHE_CLEAR_INTERVAL == 0:
                try:
                    if device == "mps" and hasattr(torch.mps, 'empty_cache'):
                        torch.mps.empty_cache()
                        if hasattr(torch.mps, 'synchronize'):
                            torch.mps.synchronize()
                    elif device == "cuda":
                        torch.cuda.empty_cache()
                except Exception:
                    pass  # Don't fail on cache clear errors
            
            return embeddings.tolist()
        
        # Cache the model and SYNC embed function
        _EMBEDDING_MODEL_CACHE[cache_key] = (model, embed_texts_sync)
        logger.info(f"Cached embedding model (sync): {cache_key}")
        
        return embed_texts_sync
    
    elif provider_name == 'azure':
        # Use Azure OpenAI embeddings
        from openai import AsyncAzureOpenAI
        
        actual_model = model_name.replace('azure/', '') if model_name.startswith('azure/') else model_name
        key = api_key or os.environ.get('AZURE_OPENAI_API_KEY')
        endpoint = api_base_url or os.environ.get('AZURE_OPENAI_ENDPOINT')
        
        if not key or not endpoint:
            raise ValueError("Azure OpenAI credentials not configured.")
        
        client = AsyncAzureOpenAI(
            api_key=key,
            api_version="2024-02-01",
            azure_endpoint=endpoint
        )
        
        async def embed_texts(texts: List[str]) -> List[List[float]]:
            response = await client.embeddings.create(
                model=actual_model,
                input=texts
            )
            return [item.embedding for item in response.data]
        
        return embed_texts
    
    else:
        raise ValueError(f"Unsupported embedding provider: {provider_name}. Supported: openai, huggingface, azure")


async def _extract_documents_from_postgres(
    db_url: str,
    selected_columns: Dict[str, List[str]],
    batch_size: int = 1000
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Extract documents from PostgreSQL database for embedding.
    
    Args:
        db_url: PostgreSQL connection URL
        selected_columns: Dict mapping table names to list of columns
        batch_size: Rows per fetch batch (streaming cursor)
    
    Returns:
        tuple: (total_count, list of document dicts with 'id', 'content', 'metadata')
    """
    from sqlalchemy import create_engine, text
    
    # Convert async URL to sync if needed
    sync_url = db_url.replace('+asyncpg', '').replace('postgresql+psycopg2', 'postgresql')
    if not sync_url.startswith('postgresql'):
        sync_url = sync_url.replace('postgres://', 'postgresql://')
    
    logger.info(f"Connecting to PostgreSQL: {sync_url.split('@')[1] if '@' in sync_url else sync_url}")
    
    engine = create_engine(sync_url)
    
    all_documents = []
    total_count = 0
    
    try:
        with engine.connect() as conn:
            for table_name, columns in selected_columns.items():
                if not columns:
                    continue
                
                logger.info(f"Extracting from table {table_name}, columns: {columns}")
                
                # Get row count
                count_result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                table_count = count_result.scalar() or 0
                total_count += table_count
                
                logger.info(f"Table {table_name} has {table_count} rows")
                
                if table_count == 0:
                    continue
                
                # Build column list - look for ID column
                id_column = None
                for candidate in ['id', 'ID', 'row_id', 'patient_id', 'record_id']:
                    if candidate in columns or candidate.lower() in [c.lower() for c in columns]:
                        id_column = candidate
                        break
                
                # If no ID column found, try to get one from the table
                if not id_column:
                    try:
                        pk_result = conn.execute(text(f"""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = :table AND table_schema = 'public'
                            ORDER BY ordinal_position
                            LIMIT 1
                        """), {"table": table_name})
                        first_col = pk_result.scalar()
                        if first_col:
                            id_column = first_col
                    except Exception:
                        pass
                
                # Build query
                safe_columns = [f'"{c}"' for c in columns]
                columns_sql = ", ".join(safe_columns)
                
                if id_column and id_column not in columns:
                    query = f'SELECT "{id_column}", {columns_sql} FROM "{table_name}" LIMIT :limit OFFSET :offset'
                    has_separate_id = True
                elif id_column:
                    query = f'SELECT {columns_sql} FROM "{table_name}" LIMIT :limit OFFSET :offset'
                    has_separate_id = False
                else:
                    # Use row number as ID
                    query = f'SELECT ROW_NUMBER() OVER () as _row_id, {columns_sql} FROM "{table_name}" LIMIT :limit OFFSET :offset'
                    has_separate_id = True
                
                # Extract in batches
                offset = 0
                while offset < table_count:
                    rows = conn.execute(text(query), {"limit": batch_size, "offset": offset}).fetchall()
                    
                    for row in rows:
                        if has_separate_id:
                            row_id = str(row[0])
                            col_start = 1
                        else:
                            # Use first column as ID
                            row_id = str(row[0]) if row[0] is not None else str(offset)
                            col_start = 0
                        
                        # Combine columns into document text
                        text_parts = []
                        metadata = {"table": table_name, "row_id": row_id}
                        
                        for i, col in enumerate(columns):
                            value = row[col_start + i] if col_start + i < len(row) else None
                            if value is not None:
                                value_str = str(value).strip()
                                if value_str and value_str.lower() not in ('none', 'null', 'nan', ''):
                                    text_parts.append(f"{col}: {value_str}")
                                    metadata[col] = value_str[:200]  # Truncate metadata
                        
                        if text_parts:
                            all_documents.append({
                                "id": f"{table_name}_{row_id}",
                                "content": "\n".join(text_parts),
                                "metadata": metadata
                            })
                    
                    offset += batch_size
                
                logger.info(f"Extracted {len([d for d in all_documents if d['metadata']['table'] == table_name])} documents from {table_name}")
        
        return total_count, all_documents
    
    finally:
        engine.dispose()


async def _extract_documents_from_duckdb(
    duckdb_path: str,
    table_name: str,
    columns: List[str],
    batch_size: int = 50000,  # PERFORMANCE: Large batches for streaming
    job_id: str = None,
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Extract documents from DuckDB for embedding.
    
    Args:
        duckdb_path: Path to DuckDB file
        table_name: Table to extract from  
        columns: Columns to include
        batch_size: Rows per fetch batch (streaming cursor)
        job_id: Optional job ID for progress updates to frontend
    
    Returns:
        tuple: (total_count, list of document dicts with 'id', 'content', 'metadata')
    """
    import duckdb
    
    if not os.path.exists(duckdb_path):
        raise ValueError(f"DuckDB file not found: {duckdb_path}")
    
    conn = duckdb.connect(duckdb_path, read_only=True)
    
    try:
        # Get total row count
        count_result = conn.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()
        total_count = count_result[0] if count_result else 0
        
        logger.info(f"Found {total_count} rows in table {table_name}")
        
        # Build column list for query - use all text columns
        safe_columns = [f'"{c}"' for c in columns]
        columns_sql = ", ".join(safe_columns)
        
        # Also get a row identifier if available
        # Try common ID column names
        id_columns = ['id', 'ID', 'row_id', 'index', 'reviewid', 'record_id', 'patient_id', 'res_id', 'encounter_id']
        id_column = None
        table_columns = [col[0] for col in conn.execute(f"DESCRIBE \"{table_name}\"").fetchall()]
        for ic in id_columns:
            if ic in table_columns:
                id_column = ic
                break
        
        logger.info(f"Using ID column: {id_column or 'ROW_NUMBER()'}")
        
        # PERFORMANCE: Use streaming cursor instead of LIMIT/OFFSET
        # This avoids O(n^2) scanning that happens with OFFSET pagination
        if id_column:
            query = f'SELECT "{id_column}", {columns_sql} FROM "{table_name}"'
        else:
            query = f'SELECT ROW_NUMBER() OVER () as _row_num, {columns_sql} FROM "{table_name}"'
        
        logger.info(f"Starting FAST streaming extraction (no OFFSET pagination)")
        extraction_start = time.time()
        
        # Execute query and use streaming fetchmany() - MUCH faster than OFFSET!
        result = conn.execute(query)
        
        documents = []
        rows_processed = 0
        last_progress_update = 0
        
        while True:
            # Fetch batch using streaming cursor (no OFFSET scanning!)
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            
            for row in rows:
                row_id = str(row[0])
                text_parts = []
                metadata = {"table": table_name, "row_id": row_id}
                
                for i, col in enumerate(columns):
                    value = row[i + 1]
                    if value is not None:
                        value_str = str(value).strip()
                        if value_str and value_str.lower() not in ('none', 'null', 'nan', ''):
                            text_parts.append(f"{col}: {value_str}")
                            if i < 5:
                                metadata[col] = value_str[:100]
                
                if text_parts:
                    documents.append({
                        "id": f"{table_name}_{row_id}",
                        "content": "\n".join(text_parts),
                        "metadata": metadata
                    })
            
            rows_processed += len(rows)
            
            # Log and update progress every 100K rows
            if rows_processed - last_progress_update >= 100000 or rows_processed >= total_count:
                last_progress_update = rows_processed
                elapsed = time.time() - extraction_start
                rate = rows_processed / elapsed if elapsed > 0 else 0
                progress_pct = rows_processed * 100 / total_count
                logger.info(f"Extraction progress: {rows_processed}/{total_count} rows ({progress_pct:.1f}%), {len(documents)} docs, {rate:.0f} rows/sec")
                
                # Update job progress in database for frontend visibility
                if job_id:
                    try:
                        await _update_job_status(
                            job_id, 
                            EmbeddingJobStatus.PREPARING, 
                            phase=f"Extracting data: {rows_processed:,}/{total_count:,} rows ({progress_pct:.1f}%)"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update extraction progress: {e}")
        
        extraction_time = time.time() - extraction_start
        logger.info(f"Extraction complete: {len(documents)} documents from {total_count} rows in {extraction_time:.1f}s")
        
        return total_count, documents
    
    finally:
        conn.close()

async def _run_embedding_job(job_config: Dict[str, Any]):
    """
    Background task to run embedding generation.
    
    Performs actual embedding generation using configured model and stores in ChromaDB.
    """
    job_id = job_config.get("job_id")
    if not job_id:
        logger.error("No job_id in job_config!")
        return
    
    config_id = job_config.get("config_id")
    if not config_id:
        logger.error(f"Job {job_id}: No config_id in job_config!")
        await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="No config_id provided")
        return
    
    embedding_model = job_config.get("embedding_model", "huggingface/BAAI/bge-large-en-v1.5")
    api_key = job_config.get("api_key")
    api_base_url = job_config.get("api_base_url")
    chunking_config = job_config.get("chunking_config") or {}
    data_dictionary = job_config.get("data_dictionary") or {}
    selected_columns_raw = job_config.get("selected_columns") or {}
    batch_size = job_config.get("batch_size") or 500  # PERFORMANCE: Larger batches for better GPU utilization
    incremental = job_config.get("incremental", False)
    data_source_id = job_config.get("data_source_id")
    
    logger.info(f"Starting embedding job {job_id} for config {config_id}")
    logger.info(f"Job {job_id} config: model={embedding_model}, batch_size={batch_size}, incremental={incremental}")
    
    job_start_time = time.time()  # Track total job time
    
    try:
        # Update status to PREPARING
        phase_start = time.time()
        logger.info(f"Job {job_id}: Updating status to PREPARING...")
        await _update_job_status(job_id, EmbeddingJobStatus.PREPARING, phase="Loading configuration...")
        logger.info(f"Job {job_id}: Status updated to PREPARING in {time.time() - phase_start:.2f}s")
        
        # Parse selected_columns (JSON string or dict)
        selected_columns = selected_columns_raw
        if isinstance(selected_columns, str):
            try:
                selected_columns = json.loads(selected_columns)
            except json.JSONDecodeError:
                logger.warning(f"Job {job_id}: Failed to parse selected_columns JSON")
                selected_columns = {}
        
        logger.info(f"Job {job_id}: selected_columns has {len(selected_columns) if selected_columns else 0} tables")
        
        # Get data source and agent info
        from app.modules.agents.models import AgentConfigModel
        from app.modules.data_sources.models import DataSourceModel
        
        # Data source info - could be file (DuckDB) or database (PostgreSQL)
        source_type = None
        duckdb_path = None
        duckdb_table_name = None
        db_url = None
        agent_id = "unknown"
        
        logger.info(f"Job {job_id}: Opening database session to fetch config...")
        async with _get_background_db_session() as session:
            logger.info(f"Job {job_id}: Database session opened, fetching config {config_id}...")
            # Get config
            stmt = select(AgentConfigModel).where(AgentConfigModel.id == config_id)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            
            if not config:
                logger.error(f"Job {job_id}: Configuration {config_id} not found!")
                await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="Configuration not found")
                return
            
            logger.info(f"Job {job_id}: Config found, agent_id={config.agent_id}, data_source_id={config.data_source_id}")
            agent_id = str(config.agent_id) if config.agent_id else "unknown"
            data_source_id = config.data_source_id
            
            # Get data source
            if data_source_id:
                logger.info(f"Job {job_id}: Fetching data source {data_source_id}...")
                ds_stmt = select(DataSourceModel).where(DataSourceModel.id == data_source_id)
                ds_result = await session.execute(ds_stmt)
                data_source = ds_result.scalar_one_or_none()
                
                if data_source:
                    source_type = data_source.source_type  # 'file' or 'database'
                    duckdb_path = data_source.duckdb_file_path
                    duckdb_table_name = data_source.duckdb_table_name
                    db_url = data_source.db_url
                    logger.info(f"Job {job_id}: Data source found: type={source_type}, db_url={db_url[:50] if db_url else 'None'}...")
                else:
                    logger.error(f"Job {job_id}: Data source {data_source_id} not found!")
            else:
                logger.error(f"Job {job_id}: No data_source_id in config!")
        
        logger.info(f"Job {job_id}: Database session closed. source_type={source_type}. Elapsed since start: {time.time() - job_start_time:.2f}s")
        
        # Validate data source configuration
        if source_type == 'file':
            if not duckdb_path or not duckdb_table_name:
                await _update_job_status(
                    job_id, 
                    EmbeddingJobStatus.FAILED, 
                    error_message="File data source not configured. Please upload a file first."
                )
                return
        elif source_type == 'database':
            if not db_url:
                await _update_job_status(
                    job_id, 
                    EmbeddingJobStatus.FAILED, 
                    error_message="Database connection URL not configured."
                )
                return
        else:
            await _update_job_status(
                job_id, 
                EmbeddingJobStatus.FAILED, 
                error_message=f"Unknown data source type: {source_type}. Expected 'file' or 'database'."
            )
            return
        
        # Generate vector DB name
        vector_db_name = f"agent_{agent_id}_config_{config_id}"
        
        logger.info(f"Job {job_id}: Using embedding model {embedding_model}, vector DB: {vector_db_name}")
        
        # Update phase
        await _update_job_status(job_id, EmbeddingJobStatus.PREPARING, phase="Extracting documents from data source...")
        
        # Extract documents based on source type
        try:
            if source_type == 'database':
                # For database sources, selected_columns is already {"table": ["col1", "col2"]}
                if not selected_columns:
                    await _update_job_status(
                        job_id, 
                        EmbeddingJobStatus.FAILED, 
                        error_message="No tables/columns selected for embedding. Please configure selected columns."
                    )
                    return
                
                logger.info(f"Extracting from database: {len(selected_columns)} tables, columns: {selected_columns}")
                
                total_count, documents = await _extract_documents_from_postgres(
                    db_url=db_url,
                    selected_columns=selected_columns,
                    batch_size=1000
                )
            else:
                # For file sources, need to get columns for the specific DuckDB table
                columns_to_embed = []
                if selected_columns and isinstance(selected_columns, dict):
                    # Format: {"table_name": ["col1", "col2"]}
                    if duckdb_table_name in selected_columns:
                        columns_to_embed = selected_columns[duckdb_table_name]
                    else:
                        # Take all columns from first table
                        for t, cols in selected_columns.items():
                            columns_to_embed = cols
                            break
                
                if not columns_to_embed:
                    await _update_job_status(
                        job_id, 
                        EmbeddingJobStatus.FAILED, 
                        error_message="No columns selected for embedding. Please configure selected columns."
                    )
                    return
                
                logger.info(f"Extracting from DuckDB: table={duckdb_table_name}, columns={columns_to_embed}")
                
                total_count, documents = await _extract_documents_from_duckdb(
                    duckdb_path=duckdb_path,
                    table_name=duckdb_table_name,
                    columns=columns_to_embed,
                    batch_size=1000,
                    job_id=job_id,
                )
        except Exception as e:
            logger.error(f"Failed to extract documents: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await _update_job_status(
                job_id, 
                EmbeddingJobStatus.FAILED, 
                error_message=f"Failed to extract documents: {str(e)}"
            )
            return
        
        if not documents:
            await _update_job_status(
                job_id, 
                EmbeddingJobStatus.FAILED, 
                error_message="No documents found to embed. Check if the selected columns have data."
            )
            return
        
        total_documents = len(documents)
        batch_count = (total_documents + batch_size - 1) // batch_size
        
        logger.info(f"Extracted {total_documents} documents for embedding ({batch_count} batches). Elapsed since start: {time.time() - job_start_time:.2f}s")
        
        # Update job with actual document count
        async with _get_background_db_session() as session:
            from sqlalchemy import update as sql_update
            from app.modules.embeddings.models import EmbeddingJobModel
            stmt = sql_update(EmbeddingJobModel).where(
                EmbeddingJobModel.job_id == job_id
            ).values(
                total_documents=total_documents,
                total_batches=batch_count
            )
            await session.execute(stmt)
        
        # Update status to EMBEDDING - model loading can take 1-2 minutes for large models
        await _update_job_status(job_id, EmbeddingJobStatus.EMBEDDING, phase="Loading embedding model (this may take 1-2 min for large models)...")
        
        # Get embedding provider
        model_load_start = time.time()
        try:
            embed_fn = await _get_embedding_provider(embedding_model, api_key, api_base_url)
            model_load_time = time.time() - model_load_start
            logger.info(f"Job {job_id}: Embedding provider loaded in {model_load_time:.2f}s. Total elapsed: {time.time() - job_start_time:.2f}s")
        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            await _update_job_status(
                job_id, 
                EmbeddingJobStatus.FAILED, 
                error_message=f"Failed to initialize embedding model: {str(e)}"
            )
            return
        
        # Initialize Vector Store using factory pattern (supports Qdrant and ChromaDB)
        await _update_job_status(job_id, EmbeddingJobStatus.EMBEDDING, phase="Initializing vector database...")
        
        from app.modules.embeddings.vector_stores.factory import get_vector_store, get_vector_store_type
        
        vector_store_type = get_vector_store_type()
        logger.info(f"Job {job_id}: Using vector store type: {vector_store_type}")
        
        vector_store = get_vector_store(vector_db_name)
        
        # Delete existing collection if not incremental
        if not incremental:
            try:
                await vector_store.delete_collection()
                logger.info(f"Deleted existing collection: {vector_db_name}")
            except Exception as e:
                logger.warning(f"Could not delete existing collection (may not exist): {e}")
        
        # Get storage path for config update
        from app.core.settings import get_settings
        settings = get_settings()
        vector_store_path = str(settings.data_dir / vector_store_type / vector_db_name)
        
        logger.info(f"Vector store ready: {vector_db_name} ({vector_store_type})")
        await _update_job_status(job_id, EmbeddingJobStatus.EMBEDDING, phase="Generating embeddings...")
        
        # Process documents in batches - optimized for throughput
        processed = 0
        total_vectors = 0
        start_time = time.time()
        failed_batches = 0
        
        # PERFORMANCE: Reduce DB overhead - check/update less frequently
        CANCEL_CHECK_INTERVAL = 20  # Check every 20 batches
        
        logger.info(f"Job {job_id}: Starting main embedding loop with {batch_count} batches, batch_size={batch_size}")
        
        for batch_idx in range(batch_count):
            batch_start_time = time.time()
            
            # Check for cancellation periodically (not every batch - expensive!)
            if batch_idx % CANCEL_CHECK_INTERVAL == 0:
                try:
                    async with _get_background_db_session() as session:
                        repo = EmbeddingJobRepository(session)
                        job = await repo.get_by_id(job_id)
                        if job and job.status == EmbeddingJobStatus.CANCELLED.value:
                            logger.info(f"Job {job_id} was cancelled")
                            return
                except Exception as e:
                    logger.warning(f"Failed to check cancellation status: {e}")
            
            # Get batch of documents
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, total_documents)
            batch_docs = documents[batch_start:batch_end]
            
            if len(batch_docs) == 0:
                logger.warning(f"Job {job_id}: Batch {batch_idx} has 0 documents! Skipping...")
                continue
            
            # Generate embeddings
            texts = [doc["content"] for doc in batch_docs]
            
            embed_start = time.time()
            try:
                # PERFORMANCE FIX: Call sync function directly (we're already in a background thread)
                # No need for run_in_executor overhead per batch!
                if asyncio.iscoroutinefunction(embed_fn):
                    # Async provider (OpenAI, Azure)
                    embeddings = await embed_fn(texts)
                else:
                    # Sync provider (HuggingFace) - call directly, no executor needed
                    embeddings = embed_fn(texts)
                embed_time = time.time() - embed_start
            except Exception as e:
                import traceback
                logger.error(f"Embedding generation failed for batch {batch_idx}: {e}")
                logger.error(traceback.format_exc())
                failed_batches += 1
                processed += len(batch_docs)
                continue
            
            # Store in Vector Store (Qdrant or ChromaDB)
            ids = [doc["id"] for doc in batch_docs]
            metadatas = [doc["metadata"] for doc in batch_docs]
            
            store_start = time.time()
            try:
                await vector_store.upsert_batch(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                total_vectors += len(embeddings)
                store_time = time.time() - store_start
            except Exception as e:
                logger.error(f"Vector store upsert failed for batch {batch_idx}: {e}")
                failed_batches += 1
                store_time = time.time() - store_start
            
            processed += len(batch_docs)
            batch_total_time = time.time() - batch_start_time
            
            # PERFORMANCE: Log less frequently (first 3 batches and every 25th)
            if batch_idx < 3 or batch_idx % 25 == 0:
                logger.info(f"Job {job_id}: Batch {batch_idx + 1} timing: embed={embed_time:.2f}s, store={store_time:.2f}s, total={batch_total_time:.2f}s for {len(batch_docs)} docs ({len(batch_docs)/batch_total_time:.1f} docs/sec). Job elapsed: {time.time() - job_start_time:.1f}s")
            
            # Calculate speed
            elapsed = time.time() - start_time
            docs_per_second = processed / elapsed if elapsed > 0 else 0
            
            # PERFORMANCE: Update progress less frequently (every 10 batches)
            if batch_idx % 10 == 0 or batch_idx == batch_count - 1:
                await _update_job_progress(
                    job_id=job_id,
                    processed=processed,
                    current_batch=batch_idx + 1,
                    total=total_documents,
                    phase=f"Batch {batch_idx + 1}/{batch_count} ({docs_per_second:.1f} docs/sec)",
                    elapsed_seconds=elapsed
                )
            
            if batch_idx % 25 == 0:
                logger.info(f"Job {job_id}: Progress: {batch_idx + 1}/{batch_count} batches | {processed}/{total_documents} docs | {docs_per_second:.1f} docs/sec")
        
        # Update status to VALIDATING
        await _update_job_status(job_id, EmbeddingJobStatus.VALIDATING, phase="Validating embeddings...")
        
        # Verify collection count
        final_count = await vector_store.get_collection_count()
        logger.info(f"Vector store collection {vector_db_name} has {final_count} vectors")
        
        # Update status to STORING
        await _update_job_status(job_id, EmbeddingJobStatus.STORING, phase="Finalizing vector database...")
        
        # Update config with vector DB info
        async with _get_background_db_session() as session:
            from sqlalchemy import update as sql_update
            stmt = sql_update(AgentConfigModel).where(
                AgentConfigModel.id == config_id
            ).values(
                vector_collection_name=vector_db_name,
                embedding_path=vector_store_path,
                embedding_status="completed"
            )
            await session.execute(stmt)
        
        # Update job with final vector count
        async with _get_background_db_session() as session:
            from sqlalchemy import update as sql_update
            from app.modules.embeddings.models import EmbeddingJobModel
            stmt = sql_update(EmbeddingJobModel).where(
                EmbeddingJobModel.job_id == job_id
            ).values(
                total_vectors=total_vectors
            )
            await session.execute(stmt)
        
        # Calculate final stats
        total_time = time.time() - start_time
        avg_speed = processed / total_time if total_time > 0 else 0
        
        # Mark as completed
        await _update_job_status(
            job_id, 
            EmbeddingJobStatus.COMPLETED, 
            phase=f"Completed: {processed} documents, {total_vectors} vectors ({avg_speed:.1f} docs/sec) - {vector_store_type}"
        )
        
        logger.info(f"Embedding job {job_id} completed: {processed} documents, {total_vectors} vectors in {total_time:.1f}s using {vector_store_type}")
        
    except Exception as e:
        logger.error(f"Embedding job {job_id} failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        try:
            await _update_job_status(
                job_id, 
                EmbeddingJobStatus.FAILED, 
                phase="Job failed",
                error_message=str(e)[:500]  # Truncate to avoid DB errors
            )
        except Exception as status_error:
            logger.error(f"Job {job_id}: Failed to update status after error: {status_error}")
