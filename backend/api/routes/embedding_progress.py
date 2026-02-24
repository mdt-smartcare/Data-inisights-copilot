"""
API routes for embedding job management and progress tracking.
Requires SuperAdmin role for all operations.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
import json

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
        from backend.sqliteDb.db import get_db_service
        db_service = get_db_service()
        config = db_service.get_config_by_id(request.config_id)
        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration {request.config_id} not found")
            
        import json
        emb_conf = json.loads(config.get('embedding_config', '{}') or '{}')
        vector_db_name = emb_conf.get('vectorDbName')
        
        # Robust naming fallback for multi-tenant isolation
        if not vector_db_name:
            agent_id = config.get('agent_id')
            conn_id = config.get('connection_id')
            if agent_id:
                vector_db_name = f"agent_{agent_id}_data"
            elif conn_id:
                vector_db_name = f"db_connection_{conn_id}_data"
            else:
                vector_db_name = "default_vector_db"
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
        # Start the job
        job_service.start_job(job_id)
        
        # 1. Fetch Configuration
        config = db_service.get_config_by_id(config_id)
        if not config:
            raise ValueError(f"Configuration {config_id} not found")
            
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
                
        else:
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
            
            # 5. Transform for Document Generator
            generator_schema = {'tables': {}}
            for table, cols in schema_info.get('details', {}).items():
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
            
        # Get Vector DB Name with multi-tenant awareness
        vector_db_name = "default_vector_db"
        try:
            emb_conf = json.loads(config.get('embedding_config', '{}') or '{}')
            if emb_conf and emb_conf.get('vectorDbName'):
                vector_db_name = emb_conf['vectorDbName']
            else:
                # Fallback matching the start endpoint logic
                agent_id = config.get('agent_id')
                conn_id = config.get('connection_id')
                if agent_id:
                    vector_db_name = f"agent_{agent_id}_data"
                elif conn_id:
                    vector_db_name = f"db_connection_{conn_id}_data"
        except Exception as e:
            logger.warning(f"Failed to parse embedding config: {e}")

        # Incremental Filtering
        import hashlib
        import os
        import chromadb
        from chromadb.config import Settings
        
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../../data/indexes/{vector_db_name}"))
        
        if not incremental:
            # Rebuild: wipe index and chroma
            cursor.execute("DELETE FROM document_index WHERE vector_db_name = ?", (vector_db_name,))
            conn.commit()
            
            import shutil
            if os.path.exists(chroma_path):
                shutil.rmtree(chroma_path)
                
            docs_to_process = documents
            stale_source_ids = []
            logger.info(f"Rebuild mode: Wiped existing database and Chroma indexing for {vector_db_name}")
        else:
            cursor.execute("SELECT source_id, checksum FROM document_index WHERE vector_db_name = ?", (vector_db_name,))
            existing_docs = {row['source_id']: row['checksum'] for row in cursor.fetchall()}
            
            docs_to_process = []
            stale_source_ids = []
            
            for doc in documents:
                doc_hash = hashlib.md5(doc.content.encode('utf-8')).hexdigest()
                doc.metadata['checksum'] = doc_hash
                
                if doc.document_id in existing_docs:
                    if existing_docs[doc.document_id] != doc_hash:
                        stale_source_ids.append(doc.document_id)
                        docs_to_process.append(doc)
                else:
                    docs_to_process.append(doc)
            
            if len(docs_to_process) == 0:
                logger.info(f"Incremental run: 0 new/modified documents out of {len(documents)}. Skipping embedding.")
                job_service.complete_job(job_id, validation_passed=True)
                return

            if stale_source_ids and os.path.exists(chroma_path):
                # Delete old chunks for updated documents
                try:
                    client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
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

            
        # Apply chunking
        chunk_size = 800
        chunk_overlap = 150
        try:
            chunking_conf = json.loads(config.get('chunking_config', '{}') or '{}')
            if chunking_conf:
                chunk_size = chunking_conf.get('parentChunkSize', 800)
                chunk_overlap = chunking_conf.get('parentChunkOverlap', 150)
        except Exception as e:
            logger.warning(f"Failed to parse chunking config: {e}")

        from langchain_text_splitters import RecursiveCharacterTextSplitter
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        chunked_documents = []
        for doc in documents:
            chunks = text_splitter.split_text(doc.content)
            for i, chunk_text in enumerate(chunks):
                from backend.services.embedding_document_generator import EmbeddingDocument
                meta = dict(doc.metadata) if doc.metadata else {}
                meta["chunk_index"] = i
                meta["source_id"] = doc.document_id
                
                chunked_documents.append(EmbeddingDocument(
                    document_id=f"{doc.document_id}-chunk-{i}",
                    document_type=getattr(doc, 'document_type', 'file'),
                    content=chunk_text,
                    metadata=meta
                ))

        documents = chunked_documents
            
        # Update job with accurate document count
        total_docs = len(documents)
        job_service._update_job(job_id, total_documents=total_docs)
        
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
        
        # Store actual vectors to vector database
        os.makedirs(chroma_path, exist_ok=True)
        
        ids = []
        texts = []
        embeddings = []
        metadatas = []
        
        for i, (doc, emb) in enumerate(zip(documents, result["embeddings"])):
            if emb is not None:
                ids.append(doc.document_id)
                texts.append(doc.content)
                embeddings.append(emb)
                
                # Sanitize metadata
                safe_meta = {}
                for k, v in doc.metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        safe_meta[k] = v
                    elif v is None:
                        continue
                    else:
                        safe_meta[k] = str(v)
                metadatas.append(safe_meta)
                
        if ids:
            client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
            collection = client.get_or_create_collection(name=vector_db_name)
            
            # Batch upsert to Chroma (max batch size ~5000, using 1000 to be safe)
            batch_size = 1000
            for i in range(0, len(ids), batch_size):
                collection.upsert(
                    ids=ids[i:i+batch_size],
                    embeddings=embeddings[i:i+batch_size],
                    documents=texts[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
        
        # Update SQLite document_index
        for doc in documents: # documents is now docks_to_process
            if 'checksum' in doc.metadata:
                cursor.execute('''
                    INSERT INTO document_index (vector_db_name, source_id, checksum)
                    VALUES (?, ?, ?)
                    ON CONFLICT(vector_db_name, source_id) DO UPDATE SET
                        checksum=excluded.checksum,
                        updated_at=CURRENT_TIMESTAMP
                ''', (vector_db_name, doc.document_id, doc.metadata['checksum']))
        conn.commit()
        conn.close()

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
