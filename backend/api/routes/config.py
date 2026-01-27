from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from backend.services.config_service import ConfigService, get_config_service
from backend.models.config import PromptGenerationRequest, PromptPublishRequest, PromptResponse
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.logging import get_logger

from backend.core.logging import get_logger
from backend.core.logging import get_logger
from backend.core.permissions import require_role, UserRole, User, get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="/config", tags=["Configuration"])

@router.post("/generate", response_model=Dict[str, Any], dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.EDITOR]))])
async def generate_prompt(
    request: PromptGenerationRequest,
    config_service: ConfigService = Depends(get_config_service)
):
    """
    Generate a draft system prompt based on the provided data dictionary.
    """
    try:
        draft_prompt = config_service.generate_draft_prompt(request.data_dictionary)
        return {"draft_prompt": draft_prompt}
    except Exception as e:
        logger.error(f"Error generating prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate prompt: {str(e)}"
        )

@router.post("/publish", response_model=PromptResponse, dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.EDITOR]))])
async def publish_prompt(
    request: PromptPublishRequest,
    service: ConfigService = Depends(get_config_service)
):
    """
    Publish a new system prompt.
    """
    try:
        result = service.publish_system_prompt(
            request.prompt_text, 
            request.user_id,
            connection_id=request.connection_id,
            schema_selection=request.schema_selection,
            data_dictionary=request.data_dictionary,
            reasoning=request.reasoning,
            example_questions=request.example_questions
        )
        return result
    except Exception as e:
        logger.error(f"Error publishing prompt: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to publish prompt: {str(e)}")

@router.get("/history", response_model=List[PromptResponse])
async def get_prompt_history(
    service: ConfigService = Depends(get_config_service)
):
    """Get all historical versions of the system prompt."""
    try:
        return service.get_prompt_history()
    except Exception as e:
        logger.error(f"Error fetching prompt history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch prompt history: {str(e)}")

@router.get("/active-metadata", response_model=Optional[Dict[str, Any]])
async def get_active_config(
    service: ConfigService = Depends(get_config_service)
):
    """Get the configuration metadata for the active prompt."""
    try:
        return service.get_active_config()
    except Exception as e:
        logger.error(f"Error fetching active config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active", response_model=Dict[str, Optional[str]])
async def get_active_prompt(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get the current active system prompt text.
    """
    try:
        prompt_text = db_service.get_latest_active_prompt()
        return {"prompt_text": prompt_text}
    except Exception as e:
        logger.error(f"Error fetching active prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch active prompt: {str(e)}"
        )
