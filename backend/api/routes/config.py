from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from backend.services.config_service import ConfigService, get_config_service
from backend.models.config import PromptGenerationRequest, PromptPublishRequest, PromptResponse
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.logging import get_logger
from backend.core.permissions import require_editor, require_super_admin, get_current_user, User
from backend.services.sql_service import get_sql_service

logger = get_logger(__name__)

router = APIRouter(prefix="/config", tags=["Configuration"])

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
        result = config_service.generate_draft_prompt(request.data_dictionary)
        return result  # Already returns {"draft_prompt": ..., "reasoning": ..., "example_questions": ...}
    except Exception as e:
        logger.error(f"Error generating prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate prompt: {str(e)}"
        )

@router.post("/publish", response_model=PromptResponse, dependencies=[Depends(require_super_admin)])
async def publish_prompt(
    request: PromptPublishRequest,
    service: ConfigService = Depends(get_config_service)
):
    """
    Publish a new system prompt.
    Requires Super Admin role.
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
            agent_id=request.agent_id
        )
        
        # Reinitialize SQL service to use the new connection if changed
        # TODO: Handle multi-agent SQL service reinitialization properly
        # For now, this might only affect the default/global service
        if request.connection_id:
            logger.info(f"Config published with connection_id={request.connection_id}, reinitializing SQL service")
            try:
                sql_service = get_sql_service()
                sql_service.reinitialize()
                logger.info("SQL service reinitialized with new database connection")
            except Exception as e:
                logger.warning(f"Failed to reinitialize SQL service: {e}. Will use new connection on next restart.")
        
        return result
    except Exception as e:
        logger.error(f"Error publishing prompt: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to publish prompt: {str(e)}")

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


@router.post("/rollback/{version_id}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def rollback_to_version(
    version_id: int,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Rollback to a previous prompt version by making it the active version.
    Requires Super Admin role.
    """
    from backend.services.audit_service import get_audit_service, AuditAction
    
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # Get the version to rollback to
        cursor.execute("SELECT id, version, prompt_text FROM system_prompts WHERE id = ?", (version_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Version not found")
        
        prompt_id, version_num, prompt_text = row
        
        # Deactivate all existing prompts
        cursor.execute("UPDATE system_prompts SET is_active = 0")
        
        # Activate the selected version
        cursor.execute("UPDATE system_prompts SET is_active = 1 WHERE id = ?", (version_id,))
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
            details={"rolled_back_to_version": version_num}
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

