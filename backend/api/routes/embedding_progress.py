"""
API routes for embedding job management and progress tracking.
Requires SuperAdmin role for all operations.
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
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

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
from backend.pipeline.extract import create_data_extractor
from backend.pipeline.transform import AdvancedDataTransformer
from backend.core.permissions import require_super_admin, get_current_user
from backend.core.logging import get_embedding_logger

logger = get_embedding_logger()

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
        from backend.sqliteDb.db import get_db_service
        db_service = get_db_service()
        config = db_service.get_config_by_id(request.config_id)
        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration {request.config_id} not found")
            
        from backend.core.vector_db_utils import derive_vector_db_name
        import json
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
            
        # Optional: Check if model exists, but don't strictly require it to be in the local LLM Registry 
        # since embeddings might use a different service or external provider.
        # We assume if the model string exists, it's valid enough to queue the job.
            
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
            user_id=current_user.id,
            incremental=request.incremental
        )
        
        logger.info(f"Started embedding job {job_id} for config {request.config_id} (incremental={request.incremental})")
        
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

async def _run_embedding_job(job_id: str, config_id: int, user_id: int, incremental: bool = True):
    """Background task to run embedding generation."""
    job_service = get_embedding_job_service()
    notification_service = get_notification_service()
    db_service = get_db_service()
    sql_service = get_sql_service()
    
    try:
        start_time = time.time()
        # 1. Fetch Configuration
        config = db_service.get_config_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration {config_id} not found")

        # --- T04: Robust Validation ---
        from backend.core.vector_db_utils import validate_vector_db_name
        import json
        emb_conf = json.loads(config.get('embedding_config', '{}') or '{}')
        
        # Validate Vector DB Namespace
        v_db_name = emb_conf.get('vectorDbName')
        if not v_db_name:
             # Fallback logic should have already happened in start_embedding_job, but we re-verify
             from backend.core.vector_db_utils import derive_vector_db_name
             source_btn = config.get('ingestion_file_name', '').split('.')[0] if config.get('data_source_type') == 'file' else None
             v_db_name = derive_vector_db_name(
                agent_id=config.get('agent_id'),
                connection_id=config.get('connection_id'),
                source_name=source_btn
             )
        
        is_valid, err_msg = validate_vector_db_name(v_db_name)
        if not is_valid:
            raise ValueError(f"Invalid Vector DB Namespace '{v_db_name}': {err_msg}")

        # Validate Embedding Model
        model_name = emb_conf.get('model')
        if not model_name:
            raise ValueError("No embedding model specified in configuration")

        agent_id = config.get('agent_id')

        # Start the job
        job_service.start_job(job_id)
        
        # Send start notification
        await notification_service.create_notification(
            user_id=user_id,
            notification_type="embedding_started",
            title="Embedding Generation Started",
            message=f"Sync process started for job {job_id}.",
            priority="low",
            action_url=f"/config?step=0&agent_id={agent_id}" if agent_id else "/config?step=0",
            action_label="Track Progress",
            related_entity_type="embedding_job",
            related_entity_id=config_id
        )
            
        data_source_type = config.get('data_source_type', 'database')
        documents = []
        
        if data_source_type == 'file':
            documents_raw = config.get('ingestion_documents')
            if not documents_raw:
                raise ValueError("No documents found for file data source")
            try:
                parsed_docs = json.loads(documents_raw)
                for i, doc in enumerate(parsed_docs):
                    # We can use a simple class or just let it be strings later
                    from backend.services.embedding_document_generator import EmbeddingDocument
                    # Construct simple wrapper since processor just needs content
                    documents.append(EmbeddingDocument(
                        document_id=f"file-doc-{i}",
                        document_type="file",
                        content=doc.get("page_content", ""),
                        metadata=doc.get("metadata", {})
                    ))
            except Exception as e:
                raise ValueError(f"Failed to parse ingestion documents: {e}")
                
        # --- T04 & T08: Common Transformer Setup ---
        # Default configuration for chunking and extraction
        extractor_config = {
            "tables": {
                "exclude_tables": [],
                "global_exclude_columns": []
            },
            "chunking": {
                "parent_splitter": {
                    "chunk_size": 800,
                    "chunk_overlap": 150
                },
                "child_splitter": {
                    "chunk_size": 200,
                    "chunk_overlap": 50
                }
            }
        }
        
        # Override with specific chunking configs if available
        chunking_conf = json.loads(config.get('chunking_config', '{}') or '{}')
        if chunking_conf:
            extractor_config['chunking']['parent_splitter']['chunk_size'] = chunking_conf.get('parentChunkSize', 800)
            extractor_config['chunking']['parent_splitter']['chunk_overlap'] = chunking_conf.get('parentChunkOverlap', 150)
            extractor_config['chunking']['child_splitter']['chunk_size'] = chunking_conf.get('childChunkSize', 200)
            extractor_config['chunking']['child_splitter']['chunk_overlap'] = chunking_conf.get('childChunkOverlap', 50)
            
        transformer = AdvancedDataTransformer(extractor_config)

        if data_source_type != 'file':
            # Database flow
            connection_id = config.get('connection_id')
            if not connection_id:
                raise ValueError("Configuration missing connection_id")
                
            # 2. Fetch Connection Details
            connection_info = db_service.get_db_connection_by_id(connection_id)
            if not connection_info:
                raise ValueError(f"Connection {connection_id} not found")
                
            # 3. Determine Selected Tables
            # schema is stored as schema_selection in prompt_configs
            schema_snapshot_raw = config.get('schema_selection', '{}')
            try:
                if schema_snapshot_raw is None:
                    schema_snapshot_raw = '{}'
                
                # In case of double JSON encoding
                if isinstance(schema_snapshot_raw, str) and schema_snapshot_raw.startswith('"') and schema_snapshot_raw.endswith('"'):
                    try:
                        schema_snapshot_raw = json.loads(schema_snapshot_raw)
                    except json.JSONDecodeError:
                        pass

                schema_selection = json.loads(schema_snapshot_raw)
                
                # If still a string after first parse, parse again (double encoded)
                if isinstance(schema_selection, str):
                    schema_selection = json.loads(schema_selection)
                    
                if isinstance(schema_selection, dict):
                    target_tables = list(schema_selection.keys())
                elif isinstance(schema_selection, list):
                    target_tables = schema_selection
                else:
                    target_tables = []
            except Exception as e:
                logger.error(f"Failed to parse schema_selection: {e}. Raw was: {schema_snapshot_raw}")
                target_tables = []
                parse_error = str(e)
                
            if not target_tables:
                err_msg = parse_error if 'parse_error' in locals() else 'None'
                raise ValueError(f"Schema parsing failed. Error: {err_msg}, Raw repr: {repr(schema_snapshot_raw)}, Target tables: {target_tables}")

            # 4. Fetch Live Schema Metadata
            schema_info = sql_service.get_schema_info_for_connection(
                connection_info['uri'], 
                table_names=target_tables
            )
            
            # 5. Extract logic: use DataExtractor
            from backend.pipeline.extract import DataExtractor
            from backend.config import get_settings
            from pathlib import Path
            
            settings = get_settings()
            backend_root = Path(__file__).parent.parent.parent
            # Fix: use absolute path for config
            config_rel_path = str(settings.rag_config_path).lstrip('./')
            config_path = str((backend_root / config_rel_path).resolve())
            
            extractor = DataExtractor(config_path) # Load base excluded tables
            # Override allowed to just requested schema
            extractor.get_allowed_tables = lambda: target_tables

            import asyncio
            job_service._update_job(job_id, status=EmbeddingJobStatus.PREPARING, phase="Extracting tables...")
            
            async def extractor_progress(current, total, table_name):
                # We normalize "Preparing" to 20% of the total job or just show sub-progress
                # For now, let's keep it simple and update Phase string
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Extracting {table_name} ({current}/{total})")

            table_data = await extractor.extract_all_tables(on_progress=extractor_progress)
            
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Generating documents from data...")
            
            def transformer_doc_progress(current, total, table_name):
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Transforming {table_name} ({current}/{total})")

            documents = await asyncio.to_thread(transformer.create_documents_from_tables, table_data, on_progress=transformer_doc_progress)
            
            # Initial count update for progress tracking during delta/chunking
            job_service._update_job(job_id, total_documents=len(documents))
            
        # Get Vector DB Name with multi-tenant awareness
        from backend.core.vector_db_utils import derive_vector_db_name
        vector_db_name = "default_vector_db"
        try:
            emb_conf = json.loads(config.get('embedding_config', '{}') or '{}')
            if emb_conf and emb_conf.get('vectorDbName'):
                vector_db_name = emb_conf['vectorDbName']
            else:
                # Fallback matching the start endpoint logic
                source_btn = config.get('ingestion_file_name', '').split('.')[0] if config.get('data_source_type') == 'file' else None
                vector_db_name = derive_vector_db_name(
                    agent_id=config.get('agent_id'),
                    connection_id=config.get('connection_id'),
                    source_name=source_btn
                )
        except Exception as e:
            logger.warning(f"Failed to parse embedding config: {e}")

        # Ensure Vector DB is registered in the registry with metadata
        try:
            llm_conf = json.loads(config.get('llm_config', '{}') or '{}')
            llm_name = llm_conf.get('model', 'default_llm')
            
            conn_reg = db_service.get_connection()
            cursor_reg = conn_reg.cursor()
            cursor_reg.execute('''
                INSERT INTO vector_db_registry (name, data_source_id, created_by, embedding_model, llm)
                VALUES (?, ?, ?, ?, ?)
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
        source_documents = documents # keep reference for index update later
        import hashlib
        import os
        from backend.services.chroma_service import get_chroma_client
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../data/indexes/{vector_db_name}"))
        
        if not incremental:
            # Rebuild: wipe index and chroma
            cursor.execute("DELETE FROM document_index WHERE vector_db_name = ?", (vector_db_name,))
            conn.commit()
            
            try:
                client = get_chroma_client(chroma_path)
                try:
                    client.delete_collection(name=vector_db_name)
                    logger.info(f"Deleted existing complete collection {vector_db_name} for rebuild.")
                except ValueError:
                    pass # Collection doesn't exist yet
            except Exception as e:
                logger.warning(f"Failed to cleanly delete collection during rebuild: {e}")
                
            docs_to_process = documents
            stale_source_ids = []
            logger.info(f"Rebuild mode: Wiped existing database indexing for {vector_db_name}")
        else:
            cursor.execute("SELECT source_id, checksum FROM document_index WHERE vector_db_name = ?", (vector_db_name,))
            existing_docs = {row['source_id']: row['checksum'] for row in cursor.fetchall()}
            
            logger.info(f"Checking for deltas among {len(documents)} documents using parallel hashing...")
            
            # Parallelize hashing and delta check
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase="Checking for modified documents...")
            
            num_workers = max(1, multiprocessing.cpu_count() - 1)
            batch_size = 50000
            doc_batches = [documents[i:i + batch_size] for i in range(0, len(documents), batch_size)]
            
            docs_to_process = []
            stale_source_ids = []
            
            # Note: We need to serialize documents slightly for cleaner multiprocessing
            # although Document is picklable, it can be slow.
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(_parallel_delta_worker, batch, existing_docs) for batch in doc_batches]
                for future in tqdm(as_completed(futures), total=len(futures), desc="Delta Check"):
                    batch_processed, batch_stale = future.result()
                    docs_to_process.extend(batch_processed)
                    stale_source_ids.extend(batch_stale)
                    job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Delta Check: {len(docs_to_process)} changes found")
            
            if len(docs_to_process) == 0:
                logger.info(f"Incremental run: 0 new/modified documents out of {len(documents)}. Skipping embedding.")
                job_service.complete_job(job_id, validation_passed=True)
                return

            if stale_source_ids and os.path.exists(chroma_path):
                # Delete old chunks for updated documents
                job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"Purging {len(stale_source_ids)} outdated documents...")
                try:
                    client = get_chroma_client(chroma_path)
                    # Check if collection exists first to avoid errors
                    try:
                        collection = client.get_collection(name=vector_db_name)
                        # Delete in batches due to potential URL length limits
                        for i in range(0, len(stale_source_ids), 100):
                            batch_stale = stale_source_ids[i:i+100]
                            collection.delete(where={"source_id": {"$in": batch_stale}})
                        logger.info(f"Deleted outdated chunks for {len(stale_source_ids)} documents.")
                    except ValueError:
                        pass # Collection doesn't exist yet
                except Exception as e:
                    logger.warning(f"Failed to cleanly delete stale chunks from Chroma: {e}")

        # Override documents with only the delta to process
        documents = docs_to_process

            
        # Apply Advanced Parent-Child Chunking using Transformer
        import asyncio
        logger.info(f"Created {len(documents)} initial documents from all tables.")
        logger.info("Applying parent-child chunking to all documents...")
        
        def chunking_progress(phase, current, total):
            pct_str = f" ({current}/{total})" if total > 0 else f" ({current})"
            job_service.update_progress(job_id, processed_documents=0, current_batch=0, phase=f"{phase}{pct_str}")

        child_chunks, docstore = await asyncio.to_thread(transformer.perform_parent_child_chunking, documents, on_progress=chunking_progress)
        
        # Override documents with the generated child chunks
        documents = child_chunks
        logger.info(f"Chunking complete. Created {len(documents)} child documents.")
            
        # Determine optimal batch size and concurrency based on provider
        from backend.services.settings_service import get_settings_service, SettingCategory
        settings_service = get_settings_service()
        emb_settings = settings_service.get_category_settings_raw(SettingCategory.EMBEDDING)
        
        provider_type = emb_settings.get("provider", "sentence-transformers")
        
        # Performance tuning based on provider type
        if provider_type == "openai":
            # API can handle high concurrency
            batch_size = emb_conf.get("batch_size", 500)
            max_concurrent = 20
        else:
            # Local models benefit from larger batches but moderate concurrency
            # to avoid NPU/GPU queue contention while maximizing saturation.
            batch_size = emb_conf.get("batch_size", 256)
            max_concurrent = 4 # Sweet spot for M-series MPS/CPU
            
        # Update job with accurate document count and total batches
        total_docs = len(documents)
        import math
        total_batches = math.ceil(total_docs / batch_size)
        job_service._update_job(job_id, total_documents=total_docs, total_batches=total_batches)
        
        # Transition to embedding phase
        job_service.transition_to_embedding(job_id)

        processor = EmbeddingBatchProcessor(BatchConfig(
            batch_size=batch_size,
            max_concurrent=max_concurrent
        ))
        
        async def on_progress(processed: int, failed: int, total: int):
            current_batch = (processed // batch_size) + 1
            job_service.update_progress(job_id, processed, current_batch, failed)
            
        # Initialize Vector DB early for streaming
        os.makedirs(chroma_path, exist_ok=True)
        client = get_chroma_client(chroma_path)
        collection = client.get_or_create_collection(name=vector_db_name)
        
        from backend.services.embedding_batch_processor import BatchResult
        
        async def on_batch_complete(batch_result: BatchResult):
            if not batch_result.embeddings:
                return
                
            # Map batch back to original document slice
            start_idx = batch_result.start_idx
            batch_docs = documents[start_idx : start_idx + batch_result.documents_processed]
            
            ids = []
            texts = []
            embeddings = []
            metadatas = []
            
            for doc, emb in zip(batch_docs, batch_result.embeddings):
                if emb is not None:
                    # Assign a stable ID for every chunk to remain idempotent
                    # Hash of content + parent ID
                    chunk_content = getattr(doc, "page_content", getattr(doc, "content", ""))
                    parent_id = doc.metadata.get("parent_doc_id", "unknown")
                    chunk_id = hashlib.sha256(f"{chunk_content}{parent_id}".encode()).hexdigest()
                    
                    ids.append(chunk_id)
                    texts.append(chunk_content)
                    embeddings.append(emb)
                    
                    # Sanitize metadata
                    safe_meta = {}
                    meta_dict = getattr(doc, "metadata", {})
                    if not isinstance(meta_dict, dict):
                        meta_dict = {}
                        
                    for k, v in meta_dict.items():
                        if isinstance(v, (str, int, float, bool)):
                            safe_meta[k] = v
                        elif v is not None:
                            safe_meta[k] = str(v)
                    metadatas.append(safe_meta)
                    
            if ids:
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Collection upsert is synchronous, run in thread pool
                        import asyncio
                        await asyncio.to_thread(
                            collection.upsert,
                            ids=ids,
                            embeddings=embeddings,
                            documents=texts,
                            metadatas=metadatas
                        )
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(f"Failed to upsert ChromaDB batch {start_idx} after {max_retries} attempts: {e}")
                            raise
                        import asyncio
                        await asyncio.sleep(2 ** attempt)

        doc_contents = [d.page_content for d in documents]
        result = await processor.process_documents(
            doc_contents,
            on_progress=on_progress,
            on_batch_complete=on_batch_complete
        )
        
        if result["cancelled"]:
            return
            
        # Write parent docstore to Chroma directory for retrieval
        import pickle
        docstore_path = f"{chroma_path}/parent_docstore.pkl"
        with open(docstore_path, "wb") as f:
            pickle.dump(docstore, f)
        logger.info(f"Parent docstore successfully cached to {docstore_path}")
        
        # Transition to validation
        job_service.transition_to_validating(job_id)
        
        # Simple validation
        validation_passed = result["failed_documents"] == 0
        
        # Transition to storing phase (which was primarily done implicitly via streaming)
        job_service.transition_to_storing(job_id)
        
        # --- Optimized Index Tracking: Update per Source Document ---
        # source_documents contains the original parent docs
        for doc in source_documents:
            metadata = doc.metadata if doc.metadata else {}
            if 'checksum' in metadata and 'source_id' in metadata:
                cursor.execute('''
                    INSERT INTO document_index (vector_db_name, source_id, checksum)
                    VALUES (?, ?, ?)
                    ON CONFLICT(vector_db_name, source_id) DO UPDATE SET
                        checksum=excluded.checksum,
                        updated_at=CURRENT_TIMESTAMP
                ''', (vector_db_name, metadata['source_id'], metadata['checksum']))
        conn.commit()
        
        # Update run timestamps in registry
        try:
            cursor.execute(f'''
                UPDATE vector_db_registry 
                SET {"last_incremental_run" if incremental else "last_full_run"} = CURRENT_TIMESTAMP
                WHERE name = ?
            ''', (vector_db_name,))
            conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update run timestamps: {e}")
            
        # Final Summary Logging
        duration = time.time() - start_time
        logger.info(f"EMBEDDING JOB SUMMARY | Job: {job_id} | Namespace: {vector_db_name} | "
                    f"Model: {model_name} | Total Chunks: {len(child_chunks)} | "
                    f"Processed: {result['processed_documents']} | Failed: {result['failed_documents']} | "
                    f"Duration: {duration:.2f}s | Speed: {result['average_speed']:.2f} docs/sec")
        
        conn.close()

        # Complete the job
        job_service.complete_job(job_id, validation_passed=validation_passed)
        
        # Send completion notification
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
        
    except Exception as e:
        logger.error(f"Embedding job {job_id} failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        job_service.fail_job(job_id, str(e))
        
        # Send failure notification
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

def _parallel_delta_worker(doc_batch: List[Document], existing_docs: Dict[str, str]) -> tuple[List[Document], List[str]]:
    """Helper to parallelize checksum calculation and delta selection."""
    processed = []
    stale = []
    
    for doc in doc_batch:
        content = getattr(doc, "page_content", getattr(doc, "content", ""))
        doc_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        if hasattr(doc, "metadata"):
            doc.metadata['checksum'] = doc_hash
        
        # Consistent ID derivation
        if hasattr(doc, "metadata") and "source_id" in doc.metadata:
            # Table-qualified ID for uniqueness
            doc_id = f"{doc.metadata.get('source_table', 'unknown')}_{doc.metadata['source_id']}"
        else:
            # Fallback (rarely used if formatted via create_documents_from_tables)
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
    config_id: Optional[int] = None,
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
        config_id=config_id,
        limit=limit,
        offset=offset
    )
    
    return jobs
