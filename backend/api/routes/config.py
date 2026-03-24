from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

from backend.services.config_service import ConfigService, get_config_service
from backend.models.config import PromptGenerationRequest, PromptPublishRequest, PromptResponse
from backend.database.db import get_db_service, DatabaseService
from backend.core.logging import get_logger
from backend.core.permissions import require_editor, require_admin, get_current_user, User
from backend.services.sql_service import get_sql_service

logger = get_logger(__name__)

router = APIRouter(prefix="/config", tags=["Configuration"])


# ============================================================================
# Request/Response Models for Operational Config
# ============================================================================

class ChunkingConfigUpdate(BaseModel):
    """Request model for updating chunking configuration."""
    parent_chunk_size: Optional[int] = Field(None, ge=100, le=4000, description="Parent chunk size")
    parent_chunk_overlap: Optional[int] = Field(None, ge=0, le=500, description="Parent chunk overlap")
    child_chunk_size: Optional[int] = Field(None, ge=50, le=1000, description="Child chunk size")
    child_chunk_overlap: Optional[int] = Field(None, ge=0, le=200, description="Child chunk overlap")
    min_chunk_length: Optional[int] = Field(None, ge=10, le=500, description="Minimum chunk length")
    reason: Optional[str] = Field(None, description="Reason for the change")


class PIIConfigUpdate(BaseModel):
    """Request model for updating PII/data privacy configuration."""
    global_exclude_columns: Optional[List[str]] = Field(None, description="Columns to exclude globally")
    exclude_tables: Optional[List[str]] = Field(None, description="Tables to exclude entirely")
    table_specific_exclusions: Optional[Dict[str, List[str]]] = Field(None, description="Table-specific exclusions")
    reason: Optional[str] = Field(None, description="Reason for the change")


class MedicalContextUpdate(BaseModel):
    """Request model for updating medical context configuration."""
    terminology_mappings: Optional[Dict[str, str]] = Field(None, description="Medical terminology mappings")
    clinical_flag_prefixes: Optional[List[str]] = Field(None, description="Clinical flag prefixes")
    reason: Optional[str] = Field(None, description="Reason for the change")


class VectorStoreConfigUpdate(BaseModel):
    """Request model for updating vector store configuration."""
    type: Optional[str] = Field(None, description="Vector store type")
    default_collection: Optional[str] = Field(None, description="Default collection name")
    chroma_base_path: Optional[str] = Field(None, description="ChromaDB base path")
    reason: Optional[str] = Field(None, description="Reason for the change")


class RAGConfigUpdate(BaseModel):
    """Request model for updating RAG pipeline configuration."""
    top_k_initial: Optional[int] = Field(None, ge=1, le=500, description="Initial documents to fetch")
    top_k_final: Optional[int] = Field(None, ge=1, le=100, description="Final documents after reranking")
    hybrid_weights: Optional[List[float]] = Field(None, description="Weights for hybrid search")
    rerank_enabled: Optional[bool] = Field(None, description="Enable reranking")
    reranker_model: Optional[str] = Field(None, description="Reranker model name")
    chunk_size: Optional[int] = Field(None, ge=100, le=4000, description="Chunk size")
    chunk_overlap: Optional[int] = Field(None, ge=0, le=500, description="Chunk overlap")
    reason: Optional[str] = Field(None, description="Reason for the change")


class ConfigUpdateResponse(BaseModel):
    """Response model for config updates."""
    status: str = "success"
    category: str
    updated_settings: Dict[str, Any]
    message: str


# ============================================================================
# Operational Configuration Endpoints (Hot-Reload Enabled)
# ============================================================================

@router.get("/chunking", response_model=Dict[str, Any])
async def get_chunking_config(
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_editor)
):
    """
    Get current chunking configuration.
    
    Returns chunking parameters used by the embedding pipeline.
    """
    try:
        return config_service.get_chunking_params()
    except Exception as e:
        logger.error(f"Error fetching chunking config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch chunking config: {str(e)}"
        )


@router.put("/chunking", response_model=ConfigUpdateResponse)
async def update_chunking_config(
    request: ChunkingConfigUpdate,
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_admin)
):
    """
    Update chunking configuration.
    
    HOT-RELOAD: Changes take effect immediately for the next ingestion job.
    No server restart required.
    
    Requires Super Admin role.
    """
    try:
        # Build settings dict from non-None values
        settings = {k: v for k, v in request.model_dump().items() 
                   if v is not None and k != 'reason'}
        
        if not settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No settings provided to update"
            )
        
        updated = config_service.update_chunking_params(
            settings, 
            updated_by=current_user.username,
            reason=request.reason
        )
        
        logger.info(f"Chunking config updated by {current_user.username}: {list(settings.keys())}")
        
        return ConfigUpdateResponse(
            category="chunking",
            updated_settings=updated,
            message="Chunking configuration updated. Changes will apply to next ingestion job."
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating chunking config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update chunking config: {str(e)}"
        )


@router.get("/pii", response_model=Dict[str, Any])
async def get_pii_config(
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_editor)
):
    """
    Get current PII/data privacy configuration.
    
    Returns PII protection rules used during data extraction.
    """
    try:
        return config_service.get_pii_rules()
    except Exception as e:
        logger.error(f"Error fetching PII config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch PII config: {str(e)}"
        )


@router.put("/pii", response_model=ConfigUpdateResponse)
async def update_pii_config(
    request: PIIConfigUpdate,
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_admin)
):
    """
    Update PII/data privacy configuration.
    
    HOT-RELOAD: Changes take effect immediately for the next ingestion job.
    No server restart required.
    
    Requires Super Admin role.
    """
    try:
        settings = {k: v for k, v in request.model_dump().items() 
                   if v is not None and k != 'reason'}
        
        if not settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No settings provided to update"
            )
        
        updated = config_service.update_pii_rules(
            settings, 
            updated_by=current_user.username,
            reason=request.reason
        )
        
        logger.info(f"PII config updated by {current_user.username}: {list(settings.keys())}")
        
        return ConfigUpdateResponse(
            category="data_privacy",
            updated_settings=updated,
            message="PII protection rules updated. Changes will apply to next ingestion job."
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating PII config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update PII config: {str(e)}"
        )


@router.get("/medical-context", response_model=Dict[str, Any])
async def get_medical_context_config(
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_editor)
):
    """
    Get current medical context configuration.
    
    Returns medical terminology mappings and clinical flag prefixes.
    """
    try:
        return config_service.get_medical_context()
    except Exception as e:
        logger.error(f"Error fetching medical context config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch medical context config: {str(e)}"
        )


@router.put("/medical-context", response_model=ConfigUpdateResponse)
async def update_medical_context_config(
    request: MedicalContextUpdate,
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_admin)
):
    """
    Update medical context configuration.
    
    HOT-RELOAD: Changes take effect immediately for the next ingestion job.
    No server restart required.
    
    Requires Super Admin role.
    """
    try:
        settings = {k: v for k, v in request.model_dump().items() 
                   if v is not None and k != 'reason'}
        
        if not settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No settings provided to update"
            )
        
        updated = config_service.update_medical_context(
            settings, 
            updated_by=current_user.username,
            reason=request.reason
        )
        
        logger.info(f"Medical context config updated by {current_user.username}: {list(settings.keys())}")
        
        return ConfigUpdateResponse(
            category="medical_context",
            updated_settings=updated,
            message="Medical context configuration updated. Changes will apply to next ingestion job."
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating medical context config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update medical context config: {str(e)}"
        )


@router.get("/vector-store", response_model=Dict[str, Any])
async def get_vector_store_config(
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_editor)
):
    """
    Get current vector store configuration.
    
    Returns vector store settings (type, collection, paths).
    """
    try:
        return config_service.get_vector_store_config()
    except Exception as e:
        logger.error(f"Error fetching vector store config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch vector store config: {str(e)}"
        )


@router.put("/vector-store", response_model=ConfigUpdateResponse)
async def update_vector_store_config(
    request: VectorStoreConfigUpdate,
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_admin)
):
    """
    Update vector store configuration.
    
    HOT-RELOAD: Changes take effect immediately for the next ingestion job.
    No server restart required.
    
    Requires Super Admin role.
    """
    try:
        settings = {k: v for k, v in request.model_dump().items() 
                   if v is not None and k != 'reason'}
        
        if not settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No settings provided to update"
            )
        
        updated = config_service.update_vector_store_config(
            settings, 
            updated_by=current_user.username,
            reason=request.reason
        )
        
        logger.info(f"Vector store config updated by {current_user.username}: {list(settings.keys())}")
        
        return ConfigUpdateResponse(
            category="vector_store",
            updated_settings=updated,
            message="Vector store configuration updated. Changes will apply to next ingestion job."
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating vector store config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update vector store config: {str(e)}"
        )


@router.get("/rag", response_model=Dict[str, Any])
async def get_rag_config(
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_editor)
):
    """
    Get current RAG pipeline configuration.
    
    Returns retrieval and reranking settings.
    """
    try:
        return config_service.get_rag_config()
    except Exception as e:
        logger.error(f"Error fetching RAG config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch RAG config: {str(e)}"
        )


@router.put("/rag", response_model=ConfigUpdateResponse)
async def update_rag_config(
    request: RAGConfigUpdate,
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_admin)
):
    """
    Update RAG pipeline configuration.
    
    HOT-RELOAD: Changes take effect immediately for new queries.
    No server restart required.
    
    Requires Super Admin role.
    """
    from backend.services.settings_service import get_settings_service
    
    try:
        settings = {k: v for k, v in request.model_dump().items() 
                   if v is not None and k != 'reason'}
        
        if not settings:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No settings provided to update"
            )
        
        # Use settings service directly for RAG category
        settings_service = get_settings_service()
        updated = settings_service.update_category_settings(
            'rag', 
            settings, 
            updated_by=current_user.username,
            change_reason=request.reason
        )
        
        logger.info(f"RAG config updated by {current_user.username}: {list(settings.keys())}")
        
        return ConfigUpdateResponse(
            category="rag",
            updated_settings=updated,
            message="RAG pipeline configuration updated. Changes will apply immediately."
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating RAG config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update RAG config: {str(e)}"
        )


@router.get("/pipeline", response_model=Dict[str, Any])
async def get_full_pipeline_config(
    config_service: ConfigService = Depends(get_config_service),
    current_user: User = Depends(require_editor)
):
    """
    Get complete embedding pipeline configuration.
    
    Returns all operational settings combined into a single response.
    Useful for viewing all configuration at once.
    """
    try:
        return config_service.get_full_embedding_pipeline_config()
    except Exception as e:
        logger.error(f"Error fetching pipeline config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch pipeline config: {str(e)}"
        )


@router.post("/invalidate-cache", response_model=Dict[str, str])
async def invalidate_config_cache(
    current_user: User = Depends(require_admin)
):
    """
    Force invalidate all configuration caches.
    
    This triggers an immediate cache refresh across all services.
    Useful for debugging or when you need changes to take effect immediately.
    
    Requires Super Admin role.
    """
    from backend.services.settings_service import get_settings_service
    
    try:
        # Invalidate settings service cache
        settings_service = get_settings_service()
        settings_service._invalidate_cache()
        
        logger.info(f"Configuration cache invalidated by {current_user.username}")
        
        return {
            "status": "success",
            "message": "All configuration caches invalidated. New values will be loaded on next access."
        }
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invalidate cache: {str(e)}"
        )


# ============================================================================
# Existing Endpoints (System Prompt Management)
# ============================================================================

@router.post("/generate", response_model=Dict[str, Any], dependencies=[Depends(require_editor)])
async def generate_prompt(
    request: PromptGenerationRequest,
    config_service: ConfigService = Depends(get_config_service)
):
    """
    Generate a draft system prompt based on the provided data dictionary.
    Requires Editor role or above.
    """
    try:
        result = config_service.generate_draft_prompt(
            request.data_dictionary, 
            data_source_type=request.data_source_type
        )
        return result  # Already returns {"draft_prompt": ..., "reasoning": ..., "example_questions": ...}
    except Exception as e:
        logger.error(f"Error generating prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate prompt: {str(e)}"
        )

@router.post("/publish", response_model=PromptResponse, dependencies=[Depends(require_admin)])
async def publish_prompt(
    request: PromptPublishRequest,
    service: ConfigService = Depends(get_config_service)
):
    """
    Publish a new system prompt.
    Requires Admin role or above.
    """
    try:
        result = service.publish_system_prompt(
            request.prompt_text, 
            request.user_id,
            connection_id=request.connection_id,
            schema_selection=request.schema_selection,
            data_dictionary=request.data_dictionary,
            reasoning=request.reasoning,
            example_questions=request.example_questions,
            embedding_config=request.embedding_config,
            retriever_config=request.retriever_config,
            chunking_config=request.chunking_config,
            llm_config=request.llm_config,
            agent_id=request.agent_id,
            data_source_type=request.data_source_type,
            ingestion_documents=request.ingestion_documents,
            ingestion_file_name=request.ingestion_file_name,
            ingestion_file_type=request.ingestion_file_type
        )
        
        # Reinitialize SQL service to use the new connection if changed
        # TODO: Handle multi-agent SQL service reinitialization properly
        # For now, this might only affect the default/global service
        if request.data_source_type == 'database' and request.connection_id:
            logger.info(f"Config published with connection_id={request.connection_id}, reinitializing SQL service")
            try:
                sql_service = get_sql_service()
                sql_service.reinitialize()
                logger.info("SQL service reinitialized with new database connection")
            except Exception as e:
                logger.warning(f"Failed to reinitialize SQL service: {e}. Will use new connection on next restart.")
        
        return result
    except Exception as e:
        logger.error(f"Error publishing prompt: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to publish prompt: {str(e)}"
        )

@router.get("/history", response_model=List[PromptResponse])
async def get_prompt_history(
    agent_id: Optional[int] = None,
    service: ConfigService = Depends(get_config_service)
):
    """Get all historical versions of the system prompt."""
    try:
        return service.get_prompt_history(agent_id=agent_id)
    except Exception as e:
        logger.error(f"Error fetching prompt history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch prompt history: {str(e)}")

@router.get("/active-metadata", response_model=Optional[Dict[str, Any]])
async def get_active_config(
    agent_id: Optional[int] = None,
    service: ConfigService = Depends(get_config_service)
):
    """Get the configuration metadata for the active prompt."""
    try:
        return service.get_active_config(agent_id=agent_id)
    except Exception as e:
        logger.error(f"Error fetching active config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active", response_model=Dict[str, Optional[str]])
async def get_active_prompt(
    agent_id: Optional[int] = None,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get the current active system prompt text.
    """
    try:
        prompt_text = db_service.get_latest_active_prompt(agent_id=agent_id)
        return {"prompt_text": prompt_text}
    except Exception as e:
        logger.error(f"Error fetching active prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch active prompt: {str(e)}"
        )


@router.post("/rollback/{version_id}", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def rollback_to_version(
    version_id: int,
    current_user: User = Depends(require_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Rollback to a previous prompt version by making it the active version.
    Requires Admin role or above.
    """
    from backend.services.audit_service import get_audit_service, AuditAction
    
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # Get the version to rollback to
        cursor.execute("SELECT id, version, prompt_text, agent_id FROM system_prompts WHERE id = %s", (version_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Version not found")
        
        prompt_id, version_num, prompt_text, agent_id = row
        
        # Deactivate all existing prompts for THIS AGENT (or global if agent_id is None)
        if agent_id:
            cursor.execute("UPDATE system_prompts SET is_active = 0 WHERE agent_id = %s", (agent_id,))
        else:
            cursor.execute("UPDATE system_prompts SET is_active = 0 WHERE agent_id IS NULL")
        
        # Activate the selected version
        cursor.execute("UPDATE system_prompts SET is_active = 1 WHERE id = %s", (version_id,))
        conn.commit()
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.PROMPT_ROLLBACK,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="prompt",
            resource_id=str(version_id),
            resource_name=f"v{version_num}",
            details={"rolled_back_to_version": version_num, "agent_id": agent_id}
        )
        
        logger.info(f"User {current_user.username} rolled back to prompt version {version_num}")
        
        return {
            "status": "success",
            "message": f"Rolled back to version {version_num}",
            "version_id": version_id,
            "version": version_num
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back to version {version_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback: {str(e)}"
        )

