from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict

from backend.services.config_service import ConfigService, get_config_service
from backend.models.config import PromptGenerationRequest, PromptPublishRequest, PromptResponse
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/config", tags=["Configuration"])

@router.post("/generate", response_model=Dict[str, str])
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

@router.post("/publish", response_model=Dict[str, Any])
async def publish_prompt(
    request: PromptPublishRequest,
    config_service: ConfigService = Depends(get_config_service)
):
    """
    Publish a new system prompt.
    """
    try:
        version = config_service.publish_prompt(request.prompt_text, request.user_id)
        return {"status": "success", "version": version}
    except Exception as e:
        logger.error(f"Error publishing prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish prompt: {str(e)}"
        )

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
