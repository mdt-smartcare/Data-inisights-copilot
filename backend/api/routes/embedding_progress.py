"""
API routes for embedding job management and progress tracking.
Requires SuperAdmin role for all operations.

Refactored for Production:
- SQLite-backed docstore to prevent OOM on large datasets
- UI batch config passthrough (previously ignored)
- Circuit breaker pattern for ChromaDB writes
- All configs now flow from UI inputs
- CHECKPOINT SUPPORT: Resume from any phase after interruption
- NON-BLOCKING: Jobs run in separate threads to not block API
"""
from typing import List, Optional, Dict, Tuple
from langchain_core.documents import Document
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
import json
import hashlib
import uuid
import os
import multiprocessing
import time
import threading
import asyncio
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor

from backend.models.schemas import User
from backend.models.rag_models import (
    EmbeddingJobCreate, EmbeddingJobProgress, EmbeddingJobSummary,
    EmbeddingJobStatus, RAGAuditAction, ChunkingConfig, ParallelizationConfig,
    MedicalContextConfig
)
from backend.database.db import get_db_service
from backend.services.embedding_job_service import get_embedding_job_service, EmbeddingJobService, JobCancelledError
from backend.services.authorization_service import get_authorization_service, AuthorizationService
from backend.services.notification_service import get_notification_service
from backend.services.embedding_batch_processor import EmbeddingBatchProcessor, BatchConfig
from backend.services.embedding_checkpoint_service import CheckpointPhase, get_checkpoint_service
from backend.pipeline.transform import AdvancedDataTransformer
from backend.core.permissions import require_admin, get_current_user
from backend.core.logging import get_embedding_logger
from backend.services.embedding_registry import get_embedding_processor_registry

logger = get_embedding_logger()

router = APIRouter(prefix="/embedding-jobs", tags=["Embedding Jobs"])

# Thread pool for running embedding jobs without blocking the event loop
_embedding_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedding_job_")


def _run_embedding_job_sync_wrapper(
    job_id: str,
    config_id: int,
    user_id: int,
    incremental: bool,
    ui_batch_size: Optional[int],
    ui_max_concurrent: Optional[int],
    ui_chunking: Optional[ChunkingConfig],
    ui_parallelization: Optional[ParallelizationConfig],
    ui_medical_context: Optional[MedicalContextConfig],
    ui_max_consecutive_failures: int,
    ui_retry_attempts: int
):
    """
    Synchronous wrapper that creates a new event loop for the async embedding job.
    This runs in a separate thread to avoid blocking the main FastAPI event loop.
    """
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_run_embedding_job(
                job_id=job_id,
                config_id=config_id,
                user_id=user_id,
                incremental=incremental,
                ui_batch_size=ui_batch_size,
                ui_max_concurrent=ui_max_concurrent,
                ui_chunking=ui_chunking,
                ui_parallelization=ui_parallelization,
                ui_medical_context=ui_medical_context,
                ui_max_consecutive_failures=ui_max_consecutive_failures,
                ui_retry_attempts=ui_retry_attempts
            ))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Embedding job {job_id} thread failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


@router.post("", response_model=dict, dependencies=[Depends(require_admin)])
async def start_embedding_job(
    request: EmbeddingJobCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service),
    auth_service: AuthorizationService = Depends(get_authorization_service)
):
    """
    Start a new embedding generation job.
    
    This kicks off async embedding generation and returns immediately
    with a job ID that can be used to track progress.
    
    Requires Admin role or above.
    """
    try:
        from backend.database.db import get_db_service
        db_service = get_db_service()
        config = db_service.get_config_by_id(request.config_id)
        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration {request.config_id} not found")
            
        from backend.core.vector_db_utils import derive_vector_db_name
        emb_conf = json.loads(config.get('embedding_config', '{}') or '{}')
        vector_db_name = emb_conf.get('vectorDbName')
        
        # Robust naming fallback for multi-tenant isolation
        if not vector_db_name:
            source_btn = config.get('ingestion_file_name', '').split('.')[0] if config.get('data_source_type') == 'file' else None
            vector_db_name = derive_vector_db_name(
                agent_id=config.get('agent_id'),
                connection_id=config.get('connection_id'),
                source_name=source_btn
            )
            logger.info(f"Derived missing vectorDbName as: {vector_db_name}")
            
        model_name = emb_conf.get('model')
        if not model_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Embedding model is missing in configuration")
            
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
                "batch_size": request.batch_size,
                "chunking": request.chunking.model_dump() if request.chunking else None,
                "parallelization": request.parallelization.model_dump() if request.parallelization else None
            }
        )
        
        # Submit job to thread pool executor (non-blocking)
        # This ensures the job runs in a completely separate thread with its own event loop
        _embedding_executor.submit(
            _run_embedding_job_sync_wrapper,
            job_id=job_id,
            config_id=request.config_id,
            user_id=current_user.id,
            incremental=request.incremental,
            ui_batch_size=request.batch_size,
            ui_max_concurrent=request.max_concurrent,
            ui_chunking=request.chunking,
            ui_parallelization=request.parallelization,
            ui_medical_context=request.medical_context_config,
            ui_max_consecutive_failures=request.max_consecutive_failures,
            ui_retry_attempts=request.retry_attempts
        )
        
        logger.info(f"Started embedding job {job_id} for config {request.config_id} (incremental={request.incremental})")
        
        return {
            "status": "started",
            "job_id": job_id,
            "message": "Embedding generation started in background"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start embedding job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start embedding job: {str(e)}"
        )


async def _run_embedding_job(
    job_id: str, 
    config_id: int, 
    user_id: int, 
    incremental: bool = True,
    ui_batch_size: Optional[int] = None,
    ui_max_concurrent: Optional[int] = None,
    ui_chunking: Optional[ChunkingConfig] = None,
    ui_parallelization: Optional[ParallelizationConfig] = None,
    ui_medical_context: Optional[MedicalContextConfig] = None,
    ui_max_consecutive_failures: int = 5,
    ui_retry_attempts: int = 3
):
    """
    Background task to run embedding generation with checkpoint support.
    
    CHECKPOINT PHASES:
    1. EXTRACTION - Table data extracted from database (saved to pickle)
    2. DOCUMENTS - Documents created from table data (saved to SQLite)
    3. CHUNKING - Child chunks created (saved to SQLite)
    4. EMBEDDING - Embeddings generated (checkpointed by ChromaDB)
    
    On restart, the job will resume from the last completed checkpoint.
    """
    job_service = get_embedding_job_service()
    notification_service = get_notification_service()
    db_service = get_db_service()
    
    # Initialize checkpoint service early
    checkpoint_service = None
    
    try:
        start_time = time.time()
        config = db_service.get_config_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration {config_id} not found")

        from backend.core.vector_db_utils import validate_vector_db_name, derive_vector_db_name
        emb_conf = json.loads(config.get('embedding_config', '{}') or '{}')
        
        v_db_name = emb_conf.get('vectorDbName')
        if not v_db_name:
             source_btn = config.get('ingestion_file_name', '').split('.')[0] if config.get('data_source_type') == 'file' else None
             v_db_name = derive_vector_db_name(
                agent_id=config.get('agent_id'),
                connection_id=config.get('connection_id'),
                source_name=source_btn
             )
        
        is_valid, err_msg = validate_vector_db_name(v_db_name)
        if not is_valid:
            raise ValueError(f"Invalid Vector DB Namespace '{v_db_name}': {err_msg}")

        model_name = emb_conf.get('model')
        if not model_name:
            raise ValueError("No embedding model specified in configuration")

        agent_id = config.get('agent_id')
        job_service.start_job(job_id)
        
        # Setup paths
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../data/indexes/{v_db_name}"))
        os.makedirs(chroma_path, exist_ok=True)
        docstore_path = os.path.join(chroma_path, "parent_docstore.db")
        
        # =================================================================
        # INITIALIZE CHECKPOINT SERVICE
        # =================================================================
        base_indexes_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/indexes"))
        checkpoint_service = get_checkpoint_service(base_indexes_path, v_db_name)
        
        # Check if we can resume from a previous checkpoint
        can_resume, resume_phase, resume_msg = checkpoint_service.can_resume(config_id)
        
        if not incremental:
            # Full rebuild - clear all checkpoints
            checkpoint_service.clear_checkpoints()
            logger.info(f"Full rebuild requested - cleared all checkpoints for {v_db_name}")
            resume_phase = None
        elif can_resume:
            logger.info(f"CHECKPOINT RESUME: {resume_msg}")
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, 
                                        phase=f"Resuming from {resume_phase.value} phase...")
        
        job_progress = job_service.get_job_progress(job_id)
        if not job_progress:
            logger.error(f"Job {job_id} not found in database, cannot proceed")
            return
        if job_progress.status == EmbeddingJobStatus.CANCELLED:
            logger.info(f"Job {job_id} cancelled before starting.")
            return
        
        await notification_service.create_notification(
            user_id=user_id,
            notification_type="embedding_started",
            title="Embedding Generation Started",
            message=f"Sync process started for job {job_id}." + (f" Resuming from {resume_phase.value}." if resume_phase else ""),
            priority="low",
            action_url=f"/config?step=0&agent_id={agent_id}" if agent_id else "/config?step=0",
            action_label="Track Progress",
            related_entity_type="embedding_job",
            related_entity_id=config_id
        )
            
        data_source_type = config.get('data_source_type', 'database')
        documents = []
        table_data = None
        child_chunks = None
        
        # Parse schema selection/column selection early
        schema_snapshot_raw = config.get('schema_selection', '{}')
        selected_columns = None
        try:
            if schema_snapshot_raw is None:
                schema_snapshot_raw = '{}'
            # Handle potential double-encoding from earlier versions
            if isinstance(schema_snapshot_raw, str) and schema_snapshot_raw.startswith('"') and schema_snapshot_raw.endswith('"'):
                try:
                    schema_snapshot_raw = json.loads(schema_snapshot_raw)
                except json.JSONDecodeError:
                    pass
            schema_selection = json.loads(schema_snapshot_raw)
            if isinstance(schema_selection, str):
                schema_selection = json.loads(schema_selection)
            
            if data_source_type == 'file':
                # For file sources, schema_selection is a list of selected columns
                if isinstance(schema_selection, list):
                    selected_columns = schema_selection
                    logger.info(f"Using selected columns for file embedding: {selected_columns}")
            else:
                # For database sources, schema_selection is a dict or list for tables
                if isinstance(schema_selection, dict):
                    target_tables = list(schema_selection.keys())
                elif isinstance(schema_selection, list):
                    target_tables = schema_selection
                else:
                    target_tables = []
        except Exception as e:
            logger.error(f"Failed to parse schema_selection: {e}. Raw was: {schema_snapshot_raw}")
            if data_source_type != 'file':
                target_tables = []
            parse_error = str(e)
        
        # =================================================================
        # BUILD CONFIG FROM UI INPUTS
        # =================================================================
        chunking_conf = json.loads(config.get('chunking_config', '{}') or '{}')
        
        # Get system defaults from settings service (no hardcoding!)
        from backend.services.settings_service import get_settings_service, SettingCategory
        settings_service = get_settings_service()
        
        # Load chunking defaults from system settings
        try:
            chunking_defaults = settings_service.get_category_settings_raw(SettingCategory.CHUNKING.value)
        except Exception as e:
            logger.warning(f"Failed to load chunking settings from DB, using fallback: {e}")
            chunking_defaults = {}
        
        # Priority: UI input > DB config > System settings
        if ui_chunking:
            parent_chunk_size = ui_chunking.parent_chunk_size
            parent_chunk_overlap = ui_chunking.parent_chunk_overlap
            child_chunk_size = ui_chunking.child_chunk_size
            child_chunk_overlap = ui_chunking.child_chunk_overlap
            logger.info(f"Using UI chunking config: parent={parent_chunk_size}/{parent_chunk_overlap}, child={child_chunk_size}/{child_chunk_overlap}")
        elif chunking_conf:
            parent_chunk_size = chunking_conf.get('parentChunkSize', chunking_defaults.get('parent_chunk_size', 512))
            parent_chunk_overlap = chunking_conf.get('parentChunkOverlap', chunking_defaults.get('parent_chunk_overlap', 100))
            child_chunk_size = chunking_conf.get('childChunkSize', chunking_defaults.get('child_chunk_size', 128))
            child_chunk_overlap = chunking_conf.get('childChunkOverlap', chunking_defaults.get('child_chunk_overlap', 25))
            logger.info(f"Using DB chunking config: parent={parent_chunk_size}/{parent_chunk_overlap}, child={child_chunk_size}/{child_chunk_overlap}")
        else:
            # Use system settings as defaults (configured in Settings page)
            parent_chunk_size = chunking_defaults.get('parent_chunk_size', 512)
            parent_chunk_overlap = chunking_defaults.get('parent_chunk_overlap', 100)
            child_chunk_size = chunking_defaults.get('child_chunk_size', 128)
            child_chunk_overlap = chunking_defaults.get('child_chunk_overlap', 25)
            logger.info(f"Using system settings chunking config: parent={parent_chunk_size}/{parent_chunk_overlap}, child={child_chunk_size}/{child_chunk_overlap}")
        
        extractor_config = {
            "tables": {"exclude_tables": [], "global_exclude_columns": []},
            "chunking": {
                "parent_splitter": {"chunk_size": parent_chunk_size, "chunk_overlap": parent_chunk_overlap},
                "child_splitter": {"chunk_size": child_chunk_size, "chunk_overlap": child_chunk_overlap}
            }
        }
        
        if ui_parallelization:
            override_num_workers = ui_parallelization.num_workers
            override_chunking_batch_size = ui_parallelization.chunking_batch_size
            delta_check_batch_size = ui_parallelization.delta_check_batch_size
            logger.info(f"Using UI parallelization: workers={override_num_workers}, chunk_batch={override_chunking_batch_size}, delta_batch={delta_check_batch_size}")
        else:
            override_num_workers = None
            override_chunking_batch_size = None
            delta_check_batch_size = 50000
        
        transformer = AdvancedDataTransformer(
            extractor_config, 
            docstore_path=docstore_path,
            num_workers_override=override_num_workers,
            batch_size_override=override_chunking_batch_size
        )

        # =================================================================
        # PHASE 1: EXTRACTION (or restore from checkpoint)
        # =================================================================
        if data_source_type == 'file':
            # File-based source - load from DuckDB/CSV instead of limited preview
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, 
                                        phase="Loading file data from DuckDB...")
            
            # Get table name from config
            file_name = config.get('ingestion_file_name', '')
            if not file_name:
                raise ValueError("No file name found in configuration")
            
            # Import helper to get table name
            from backend.api.routes.ingestion import _sanitize_table_name, _get_user_duckdb_path
            table_name = _sanitize_table_name(file_name)
            duckdb_path = _get_user_duckdb_path(user_id)
            
            if not duckdb_path.exists():
                # Fallback to preview documents if DuckDB not available
                logger.warning(f"DuckDB not found at {duckdb_path}, falling back to preview documents")
                documents_raw = config.get('ingestion_documents')
                if not documents_raw:
                    raise ValueError("No documents found for file data source")
                parsed_docs = json.loads(documents_raw)
                for doc in parsed_docs:
                    documents.append(Document(
                        page_content=doc.get("page_content", ""),
                        metadata=doc.get("metadata", {})
                    ))
            else:
                # Load ALL rows from DuckDB
                import duckdb
                
                try:
                    conn = duckdb.connect(str(duckdb_path), read_only=True)
                    
                    # Get total row count first
                    count_result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                    total_rows = count_result[0] if count_result else 0
                    logger.info(f"Loading {total_rows:,} rows from DuckDB table: {table_name}")
                    
                    # Get column names
                    col_info = conn.execute(f"DESCRIBE SELECT * FROM {table_name}").fetchall()
                    columns = [row[0] for row in col_info]
                    
                    # Process in batches to avoid memory issues
                    BATCH_SIZE = 10000
                    offset = 0
                    doc_id = 0
                    
                    while offset < total_rows:
                        if job_service.is_job_cancelled(job_id):
                            raise JobCancelledError(f"Job {job_id} cancelled during file loading")
                        
                        # Fetch batch
                        batch_query = f"SELECT * FROM {table_name} LIMIT {BATCH_SIZE} OFFSET {offset}"
                        rows = conn.execute(batch_query).fetchall()
                        
                        for row in rows:
                            # Create document content from row data
                            row_dict = {columns[i]: row[i] for i in range(len(columns)) if row[i] is not None}
                            
                            # Filter columns if selection is provided
                            if selected_columns:
                                row_dict = {k: v for k, v in row_dict.items() if k in selected_columns}
                            
                            # Format as readable text for embedding
                            content_parts = []
                            for col, val in row_dict.items():
                                if val is not None and str(val).strip():
                                    # Clean column name for readability
                                    clean_col = col.replace('_', ' ').title()
                                    content_parts.append(f"{clean_col}: {val}")
                            
                            if content_parts:
                                page_content = "\n".join(content_parts)
                                documents.append(Document(
                                    page_content=page_content,
                                    metadata={
                                        "source": file_name,
                                        "table": table_name,
                                        "row_id": doc_id,
                                        "source_id": f"{table_name}_row_{doc_id}"
                                    }
                                ))
                                doc_id += 1
                        
                        offset += BATCH_SIZE
                        if offset % 50000 == 0 or offset >= total_rows:
                            job_service.update_progress(
                                job_id, processed_documents=0, current_batch=0,
                                phase=f"Loading rows from file... ({min(offset, total_rows):,}/{total_rows:,})"
                            )
                            logger.info(f"Loaded {min(offset, total_rows):,}/{total_rows:,} rows from {table_name}")
                    
                    conn.close()
                    logger.info(f"Created {len(documents):,} documents from {table_name}")
                    
                except duckdb.CatalogException:
                    conn.close()
                    raise ValueError(f"Table '{table_name}' not found in DuckDB. The file may still be processing in background. Please wait and try again.")
                except Exception as e:
                    raise ValueError(f"Failed to load data from DuckDB: {e}")
        else:
            # Database source - check for extraction checkpoint
            if resume_phase and resume_phase != CheckpointPhase.EXTRACTION:
                # Try to load extraction checkpoint
                table_data = checkpoint_service.load_extraction_checkpoint()
                if table_data:
                    logger.info(f"CHECKPOINT: Loaded extraction data from checkpoint ({sum(len(v) for v in table_data.values())} rows)")
                else:
                    logger.warning("CHECKPOINT: Extraction checkpoint not found, re-extracting...")
                    resume_phase = None  # Force re-extraction
            
            if not table_data:
                # Perform extraction
                connection_id = config.get('connection_id')
                if not connection_id:
                    raise ValueError(
                        f"Configuration {config_id} has data_source_type='database' but no connection_id. "
                        "Please edit the agent configuration and select a database connection, then republish."
                    )
                connection_info = db_service.get_db_connection_by_id(connection_id)
                if not connection_info:
                    raise ValueError(f"Connection {connection_id} not found")
                
                # Get the database URI from the connection
                database_uri = connection_info.get('uri')
                if not database_uri:
                    raise ValueError(f"Connection {connection_id} has no URI configured")
                    
                if not 'target_tables' in locals() or not target_tables:
                    err_msg = parse_error if 'parse_error' in locals() else 'None'
                    raise ValueError(f"Schema parsing failed or no tables selected. Error: {err_msg}")

                from backend.pipeline.extract import DataExtractor
                from backend.config import get_settings
                from pathlib import Path
                
                settings = get_settings()
                backend_root = Path(__file__).parent.parent.parent
                config_rel_path = str(settings.rag_config_path).lstrip('./')
                config_path = str((backend_root / config_rel_path).resolve())
                
                # Pass the database_uri from the config to DataExtractor
                extractor = DataExtractor(config_path, database_uri=database_uri)
                extractor.get_allowed_tables = lambda: target_tables

                import asyncio
                job_service._update_job(job_id, status=EmbeddingJobStatus.PREPARING, phase="Extracting tables...")
                
                async def extractor_progress(current, total, table_name):
                    if job_service.is_job_cancelled(job_id):
                        raise JobCancelledError(f"Job {job_id} cancelled during extraction of {table_name}")
                    job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Extracting {table_name} ({current}/{total})")

                table_data = await extractor.extract_all_tables(on_progress=extractor_progress)
                
                job_progress = job_service.get_job_progress(job_id)
                if not job_progress or job_progress.status == EmbeddingJobStatus.CANCELLED:
                    logger.info(f"Job {job_id} cancelled after extraction.")
                    return
                
                # =================================================================
                # CHECKPOINT: Save extraction data
                # =================================================================
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Saving extraction checkpoint...")
                checkpoint_service.save_extraction_checkpoint(job_id, config_id, table_data, incremental)
                logger.info(f"CHECKPOINT: Extraction phase complete and saved")
        
        # =================================================================
        # PHASE 2: DOCUMENT CREATION (or restore from checkpoint)
        # =================================================================
        if resume_phase and resume_phase not in [CheckpointPhase.EXTRACTION, CheckpointPhase.DOCUMENTS]:
            # Try to load documents checkpoint
            documents = checkpoint_service.load_documents_checkpoint()
            if documents:
                logger.info(f"CHECKPOINT: Loaded {len(documents)} documents from checkpoint")
            else:
                logger.warning("CHECKPOINT: Documents checkpoint not found, re-creating...")
                resume_phase = CheckpointPhase.DOCUMENTS  # Force re-creation
        
        if not documents and table_data:
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Generating documents from data...")
            
            def transformer_doc_progress(current, total, table_name):
                if job_service.is_job_cancelled(job_id):
                    raise JobCancelledError(f"Job {job_id} cancelled during transformation of {table_name}")
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Transforming {table_name} ({current}/{total})")

            import asyncio
            documents = await asyncio.to_thread(
                transformer.create_documents_from_tables, 
                table_data, 
                on_progress=transformer_doc_progress,
                check_cancellation=lambda: job_service.is_job_cancelled(job_id)
            )
            
            job_progress = job_service.get_job_progress(job_id)
            if not job_progress or job_progress.status == EmbeddingJobStatus.CANCELLED:
                logger.info(f"Job {job_id} cancelled after transformation.")
                return
            
            # =================================================================
            # CHECKPOINT: Save documents
            # =================================================================
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Saving documents checkpoint...")
            checkpoint_service.save_documents_checkpoint(job_id, config_id, documents, incremental)
            logger.info(f"CHECKPOINT: Documents phase complete ({len(documents)} docs saved)")
        
        job_service._update_job(job_id, total_documents=len(documents))
        vector_db_name = v_db_name

        # Register in vector_db_registry
        try:
            llm_conf = json.loads(config.get('llm_config', '{}') or '{}')
            llm_name = llm_conf.get('model', 'default_llm')
            conn_reg = db_service.get_connection()
            cursor_reg = conn_reg.cursor()
            cursor_reg.execute('''
                INSERT INTO vector_db_registry (name, data_source_id, created_by, embedding_model, llm)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(name) DO UPDATE SET
                    data_source_id=excluded.data_source_id,
                    embedding_model=excluded.embedding_model,
                    llm=excluded.llm
            ''', (vector_db_name, str(config.get('connection_id') or config.get('agent_id') or 'system'), str(user_id), model_name, llm_name))
            conn_reg.commit()
            conn_reg.close()
        except Exception as e:
            logger.warning(f"Failed to update vector_db_registry: {e}")

        # Incremental Filtering
        source_documents = documents
        from backend.services.chroma_service import get_chroma_client
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        if not incremental:
            cursor.execute("DELETE FROM document_index WHERE vector_db_name = %s", (vector_db_name,))
            conn.commit()
            try:
                from backend.services.settings_service import get_settings_service, SettingCategory
                settings_service = get_settings_service()
                vs_settings = settings_service.get_category_settings_raw(SettingCategory.VECTOR_STORE)
                provider_type = vs_settings.get("type", "qdrant")  # Default to qdrant for prod
                
                from backend.pipeline.vector_stores.factory import VectorStoreFactory
                vector_store = VectorStoreFactory.get_provider(provider_type, collection_name=vector_db_name)
                
                import asyncio
                await vector_store.delete_collection()
                logger.info(f"Deleted existing collection {vector_db_name} for rebuild.")
            except Exception as e:
                logger.warning(f"Failed to cleanly delete collection during rebuild: {e}")
            docs_to_process = documents
            stale_source_ids = []
            logger.info(f"Rebuild mode: Wiped existing database indexing for {vector_db_name}")
        else:
            cursor.execute("SELECT source_id, checksum FROM document_index WHERE vector_db_name = %s", (vector_db_name,))
            existing_docs = {row['source_id']: row['checksum'] for row in cursor.fetchall()}
            
            logger.info(f"Checking for deltas among {len(documents)} documents...")
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Checking for modified documents...")
            
            num_workers = max(1, multiprocessing.cpu_count() // 2)
            doc_batches = [documents[i:i + delta_check_batch_size] for i in range(0, len(documents), delta_check_batch_size)]
            
            # Sync function for delta checking (runs in thread pool)
            def run_delta_check_sync():
                local_docs = []
                local_stale = []
                with ProcessPoolExecutor(max_workers=num_workers) as executor:
                    futures = [executor.submit(_parallel_delta_worker, batch, existing_docs) for batch in doc_batches]
                    for future in tqdm(as_completed(futures), total=len(futures), desc="Delta Check"):
                        if job_service.is_job_cancelled(job_id):
                            raise JobCancelledError(f"Job {job_id} cancelled during Delta Check")
                        batch_processed, batch_stale = future.result()
                        local_docs.extend(batch_processed)
                        local_stale.extend(batch_stale)
                return local_docs, local_stale

            import asyncio
            docs_to_process, stale_source_ids = await asyncio.to_thread(run_delta_check_sync)
            
            if len(docs_to_process) == 0:
                logger.info(f"Incremental run: 0 new/modified documents. Skipping embedding.")
                job_service.complete_job(job_id, validation_passed=True)
                return

            if stale_source_ids:
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Purging {len(stale_source_ids)} outdated documents...")
                try:
                    from backend.services.settings_service import get_settings_service, SettingCategory
                    settings_service = get_settings_service()
                    vs_settings = settings_service.get_category_settings_raw(SettingCategory.VECTOR_STORE)
                    provider_type = vs_settings.get("type", "qdrant")
                    
                    from backend.pipeline.vector_stores.factory import VectorStoreFactory
                    vector_store = VectorStoreFactory.get_provider(provider_type, collection_name=vector_db_name)
                    
                    import asyncio
                    await vector_store.delete_by_source_ids(stale_source_ids)
                    logger.info(f"Deleted outdated chunks for {len(stale_source_ids)} documents.")
                except Exception as e:
                    logger.warning(f"Failed to cleanly delete stale chunks from Vector DB: {e}")

        documents = docs_to_process
        
        # =================================================================
        # PHASE 3: CHUNKING (or restore from checkpoint)
        # =================================================================
        if resume_phase == CheckpointPhase.EMBEDDING:
            # Try to load chunks checkpoint
            child_chunks = checkpoint_service.load_chunks_checkpoint()
            if child_chunks:
                logger.info(f"CHECKPOINT: Loaded {len(child_chunks)} chunks from checkpoint")
                documents = child_chunks
            else:
                logger.warning("CHECKPOINT: Chunks checkpoint not found, re-chunking...")
        
        if not child_chunks:
            import asyncio
            logger.info(f"Created {len(documents)} initial documents. Applying parent-child chunking...")
            
            def chunking_progress(phase, current, total):
                if job_service.is_job_cancelled(job_id):
                    raise JobCancelledError(f"Job {job_id} cancelled during chunking phase: {phase}")
                pct_str = f" ({current}/{total})" if total > 0 else f" ({current})"
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"{phase}{pct_str}")

            child_chunks, docstore = await asyncio.to_thread(
                transformer.perform_parent_child_chunking, 
                documents, 
                on_progress=chunking_progress,
                check_cancellation=lambda: job_service.is_job_cancelled(job_id)
            )
            
            job_progress = job_service.get_job_progress(job_id)
            if not job_progress or job_progress.status == EmbeddingJobStatus.CANCELLED:
                logger.info(f"Job {job_id} cancelled after chunking.")
                return
            
            # =================================================================
            # CHECKPOINT: Save chunks (SKIP for large datasets - ChromaDB handles resume)
            # =================================================================
            CHECKPOINT_THRESHOLD = 100000  # Skip checkpoint for datasets > 100k chunks
            if len(child_chunks) <= CHECKPOINT_THRESHOLD:
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Saving chunks checkpoint...")
                checkpoint_service.save_chunks_checkpoint(job_id, config_id, child_chunks, incremental)
                logger.info(f"CHECKPOINT: Chunking phase complete ({len(child_chunks)} chunks saved)")
            else:
                logger.info(f"CHECKPOINT: Skipping chunks checkpoint for large dataset ({len(child_chunks):,} chunks > {CHECKPOINT_THRESHOLD:,} threshold). ChromaDB stateful resume will handle interruptions.")
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, 
                                            phase=f"Skipped checkpoint (large dataset: {len(child_chunks):,} chunks)")
            
            documents = child_chunks
        else:
            # Load docstore separately if we resumed from chunks checkpoint
            docstore = None
            if os.path.exists(docstore_path):
                try:
                    from backend.pipeline.docstore import SQLiteDocStore
                    docstore = SQLiteDocStore(docstore_path)
                    logger.info(f"Loaded existing docstore from {docstore_path}")
                except Exception as e:
                    logger.warning(f"Could not load docstore: {e}")
        
        logger.info(f"Chunking complete. {len(documents)} child documents ready for embedding.")
            
        # =================================================================
        # PHASE 4: EMBEDDING (ChromaDB handles checkpointing)
        # =================================================================
        from backend.services.settings_service import get_settings_service, SettingCategory
        settings_service = get_settings_service()
        emb_settings = settings_service.get_category_settings_raw(SettingCategory.EMBEDDING)
        
        provider_type = emb_settings.get("provider", "sentence-transformers")
        
        # =================================================================
        # MPS/CUDA BATCH SIZE OPTIMIZATION
        # For local GPU providers, override small UI batch sizes for efficiency
        # =================================================================
        MIN_GPU_BATCH_SIZE = 128  # Optimal for MPS/CUDA with BGE-M3
        
        # Local GPU providers that benefit from larger batch sizes
        LOCAL_GPU_PROVIDERS = ("sentence-transformers", "huggingface", "bge-m3", "bge")
        
        # Also check model name for local models (handles misconfigured provider settings)
        LOCAL_MODEL_PATTERNS = ("bge-", "bge_", "sentence-transformers", "all-minilm", "e5-", "gte-")
        model_name_lower = model_name.lower() if model_name else ""
        is_local_model = (
            provider_type in LOCAL_GPU_PROVIDERS or 
            any(pattern in model_name_lower for pattern in LOCAL_MODEL_PATTERNS)
        )
        
        if is_local_model and provider_type not in LOCAL_GPU_PROVIDERS:
            logger.info(f"Detected local model '{model_name}' but provider is '{provider_type}'. Treating as local GPU model.")
        
        if ui_batch_size is not None:
            batch_size = ui_batch_size
            # Override suboptimal batch sizes for GPU providers
            if is_local_model and batch_size < MIN_GPU_BATCH_SIZE:
                logger.info(f"MPS/CUDA OPTIMIZATION: UI batch_size={batch_size} is suboptimal for GPU. Overriding to {MIN_GPU_BATCH_SIZE} for ~2.5x speedup.")
                batch_size = MIN_GPU_BATCH_SIZE
            else:
                logger.info(f"Using UI-specified batch_size: {batch_size}")
        elif provider_type == "openai" and not is_local_model:
            batch_size = emb_conf.get("batch_size", 500)
        else:
            # Default to optimal GPU batch size for local models
            batch_size = emb_conf.get("batch_size", MIN_GPU_BATCH_SIZE)
        
        if ui_max_concurrent is not None:
            max_concurrent = ui_max_concurrent
            logger.info(f"Using UI-specified max_concurrent: {max_concurrent}")
        elif provider_type == "openai" and not is_local_model:
            max_concurrent = 20
        else:
            max_concurrent = min(4, max(1, multiprocessing.cpu_count() // 4))
        
        logger.info(f"Embedding batch config: batch_size={batch_size}, max_concurrent={max_concurrent}, provider={provider_type}, model={model_name}")
            
        total_docs = len(documents)
        import math
        total_batches = math.ceil(total_docs / batch_size)
        job_service._update_job(job_id, total_documents=total_docs, total_batches=total_batches)
        
        job_service.transition_to_embedding(job_id)

        use_celery = os.getenv("USE_CELERY_FOR_EMBEDDINGS", "false").lower() == "true"
        
        if use_celery:
            logger.info(f"Celery mode enabled - dispatching batches to RabbitMQ queue")
        
        processor = EmbeddingBatchProcessor(BatchConfig(
            batch_size=batch_size,
            max_concurrent=max_concurrent,
            retry_attempts=ui_retry_attempts
        ), use_celery=use_celery, table_name=vector_db_name)
        
        # Stateful resume: Fetch existing chunk IDs from Chroma
        from backend.services.chroma_service import get_existing_chunk_ids
        
        job_service.update_progress(job_id, processed_documents=0, current_batch=0, 
                                    phase="Checking for already-embedded chunks (stateful resume)...")
        
        import asyncio
        existing_chunk_ids = await asyncio.to_thread(get_existing_chunk_ids, chroma_path, vector_db_name)
        
        if existing_chunk_ids:
            logger.info(f"Stateful resume: Found {len(existing_chunk_ids)} existing embeddings in Chroma")
            processor.set_existing_ids(existing_chunk_ids)
        else:
            logger.info("Stateful resume: No existing embeddings found, processing all documents")
        
        registry = get_embedding_processor_registry()
        registry.register(job_id, processor)
        
        skipped_count = 0
        
        async def on_progress(processed: int, failed: int, total: int):
            current_batch = (processed // batch_size) + 1
            job_service.update_progress(job_id, processed, current_batch, failed, skipped_documents=skipped_count)
            
        vs_settings = settings_service.get_category_settings_raw(SettingCategory.VECTOR_STORE)
        vector_db_provider_type = vs_settings.get("type", "qdrant")
        
        from backend.pipeline.vector_stores.factory import VectorStoreFactory
        vector_store = VectorStoreFactory.get_provider(vector_db_provider_type, collection_name=vector_db_name)
        
        consecutive_failures = 0
        max_consecutive_failures = ui_max_consecutive_failures
        
        from backend.services.embedding_batch_processor import BatchResult
        
        async def on_batch_complete(batch_result: BatchResult):
            nonlocal consecutive_failures
            if not batch_result.embeddings:
                return
            start_idx = batch_result.start_idx
            batch_docs = documents[start_idx : start_idx + batch_result.documents_processed]
            
            ids, texts, embeddings, metadatas = [], [], [], []
            for doc, emb in zip(batch_docs, batch_result.embeddings):
                if emb is not None:
                    chunk_content = getattr(doc, "page_content", getattr(doc, "content", ""))
                    parent_id = doc.metadata.get("doc_id", "unknown")
                    chunk_id = hashlib.sha256(f"{chunk_content}{parent_id}".encode()).hexdigest()
                    ids.append(chunk_id)
                    texts.append(chunk_content)
                    embeddings.append(emb)
                    safe_meta = {}
                    meta_dict = getattr(doc, "metadata", {})
                    if isinstance(meta_dict, dict):
                        for k, v in meta_dict.items():
                            if isinstance(v, (str, int, float, bool)):
                                safe_meta[k] = v
                            elif v is not None:
                                safe_meta[k] = str(v)
                    metadatas.append(safe_meta)
                    
            if ids:
                for attempt in range(ui_retry_attempts):
                    try:
                        await vector_store.upsert_batch(
                            ids=ids,
                            documents=texts,
                            embeddings=embeddings,
                            metadatas=metadatas
                        )
                        consecutive_failures = 0
                        break
                    except Exception as e:
                        consecutive_failures += 1
                        if consecutive_failures >= max_consecutive_failures:
                            raise RuntimeError(f"Vector DB circuit breaker: {consecutive_failures} consecutive failures. Last error: {e}")
                        if attempt == ui_retry_attempts - 1:
                            raise
                        import random
                        await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))

        doc_contents = [d.page_content for d in documents]
        
        result = await processor.process_documents_with_resume(
            doc_contents,
            doc_objects=documents,
            on_progress=on_progress,
            on_batch_complete=on_batch_complete
        )
        
        skipped_count = result.get("skipped_documents", 0)
        registry.unregister(job_id)
        
        if result["cancelled"]:
            logger.info(f"Embedding loop for job {job_id} recognized cancellation.")
            return
        
        if result.get("resumed"):
            logger.info(f"Stateful resume complete: Skipped {skipped_count} already-embedded, processed {result['processed_documents']} new")
        
        # Export SQLite docstore to pickle for backward compatibility
        if docstore:
            docstore_pickle_path = f"{chroma_path}/parent_docstore.pkl"
            if hasattr(docstore, 'export_to_pickle'):
                await asyncio.to_thread(docstore.export_to_pickle, docstore_pickle_path)
            else:
                import pickle
                with open(docstore_pickle_path, "wb") as f:
                    pickle.dump(docstore, f)
            logger.info(f"Parent docstore exported to {docstore_pickle_path}")
        
        # =================================================================
        # CHECKPOINT: Mark as complete
        # =================================================================
        from backend.services.embedding_checkpoint_service import CheckpointMetadata
        from datetime import datetime
        
        complete_metadata = CheckpointMetadata(
            job_id=job_id,
            config_id=config_id,
            phase=CheckpointPhase.COMPLETE,
            created_at=datetime.utcnow().isoformat(),
            total_items=result['processed_documents'],
            checksum="complete",
            incremental=incremental,
            extra={"skipped": skipped_count, "failed": result['failed_documents']}
        )
        checkpoint_service.save_metadata(complete_metadata)
        logger.info(f"CHECKPOINT: Job marked as complete")
        
        job_service.transition_to_validating(job_id)
        validation_passed = result["failed_documents"] == 0
        
        job_service.transition_to_storing(job_id)
        
        for doc in source_documents:
            metadata = doc.metadata if doc.metadata else {}
            if 'checksum' in metadata and 'source_id' in metadata:
                cursor.execute('''
                    INSERT INTO document_index (vector_db_name, source_id, checksum)
                    VALUES (%s, %s, %s)
                    ON CONFLICT(vector_db_name, source_id) DO UPDATE SET
                        checksum=excluded.checksum,
                        updated_at=CURRENT_TIMESTAMP
                ''', (vector_db_name, metadata['source_id'], metadata['checksum']))
        conn.commit()
        
        try:
            cursor.execute(f'''
                UPDATE vector_db_registry 
                SET {"last_incremental_run" if incremental else "last_full_run"} = CURRENT_TIMESTAMP
                WHERE name = %s
            ''', (vector_db_name,))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update run timestamps: {e}")
            
        duration = time.time() - start_time
        logger.info(f"EMBEDDING JOB SUMMARY | Job: {job_id} | Namespace: {vector_db_name} | "
                    f"Model: {model_name} | Total Chunks: {len(documents)} | "
                    f"Processed: {result['processed_documents']} | Failed: {result['failed_documents']} | "
                    f"Duration: {duration:.2f}s | Speed: {result['average_speed']:.2f} docs/sec")
        
        conn.close()
        job_service.complete_job(job_id, validation_passed=validation_passed)
        
        # INVALIDATE SQL CACHE ON SUCCESSFUL SYNC
        try:
            from backend.services.sql_service import invalidate_sql_cache
            invalidate_sql_cache()
            logger.info("Invalidated SQL query cache following manual database sync.")
        except Exception as e:
            logger.warning(f"Failed to invalidate SQL cache after manual sync: {e}")
            
        
        await notification_service.create_notification(
            user_id=user_id,
            notification_type="embedding_complete",
            title="Sync Complete",
            message=f"Successfully updated {result['processed_documents']} embeddings for {vector_db_name}.",
            priority="medium",
            action_url=f"/config?step=0&agent_id={agent_id}" if agent_id else "/config?step=0",
            action_label="View Sync Info",
            related_entity_type="embedding_job",
            related_entity_id=config_id
        )
        
    except JobCancelledError as e:
        logger.info(f"Embedding job {job_id} stopped: {e}")
        return

    except Exception as e:
        logger.error(f"Embedding job {job_id} failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        job_service.fail_job(job_id, str(e))
        
        try:
            await notification_service.create_notification(
                user_id=user_id,
                notification_type="embedding_failed",
                title="Embedding Generation Failed",
                message=str(e),
                priority="high"
            )
        except:
            pass


def _parallel_delta_worker(doc_batch: List[Document], existing_docs: Dict[str, str]) -> Tuple[List[Document], List[str]]:
    """Helper to parallelize checksum calculation and delta selection."""
    processed = []
    stale = []
    
    for doc in doc_batch:
        content = getattr(doc, "page_content", getattr(doc, "content", ""))
        doc_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        if hasattr(doc, "metadata"):
            doc.metadata['checksum'] = doc_hash
        
        if hasattr(doc, "metadata") and "source_id" in doc.metadata:
            doc_id = doc.metadata['source_id']
        else:
            doc_id = str(uuid.uuid4())
            
        if hasattr(doc, "metadata"):
            doc.metadata['source_id'] = doc_id
            
        if doc_id in existing_docs:
            if existing_docs[doc_id] != doc_hash:
                stale.append(doc_id)
                processed.append(doc)
        else:
            processed.append(doc)
            
    return processed, stale


@router.get("/{job_id}/progress", response_model=EmbeddingJobProgress)
async def get_embedding_progress(
    job_id: str,
    current_user: User = Depends(require_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service)
):
    """
    Get current progress of an embedding job.
    
    Use this for polling-based progress updates.
    For real-time updates, use the WebSocket endpoint.
    
    Requires Admin role or above.
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
    current_user: User = Depends(require_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service)
):
    """
    Get summary of a completed embedding job.
    
    Requires Admin role or above.
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
    current_user: User = Depends(require_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service),
    auth_service: AuthorizationService = Depends(get_authorization_service)
):
    """
    Cancel a running embedding job.
    
    Only jobs in QUEUED, PREPARING, or EMBEDDING status can be cancelled.
    
    Requires Admin role or above.
    """
    success = job_service.cancel_job(job_id, current_user)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job cannot be cancelled (may be already completed or not found)"
        )
    
    # Also cancel active processor if it exists
    registry = get_embedding_processor_registry()
    processor = registry.get_processor(job_id)
    if processor:
        logger.info(f"Signalling cancellation to processor for job {job_id}")
        processor.cancel()
    
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
    config_id: Optional[int] = None,
    limit: int = 10,
    offset: int = 0,
    current_user: User = Depends(require_admin),
    job_service: EmbeddingJobService = Depends(get_embedding_job_service)
):
    """
    List all embedding jobs with optional filtering.
    
    Requires Admin role or above.
    """
    jobs = job_service.list_jobs(
        status=status_filter,
        config_id=config_id,
        limit=limit,
        offset=offset
    )
    
    return jobs


@router.get("/checkpoint/{vector_db_name}", response_model=dict)
async def get_checkpoint_status(
    vector_db_name: str,
    current_user: User = Depends(require_admin)
):
    """
    Get checkpoint status for a vector database.
    
    Returns information about existing checkpoints that can be used
    to resume an interrupted embedding job.
    
    Requires SuperAdmin role.
    """
    try:
        base_indexes_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/indexes"))
        checkpoint_service = get_checkpoint_service(base_indexes_path, vector_db_name)
        status = checkpoint_service.get_checkpoint_status()
        return status
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get checkpoint status: {str(e)}"
        )


@router.delete("/checkpoint/{vector_db_name}", response_model=dict)
async def clear_checkpoints(
    vector_db_name: str,
    current_user: User = Depends(require_admin),
    auth_service: AuthorizationService = Depends(get_authorization_service)
):
    """
    Clear all checkpoints for a vector database.
    
    Use this to force a full rebuild from scratch on the next job.
    
    Requires SuperAdmin role.
    """
    try:
        base_indexes_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/indexes"))
        checkpoint_service = get_checkpoint_service(base_indexes_path, vector_db_name)
        checkpoint_service.clear_checkpoints()
        
        auth_service.log_rag_action(
            user=current_user,
            action=RAGAuditAction.EMBEDDING_CANCELLED,
            changes={"action": "checkpoints_cleared", "vector_db_name": vector_db_name}
        )
        
        return {
            "status": "success",
            "message": f"Cleared all checkpoints for {vector_db_name}"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear checkpoints: {str(e)}"
        )
