import os
import asyncio
import hashlib
from celery import Celery
from typing import List, Dict, Any, Union

from backend.core.logging import get_logger
from backend.pipeline.file_rag_pipeline import ChunkedDocument

# For the Celery Beat Dispatcher
from datetime import datetime, timezone
import asyncio

logger = get_logger(__name__)

# =============================================================================
# CRITICAL: Force CPU for Celery workers on macOS
# Apple's MPS (Metal Performance Shaders) doesn't work with forked processes
# which causes SIGABRT crashes. We must use CPU in worker subprocesses.
# =============================================================================
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Disable CUDA as well for consistency

# Initialize Celery app with RabbitMQ broker and Redis results backend
# RabbitMQ for message queuing (reliable delivery, persistence)
# Redis for results storage (fast reads for task status)
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    'embedding_worker',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # Worker optimization
    worker_prefetch_multiplier=1,  # Since batches are large, prefetch 1 at a time
    task_acks_late=True,  # Ack after task is fully completed to prevent data loss
    # Task result settings
    result_expires=3600,  # Results expire after 1 hour
    task_track_started=True,  # Track when tasks start
    # RabbitMQ specific settings
    task_default_queue='embedding_tasks',
    task_queues={
        'embedding_tasks': {
            'exchange': 'embedding_tasks',
            'routing_key': 'embedding_tasks',
        },
    },
    # Retry settings
    task_default_retry_delay=30,  # 30 seconds between retries
    task_reject_on_worker_lost=True,  # Requeue tasks if worker dies
    # Celery Beat Configuration
    beat_schedule={
        'dispatch-vector-db-syncs-every-minute': {
            'task': 'backend.pipeline.workers.embedding_worker.dispatch_vector_db_syncs',
            'schedule': 60.0,  # Run every 60 seconds
        },
    }
)

# Global embedding provider instance (lazy loaded)
_embedding_provider = None

def get_embedding_provider():
    global _embedding_provider
    if _embedding_provider is None:
        logger.info("Initializing BGE-M3 embedding provider in worker process...")
        from backend.services.embedding_providers import BGEProvider
        # Path should be relative to where worker is executed or absolute
        models_path = os.getenv("MODELS_PATH", "./models")
        _embedding_provider = BGEProvider(
            model_path=f"{models_path}/bge-m3"
        )
    return _embedding_provider

@celery_app.task(bind=True, max_retries=3)
def process_embedding_batch(self, batch_run_id: str, table_name: str, serialized_chunks: List[Union[Dict[str, Any], str]]):
    """
    Celery task to embed a batch of chunks and store them in the vector database.
    
    Args:
        batch_run_id: Unique identifier for the whole ingestion job
        table_name: The table we are processing
        serialized_chunks: List of either:
            - Serialized ChunkedDocument dictionaries (from file_rag_pipeline.py)
            - Raw document strings (from embedding_progress.py)
    """
    logger.info(f"Worker received batch of {len(serialized_chunks)} chunks for {table_name}")
    
    try:
        # Detect input format: dictionaries vs raw strings
        if serialized_chunks and isinstance(serialized_chunks[0], dict):
            # Format 1: Serialized ChunkedDocument dictionaries
            logger.debug("Processing serialized ChunkedDocument dictionaries")
            chunks = [
                ChunkedDocument(
                    chunk_id=c['chunk_id'],
                    content=c['content'],
                    parent_id=c['parent_id'],
                    metadata=c['metadata'],
                    is_parent=c['is_parent']
                )
                for c in serialized_chunks
            ]
            texts = [c.content for c in chunks]
            ids = [c.chunk_id for c in chunks]
            metadatas = [c.metadata for c in chunks]
        else:
            # Format 2: Raw document strings (from embedding_progress.py)
            logger.debug("Processing raw document strings")
            texts = serialized_chunks  # Already a list of strings
            # Generate chunk IDs from content hash
            ids = [hashlib.sha256(f"{text}{table_name}".encode()).hexdigest() for text in texts]
            metadatas = [{"source": table_name, "batch_run_id": batch_run_id} for _ in texts]
        
        # 3. Get provider and generate embeddings synchronously within the worker
        provider = get_embedding_provider()
        
        # Run the async embedding in the event loop wrapper
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        embeddings = loop.run_until_complete(provider.aembed_documents(texts))
        
        # 4. Prepare data for vector store insertion
        from backend.pipeline.vector_stores.factory import VectorStoreFactory
        from backend.services.settings_service import get_settings_service, SettingCategory
        
        # Initialize Vector Store Factory
        settings_service = get_settings_service()
        vs_settings = settings_service.get_category_settings_raw(SettingCategory.VECTOR_STORE)
        provider_type = vs_settings.get("type", "qdrant")

        # Use table_name directly as collection name (not prefixed with file_rag_)
        # This ensures consistency with embedding_progress.py
        collection_name = table_name if not table_name.startswith("file_rag_") else table_name
        
        vector_store = VectorStoreFactory.get_provider(
            provider_type, 
            collection_name=collection_name
        )
        
        # 5. Insert to vector database
        loop.run_until_complete(
            vector_store.upsert_batch(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas
            )
        )
        
        logger.info(f"Successfully embedded and stored batch of {len(ids)} chunks.")
        
        # Return summary
        return {
            "status": "success",
            "processed_chunks": len(ids),
            "table_name": table_name
        }
        
    except Exception as exc:
        logger.error(f"Error processing embedding batch: {exc}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


# =============================================================================
# Background Scheduling (Celery Beat Dispatcher & Sync task)
# =============================================================================

@celery_app.task(bind=True)
def dispatch_vector_db_syncs(self):
    """
    Runs every minute via Celery Beat.
    Checks sqlite database for any schedules where `next_run_at <= NOW()`.
    Pushes those jobs into `execute_vector_db_sync` and calculates their next runtime.
    """
    logger.info("Celery Beat Tick: Dispatching Vector DB Syncs...")
    from backend.services.schedule_manager import get_schedule_manager
    from backend.sqliteDb.db import get_db_service
    
    manager = get_schedule_manager()
    db = get_db_service()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute('''
            SELECT vector_db_name, schedule_cron
            FROM vector_db_schedules
            WHERE enabled = 1 AND next_run_at <= ?
        ''', (now_iso,))
        
        due_jobs = cursor.fetchall()
        
        for row in due_jobs:
            db_name = row['vector_db_name']
            cron_str = row['schedule_cron']
            
            logger.info(f"Targeting '{db_name}' sync for background execution.")
            
            # 1. Update status to QUEUED
            manager.update_run_status(db_name, status=manager.ScheduleStatus.QUEUED)
            
            # 2. Push to queue
            celery_app.send_task(
                'backend.pipeline.workers.embedding_worker.execute_vector_db_sync',
                args=[db_name, False],
                queue='embedding_tasks'
            )
            
            # 3. Calculate next run and update it
            # We fetch from DB again via manager, or just compute directly
            # For simplicity let's read the latest schedule from manager DB state and compute
            schedule_info = manager.get_schedule(db_name)
            if schedule_info:
                # Get standard cron
                computed_cron = manager._get_cron_string(
                    manager.ScheduleType(schedule_info['schedule_type']),
                    schedule_info['schedule_hour'],
                    schedule_info['schedule_minute'],
                    schedule_info['schedule_day_of_week'],
                    schedule_info.get('schedule_cron')
                )
                
                next_run = manager.calculate_next_run(computed_cron)
                if next_run:
                    manager.update_next_run_time(db_name, next_run)
                    logger.info(f"Updated next_run_at for '{db_name}' to {next_run.isoformat()}")

    except Exception as e:
        logger.error(f"Error dispatching syncs: {e}")
    finally:
        conn.close()


@celery_app.task(bind=True, max_retries=1)
def execute_vector_db_sync(self, vector_db_name: str, is_manual: bool = False):
    """
    The actual syncing task, executing the embedding progress ingestion.
    Replaces `SchedulerService._execute_sync_job`.
    """
    job_source = "manual" if is_manual else "scheduled"
    logger.info(f"Executing {job_source} sync for vector DB: {vector_db_name}")
    
    from backend.services.schedule_manager import get_schedule_manager
    manager = get_schedule_manager()
    db = manager.db
    
    manager.update_run_status(vector_db_name, manager.ScheduleStatus.RUNNING)
    
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT sp.id as prompt_id, pc.embedding_config 
            FROM system_prompts sp
            JOIN prompt_configs pc ON sp.id = pc.prompt_id
            WHERE sp.is_active = 1
            ORDER BY sp.id DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        config_id = None
        for row in rows:
            try:
                import json
                emb_conf = json.loads(row['embedding_config'] or '{}')
                if emb_conf.get('vectorDbName') == vector_db_name:
                    config_id = row['prompt_id']
                    break
            except Exception:
                continue
        
        if not config_id:
            raise ValueError(f"No active configuration found for vector DB: {vector_db_name}")
            
        from backend.services.embedding_job_service import get_embedding_job_service
        from backend.models.schemas import User
        
        job_service = get_embedding_job_service()
        
        # System user
        system_user = User(
            id=0,
            username="scheduler",
            email="scheduler@system",
            role="super_admin",
            is_active=True
        )
        
        job_id = job_service.create_job(
            config_id=config_id,
            total_documents=100,
            user=system_user,
            batch_size=50,
            max_concurrent=5
        )
        
        from backend.api.routes.embedding_progress import _run_embedding_job
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        loop.run_until_complete(
            _run_embedding_job(
                job_id=job_id,
                config_id=config_id,
                user_id=0,
                incremental=True
            )
        )
        
        manager.update_run_status(vector_db_name, manager.ScheduleStatus.SUCCESS, job_id=job_id)
        logger.info(f"{job_source.capitalize()} sync completed for {vector_db_name}, job_id={job_id}")
        
        # INVALIDATE SQL CACHE ON SUCCESSFUL SYNC
        try:
            from backend.services.sql_service import invalidate_sql_cache
            invalidate_sql_cache()
            logger.info("Invalidated SQL query cache following database sync.")
        except Exception as e:
            logger.warning(f"Failed to invalidate SQL cache after sync: {e}")
            
        
    except Exception as e:
        logger.error(f"Scheduled sync failed for {vector_db_name}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        manager.update_run_status(vector_db_name, manager.ScheduleStatus.FAILED)


if __name__ == '__main__':
    celery_app.start()
