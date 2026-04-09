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
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from collections import OrderedDict
import hashlib
import multiprocessing
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

# =============================================================================
# Concurrent Batch Processing Configuration (ported from old backend)
# =============================================================================
# API providers (OpenAI, Azure) benefit from concurrent HTTP requests
# Local models (HuggingFace/SentenceTransformers) should process sequentially 
# to maximize GPU utilization and avoid memory contention
DEFAULT_API_CONCURRENT = 4  # Process up to 4 batches concurrently for API providers
DEFAULT_LOCAL_BATCH_SIZE = 256  # Larger batches for local GPU models (more efficient)

# =============================================================================
# MPS/CUDA BATCH SIZE OPTIMIZATION (ported from old backend)
# =============================================================================
# For local GPU providers, override small UI batch sizes for efficiency
# Small batches (e.g., 32) underutilize GPU parallelism - 128+ is optimal
MIN_GPU_BATCH_SIZE = 128  # Optimal minimum for MPS/CUDA with BGE-M3

# Local GPU providers that benefit from larger batch sizes
LOCAL_GPU_PROVIDERS = ("huggingface", "sentence-transformers", "bge-m3", "bge")

# Model name patterns for local models (handles misconfigured provider settings)
LOCAL_MODEL_PATTERNS = ("bge-", "bge_", "sentence-transformers", "all-minilm", "e5-", "gte-")


def _is_api_provider(model_name: str) -> bool:
    """Check if the embedding model is an API-based provider (supports concurrent requests)."""
    if not model_name:
        return False
    model_lower = model_name.lower()
    return model_lower.startswith('openai/') or model_lower.startswith('azure/')


def _is_local_gpu_model(model_name: str) -> bool:
    """
    Check if the embedding model is a local GPU model that benefits from larger batch sizes.
    
    Local models like BGE-M3, sentence-transformers, etc. run on MPS/CUDA and 
    achieve better throughput with batch sizes >= 128.
    """
    if not model_name:
        return False
    model_lower = model_name.lower()
    
    # Check provider prefix
    provider = model_lower.split('/')[0] if '/' in model_lower else ''
    if provider in LOCAL_GPU_PROVIDERS:
        return True
    
    # Check model name patterns
    return any(pattern in model_lower for pattern in LOCAL_MODEL_PATTERNS)


def _optimize_batch_size_for_gpu(batch_size: int, model_name: str) -> int:
    """
    Optimize batch size for local GPU models.
    
    Small UI batch sizes (e.g., 32) are suboptimal for GPU processing.
    This overrides them to MIN_GPU_BATCH_SIZE for ~2-3x speedup.
    
    Returns the original batch_size for API providers.
    """
    if _is_local_gpu_model(model_name) and batch_size < MIN_GPU_BATCH_SIZE:
        logger.info(
            f"MPS/CUDA OPTIMIZATION: UI batch_size={batch_size} is suboptimal for GPU. "
            f"Overriding to {MIN_GPU_BATCH_SIZE} for ~2.5x speedup."
        )
        return MIN_GPU_BATCH_SIZE
    return batch_size


# =============================================================================
# Query Embedding Cache (Performance Optimization)
# =============================================================================
# embed_query() is deterministic: same text → same embedding.
# Queries repeat frequently (follow-ups, retries, similar phrasing).
# 512 entries ≈ 2MB for 1024-dim embeddings.
_QUERY_EMBEDDING_CACHE: OrderedDict[str, List[float]] = OrderedDict()
_QUERY_CACHE_MAX = 512


def get_cached_query_embedding(text: str, embed_fn) -> List[float]:
    """
    Get query embedding with LRU caching.
    
    Caching avoids re-computing embeddings (~50-200ms per query).
    512 entries ≈ 2MB for 1024-dim vectors.
    """
    cache_key = text.strip()
    
    if cache_key in _QUERY_EMBEDDING_CACHE:
        _QUERY_EMBEDDING_CACHE.move_to_end(cache_key)
        return _QUERY_EMBEDDING_CACHE[cache_key]
    
    # Cache miss — compute embedding
    if asyncio.iscoroutinefunction(embed_fn):
        loop = asyncio.get_event_loop()
        embedding = loop.run_until_complete(embed_fn([text]))[0]
    else:
        embedding = embed_fn([text])[0]
    
    _QUERY_EMBEDDING_CACHE[cache_key] = embedding
    if len(_QUERY_EMBEDDING_CACHE) > _QUERY_CACHE_MAX:
        _QUERY_EMBEDDING_CACHE.popitem(last=False)
    
    return embedding


# =============================================================================
# Parallel Delta Worker for Incremental Updates
# =============================================================================

def _parallel_delta_worker(
    doc_batch: List[Dict[str, Any]], 
    existing_checksums: Dict[str, str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Worker function for parallel delta checking during incremental updates.
    
    Calculates checksums for documents and identifies which need re-embedding.
    Runs in separate process via ProcessPoolExecutor for CPU parallelism.
    """
    processed = []
    stale_ids = []
    
    for doc in doc_batch:
        content = doc.get("content", "")
        doc_id = doc.get("id", str(uuid.uuid4()))
        
        # Calculate checksum
        doc_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        # Add checksum to metadata
        if "metadata" not in doc:
            doc["metadata"] = {}
        doc["metadata"]["checksum"] = doc_hash
        doc["metadata"]["source_id"] = doc_id
        
        # Check if document exists and has changed
        if doc_id in existing_checksums:
            if existing_checksums[doc_id] != doc_hash:
                stale_ids.append(doc_id)
                processed.append(doc)
        else:
            processed.append(doc)
    
    return processed, stale_ids


async def _parallel_delta_check(
    documents: List[Dict[str, Any]],
    existing_checksums: Dict[str, str],
    delta_check_batch_size: int = 50000,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Perform parallel delta checking to identify new/modified documents.
    
    Uses ProcessPoolExecutor for CPU-bound checksum calculation.
    """
    if not existing_checksums:
        # No existing data - add checksums to all docs
        for doc in documents:
            content = doc.get("content", "")
            doc_id = doc.get("id", str(uuid.uuid4()))
            doc_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            if "metadata" not in doc:
                doc["metadata"] = {}
            doc["metadata"]["checksum"] = doc_hash
            doc["metadata"]["source_id"] = doc_id
        return documents, []
    
    num_workers = max(1, multiprocessing.cpu_count() // 2)
    doc_batches = [
        documents[i:i + delta_check_batch_size] 
        for i in range(0, len(documents), delta_check_batch_size)
    ]
    
    logger.info(f"Delta check: {len(documents)} docs, {len(doc_batches)} batches, {num_workers} workers")
    
    def run_delta_check_sync():
        local_processed = []
        local_stale = []
        
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(_parallel_delta_worker, batch, existing_checksums) 
                for batch in doc_batches
            ]
            
            for i, future in enumerate(as_completed(futures)):
                try:
                    batch_processed, batch_stale = future.result()
                    local_processed.extend(batch_processed)
                    local_stale.extend(batch_stale)
                except Exception as e:
                    logger.error(f"Delta check batch failed: {e}")
        
        return local_processed, local_stale
    
    loop = asyncio.get_event_loop()
    all_processed, all_stale = await loop.run_in_executor(None, run_delta_check_sync)
    
    logger.info(f"Delta check complete: {len(all_processed)} to process, {len(all_stale)} stale")
    return all_processed, all_stale


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
        # Use request override first, then chunking_config, then embedding_config
        batch_size = request.batch_size or chunking_config.get('batch_size') or emb_config.get('batch_size', 256)
        max_concurrent = request.max_concurrent or chunking_config.get('max_concurrent') or emb_config.get('max_concurrent', 5)
        
        # If request has chunking config, merge it
        if request.chunking:
            chunking_config = {
                'parent_chunk_size': request.chunking.parent_chunk_size,
                'parent_chunk_overlap': request.chunking.parent_chunk_overlap,
                'child_chunk_size': request.chunking.child_chunk_size,
                'child_chunk_overlap': request.chunking.child_chunk_overlap,
                'batch_size': batch_size,  # Include batch_size in chunking_config
                'max_concurrent': max_concurrent,
            }
        
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
        incremental: bool = False,
        batch_size: int = None,
        max_concurrent: int = None,
        chunking_override: dict = None
    ) -> None:
        """
        Start embedding job in background thread.
        
        Settings are read from job record (which includes request overrides) or agent_config table.
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
        
        # Use passed batch_size first (from create_job), then chunking_config, then embedding_config
        if batch_size is None:
            batch_size = chunking_config.get('batch_size') or emb_config.get('batch_size', 256)
        if max_concurrent is None:
            max_concurrent = chunking_config.get('max_concurrent') or emb_config.get('max_concurrent', 5)
        
        # Apply chunking override from request if provided
        if chunking_override:
            chunking_config.update(chunking_override)
            logger.info(f"Applied chunking override: {chunking_override}")
        
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
                batch_size=256,  # PERFORMANCE FIX: Large batch for GPU efficiency (was 128)
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
    batch_size: int = 50000,
    job_id: str = None,
) -> tuple[int, List[Dict[str, Any]]]:
    """
    Extract documents from DuckDB for embedding.
    
    Handles column name mismatches by normalizing names and mapping to actual table columns.
    For example, maps "live_improved_yes_no" to "Live Improved (Yes/No)".
    """
    import duckdb
    import re as regex_module
    
    if not os.path.exists(duckdb_path):
        raise ValueError(f"DuckDB file not found: {duckdb_path}")
    
    conn = duckdb.connect(duckdb_path, read_only=True)
    
    try:
        # Get total row count
        count_result = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
        total_count = count_result[0] if count_result else 0
        
        logger.info(f"Found {total_count} rows in table {table_name}")
        
        # Get actual column names from the table schema
        table_columns = [col[0] for col in conn.execute(f'DESCRIBE "{table_name}"').fetchall()]
        logger.info(f"Actual columns ({len(table_columns)}): {table_columns[:10]}...")
        logger.info(f"Requested columns ({len(columns)}): {columns[:10]}...")
        
        # Normalize column names for matching (handles "Live Improved (Yes/No)" vs "live_improved_yes_no")
        def normalize_col(name: str) -> str:
            n = name.lower().strip()
            n = regex_module.sub(r'[^a-z0-9]', '_', n)
            n = regex_module.sub(r'_+', '_', n).strip('_')
            return n
        
        # Build mapping: normalized -> actual column name
        col_map = {}
        for col in table_columns:
            col_map[normalize_col(col)] = col
            col_map[col] = col
            col_map[col.lower()] = col
        
        # Map requested columns to actual columns
        validated_columns = []  # Actual column names for SQL
        display_columns = []    # Display names for documents
        missing_columns = []
        
        for req in columns:
            if req in table_columns:
                validated_columns.append(req)
                display_columns.append(req)
            elif req.lower() in col_map:
                validated_columns.append(col_map[req.lower()])
                display_columns.append(req)
            elif normalize_col(req) in col_map:
                validated_columns.append(col_map[normalize_col(req)])
                display_columns.append(req)
            else:
                missing_columns.append(req)
        
        if missing_columns:
            logger.warning(f"Columns not found (skipped): {missing_columns[:10]}{'...' if len(missing_columns) > 10 else ''}")
        
        if not validated_columns:
            raise ValueError(f"None of the requested columns exist in table '{table_name}'")
        
        logger.info(f"Validated {len(validated_columns)}/{len(columns)} columns for extraction")
        
        # Build column list for query using VALIDATED column names
        safe_columns = [f'"{c}"' for c in validated_columns]
        columns_sql = ", ".join(safe_columns)
        
        # Find ID column
        id_columns = ['id', 'ID', 'row_id', 'index', 'reviewid', 'record_id', 'patient_id', 'res_id', 'encounter_id']
        id_column = None
        for ic in id_columns:
            if ic in table_columns:
                id_column = ic
                break
        
        logger.info(f"Using ID column: {id_column or 'ROW_NUMBER()'}")
        
        # Build query
        if id_column:
            query = f'SELECT "{id_column}", {columns_sql} FROM "{table_name}"'
        else:
            query = f'SELECT ROW_NUMBER() OVER () as _row_num, {columns_sql} FROM "{table_name}"'
        
        logger.info("Starting FAST streaming extraction (no OFFSET pagination)")
        extraction_start = time.time()
        
        result = conn.execute(query)
        
        documents = []
        rows_processed = 0
        last_progress_update = 0
        
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            
            for row in rows:
                row_id = str(row[0])
                text_parts = []
                metadata = {"table": table_name, "row_id": row_id}
                
                for i, col in enumerate(display_columns):
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
            
            if rows_processed - last_progress_update >= 100000 or rows_processed >= total_count:
                last_progress_update = rows_processed
                elapsed = time.time() - extraction_start
                rate = rows_processed / elapsed if elapsed > 0 else 0
                progress_pct = rows_processed * 100 / total_count if total_count > 0 else 0
                logger.info(f"Extraction progress: {rows_processed}/{total_count} rows ({progress_pct:.1f}%), {len(documents)} docs, {rate:.0f} rows/sec")
                
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
    Background task to run embedding generation with parent-child chunking.
    
    Pipeline:
    1. Extract raw data from DuckDB/PostgreSQL
    2. Transform to LangChain Documents with medical context enrichment
    3. Apply Parent-Child (Small-to-Big) chunking via AdvancedDataTransformer
    4. Generate embeddings for child chunks
    5. Store in vector DB with parent document linking
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
    
    batch_size = job_config.get("batch_size") or 256
    incremental = job_config.get("incremental", False)
    batch_size = _optimize_batch_size_for_gpu(batch_size, embedding_model)
    data_source_id = job_config.get("data_source_id")
    
    logger.info(f"Starting embedding job {job_id} for config {config_id}")
    
    # Parse chunking configuration
    parent_chunk_size = chunking_config.get('parent_chunk_size') or chunking_config.get('parentChunkSize', 512)
    parent_chunk_overlap = chunking_config.get('parent_chunk_overlap') or chunking_config.get('parentChunkOverlap', 100)
    child_chunk_size = chunking_config.get('child_chunk_size') or chunking_config.get('childChunkSize', 128)
    child_chunk_overlap = chunking_config.get('child_chunk_overlap') or chunking_config.get('childChunkOverlap', 25)
    use_parent_child_chunking = chunking_config.get('use_parent_child_chunking', True)
    
    logger.info(f"Job {job_id} config: model={embedding_model}, batch_size={batch_size}, incremental={incremental}")
    logger.info(f"Job {job_id} chunking: parent={parent_chunk_size}/{parent_chunk_overlap}, child={child_chunk_size}/{child_chunk_overlap}, enabled={use_parent_child_chunking}")
    
    job_start_time = time.time()
    
    try:
        await _update_job_status(job_id, EmbeddingJobStatus.PREPARING, phase="Loading configuration...")
        
        selected_columns = selected_columns_raw
        if isinstance(selected_columns, str):
            try:
                selected_columns = json.loads(selected_columns)
            except json.JSONDecodeError:
                selected_columns = {}
        
        from app.modules.agents.models import AgentConfigModel
        from app.modules.data_sources.models import DataSourceModel
        
        source_type = None
        duckdb_path = None
        duckdb_table_name = None
        db_url = None
        agent_id = "unknown"
        
        async with _get_background_db_session() as session:
            stmt = select(AgentConfigModel).where(AgentConfigModel.id == config_id)
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            
            if not config:
                await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="Configuration not found")
                return
            
            agent_id = str(config.agent_id) if config.agent_id else "unknown"
            data_source_id = config.data_source_id
            
            if data_source_id:
                ds_stmt = select(DataSourceModel).where(DataSourceModel.id == data_source_id)
                ds_result = await session.execute(ds_stmt)
                data_source = ds_result.scalar_one_or_none()
                
                if data_source:
                    source_type = data_source.source_type
                    duckdb_path = data_source.duckdb_file_path
                    duckdb_table_name = data_source.duckdb_table_name
                    db_url = data_source.db_url
        
        # Validate data source
        if source_type == 'file' and (not duckdb_path or not duckdb_table_name):
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="File data source not configured.")
            return
        elif source_type == 'database' and not db_url:
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="Database URL not configured.")
            return
        elif source_type not in ('file', 'database'):
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message=f"Unknown source type: {source_type}")
            return
        
        vector_db_name = f"agent_{agent_id}_config_{config_id}"
        
        # =================================================================
        # PHASE 1: Extract raw data
        # =================================================================
        await _update_job_status(job_id, EmbeddingJobStatus.PREPARING, phase="Extracting documents...")
        
        try:
            if source_type == 'database':
                if not selected_columns:
                    await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="No columns selected.")
                    return
                total_count, raw_documents = await _extract_documents_from_postgres(db_url=db_url, selected_columns=selected_columns, batch_size=1000)
            else:
                columns_to_embed = []
                if selected_columns and isinstance(selected_columns, dict):
                    columns_to_embed = selected_columns.get(duckdb_table_name, [])
                    if not columns_to_embed:
                        for cols in selected_columns.values():
                            columns_to_embed = cols
                            break
                
                if not columns_to_embed:
                    await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="No columns selected.")
                    return
                
                total_count, raw_documents = await _extract_documents_from_duckdb(
                    duckdb_path=duckdb_path, table_name=duckdb_table_name,
                    columns=columns_to_embed, batch_size=1000, job_id=job_id
                )
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message=f"Extraction failed: {str(e)[:400]}")
            return
        
        if not raw_documents:
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message="No documents found.")
            return
        
        logger.info(f"Job {job_id}: Extracted {len(raw_documents)} raw documents in {time.time() - job_start_time:.1f}s")
        
        # =================================================================
        # PHASE 2: Parent-Child Chunking (if enabled)
        # =================================================================
        if use_parent_child_chunking:
            await _update_job_status(job_id, EmbeddingJobStatus.PREPARING, phase="Applying parent-child chunking...")
            
            try:
                from langchain_core.documents import Document as LCDocument
                from app.modules.embeddings.transform import AdvancedDataTransformer
                from app.core.config import get_settings
                
                settings = get_settings()
                
                transformer_config = {
                    'chunking': {
                        'parent_splitter': {'chunk_size': parent_chunk_size, 'chunk_overlap': parent_chunk_overlap},
                        'child_splitter': {'chunk_size': child_chunk_size, 'chunk_overlap': child_chunk_overlap}
                    },
                    'medical_context': data_dictionary if isinstance(data_dictionary, dict) else {},
                }
                
                docstore_dir = settings.data_dir / "docstores" / vector_db_name
                docstore_dir.mkdir(parents=True, exist_ok=True)
                docstore_path = str(docstore_dir / "parent_docs.db")
                
                transformer = AdvancedDataTransformer(config=transformer_config, docstore_path=docstore_path)
                
                lc_documents = [
                    LCDocument(
                        page_content=doc["content"],
                        metadata={"source_table": doc["metadata"].get("table", "unknown"), "source_id": doc["id"], **{k: v for k, v in doc["metadata"].items() if k != "table"}}
                    )
                    for doc in raw_documents
                ]
                
                logger.info(f"Job {job_id}: Running parent-child chunking on {len(lc_documents)} documents...")
                
                loop = asyncio.get_event_loop()
                def run_chunking():
                    return transformer.perform_parent_child_chunking(documents=lc_documents)
                
                chunking_start = time.time()
                child_documents, parent_docstore = await loop.run_in_executor(None, run_chunking)
                
                logger.info(f"Job {job_id}: Chunking complete in {time.time() - chunking_start:.1f}s: {len(lc_documents)} parents -> {len(child_documents)} children")
                
                documents = [
                    {
                        "id": hashlib.sha256(f"{child.page_content}{child.metadata.get('doc_id', '')}".encode()).hexdigest()[:16],
                        "content": child.page_content,
                        "metadata": child.metadata
                    }
                    for child in child_documents
                ]
                total_documents = len(documents)
                
            except Exception as e:
                logger.error(f"Job {job_id}: Chunking failed: {e}, falling back to raw documents")
                import traceback
                logger.error(traceback.format_exc())
                documents = raw_documents
                total_documents = len(documents)
        else:
            documents = raw_documents
            total_documents = len(documents)
        
        batch_count = (total_documents + batch_size - 1) // batch_size
        logger.info(f"Job {job_id}: {total_documents} documents ready for embedding ({batch_count} batches)")
        
        async with _get_background_db_session() as session:
            from sqlalchemy import update as sql_update
            from app.modules.embeddings.models import EmbeddingJobModel
            stmt = sql_update(EmbeddingJobModel).where(EmbeddingJobModel.job_id == job_id).values(total_documents=total_documents, total_batches=batch_count)
            await session.execute(stmt)
        
        # =================================================================
        # PHASE 3: Load Embedding Model
        # =================================================================
        await _update_job_status(job_id, EmbeddingJobStatus.EMBEDDING, phase="Loading embedding model...")
        
        try:
            embed_fn = await _get_embedding_provider(embedding_model, api_key, api_base_url)
            logger.info(f"Job {job_id}: Embedding model loaded")
        except Exception as e:
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, error_message=f"Model load failed: {str(e)[:400]}")
            return
        
        # =================================================================
        # PHASE 4: Initialize Vector Store
        # =================================================================
        await _update_job_status(job_id, EmbeddingJobStatus.EMBEDDING, phase="Initializing vector store...")
        
        from app.modules.embeddings.vector_stores.factory import get_vector_store, get_vector_store_type
        from app.core.settings import get_settings
        
        vector_store_type = get_vector_store_type()
        vector_store = get_vector_store(vector_db_name)
        
        if not incremental:
            try:
                await vector_store.delete_collection()
            except:
                pass
        
        settings = get_settings()
        vector_store_path = str(settings.data_dir / vector_store_type / vector_db_name)
        
        await _update_job_status(job_id, EmbeddingJobStatus.EMBEDDING, phase="Generating embeddings...")
        
        # =================================================================
        # PHASE 5: Embed and Store
        # =================================================================
        processed = 0
        total_vectors = 0
        start_time = time.time()
        failed_batches = 0
        CANCEL_CHECK_INTERVAL = 20
        
        use_concurrent = _is_api_provider(embedding_model) and asyncio.iscoroutinefunction(embed_fn)
        max_concurrent = job_config.get("max_concurrent") or DEFAULT_API_CONCURRENT
        
        logger.info(f"Job {job_id}: Starting embedding: {batch_count} batches, concurrent={use_concurrent}")
        
        if use_concurrent:
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def process_batch(batch_idx):
                async with semaphore:
                    batch_start = batch_idx * batch_size
                    batch_docs = documents[batch_start:batch_start + batch_size]
                    if not batch_docs:
                        return {"processed": 0, "vectors": 0, "failed": False}
                    try:
                        texts = [d["content"] for d in batch_docs]
                        embeddings = await embed_fn(texts)
                        await vector_store.upsert_batch(ids=[d["id"] for d in batch_docs], documents=texts, embeddings=embeddings, metadatas=[d["metadata"] for d in batch_docs])
                        return {"processed": len(batch_docs), "vectors": len(embeddings), "failed": False}
                    except Exception as e:
                        logger.error(f"Batch {batch_idx} failed: {e}")
                        return {"processed": len(batch_docs), "vectors": 0, "failed": True}
            
            tasks = [process_batch(i) for i in range(batch_count)]
            completed = 0
            for coro in asyncio.as_completed(tasks):
                result = await coro
                completed += 1
                processed += result["processed"]
                total_vectors += result["vectors"]
                if result["failed"]:
                    failed_batches += 1
                if completed % 10 == 0 or completed == batch_count:
                    elapsed = time.time() - start_time
                    await _update_job_progress(job_id, processed, completed, total_documents, f"Batch {completed}/{batch_count} ({processed/elapsed:.1f} docs/sec)", elapsed)
        else:
            for batch_idx in range(batch_count):
                if batch_idx % CANCEL_CHECK_INTERVAL == 0:
                    try:
                        async with _get_background_db_session() as session:
                            repo = EmbeddingJobRepository(session)
                            job = await repo.get_by_id(job_id)
                            if job and job.status == EmbeddingJobStatus.CANCELLED.value:
                                return
                    except:
                        pass
                
                batch_start = batch_idx * batch_size
                batch_docs = documents[batch_start:batch_start + batch_size]
                if not batch_docs:
                    continue
                
                texts = [d["content"] for d in batch_docs]
                try:
                    if asyncio.iscoroutinefunction(embed_fn):
                        embeddings = await embed_fn(texts)
                    else:
                        embeddings = embed_fn(texts)
                except Exception as e:
                    logger.error(f"Embed failed batch {batch_idx}: {e}")
                    failed_batches += 1
                    processed += len(batch_docs)
                    continue
                
                try:
                    await vector_store.upsert_batch(ids=[d["id"] for d in batch_docs], documents=texts, embeddings=embeddings, metadatas=[d["metadata"] for d in batch_docs])
                    total_vectors += len(embeddings)
                except Exception as e:
                    logger.error(f"Store failed batch {batch_idx}: {e}")
                    failed_batches += 1
                
                processed += len(batch_docs)
                
                if batch_idx % 10 == 0 or batch_idx == batch_count - 1:
                    elapsed = time.time() - start_time
                    await _update_job_progress(job_id, processed, batch_idx + 1, total_documents, f"Batch {batch_idx + 1}/{batch_count} ({processed/elapsed:.1f} docs/sec)", elapsed)
                
                if batch_idx < 3 or batch_idx % 25 == 0:
                    logger.info(f"Job {job_id}: Batch {batch_idx + 1}/{batch_count}, {processed}/{total_documents} docs")
        
        # =================================================================
        # PHASE 6: Finalize
        # =================================================================
        await _update_job_status(job_id, EmbeddingJobStatus.VALIDATING, phase="Validating...")
        
        final_count = await vector_store.get_collection_count()
        logger.info(f"Job {job_id}: Vector store has {final_count} vectors")
        
        await _update_job_status(job_id, EmbeddingJobStatus.STORING, phase="Finalizing...")
        
        async with _get_background_db_session() as session:
            from sqlalchemy import update as sql_update
            stmt = sql_update(AgentConfigModel).where(AgentConfigModel.id == config_id).values(
                vector_collection_name=vector_db_name, embedding_path=vector_store_path, embedding_status="completed"
            )
            await session.execute(stmt)
        
        async with _get_background_db_session() as session:
            from sqlalchemy import update as sql_update
            from app.modules.embeddings.models import EmbeddingJobModel
            stmt = sql_update(EmbeddingJobModel).where(EmbeddingJobModel.job_id == job_id).values(total_vectors=total_vectors)
            await session.execute(stmt)
        
        total_time = time.time() - start_time
        chunking_info = "with parent-child chunking" if use_parent_child_chunking else "no chunking"
        
        await _update_job_status(job_id, EmbeddingJobStatus.COMPLETED, 
            phase=f"Completed: {processed} docs, {total_vectors} vectors ({processed/total_time:.1f} docs/sec) - {chunking_info}")
        
        logger.info(f"Job {job_id} completed: {processed} docs, {total_vectors} vectors in {total_time:.1f}s ({chunking_info})")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await _update_job_status(job_id, EmbeddingJobStatus.FAILED, phase="Failed", error_message=str(e)[:500])
        except:
            pass

