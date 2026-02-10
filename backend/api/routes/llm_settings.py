"""
LLM Settings API Routes - CRUD endpoints for LLM provider configuration.
Provides REST API for managing LLM providers and validating credentials.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal

from backend.services.llm_registry import get_llm_registry, LLMRegistry
from backend.core.permissions import require_super_admin, require_editor, get_current_user, User
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings/llm", tags=["LLM Settings"])


# ============================================================================
# Request/Response Models
# ============================================================================

class LLMProviderUpdateRequest(BaseModel):
    """Request model for updating LLM provider."""
    provider: Literal["openai", "azure", "anthropic", "ollama", "huggingface", "local"] = Field(
        ..., description="LLM provider type"
    )
    config: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Provider-specific configuration (model_name, temperature, api_key, etc.)"
    )
    reason: Optional[str] = Field(None, description="Reason for the change")


class LLMValidationRequest(BaseModel):
    """Request model for credential validation."""
    provider: Literal["openai", "azure", "anthropic", "ollama", "huggingface", "local"] = Field(
        ..., description="LLM provider type to validate"
    )
    config: Dict[str, Any] = Field(
        ..., description="Configuration to validate (including api_key if required)"
    )


class LLMProviderInfo(BaseModel):
    """Response model for provider information."""
    name: str
    display_name: str
    description: str
    requires_api_key: bool
    requires_endpoint: bool = False
    is_active: bool
    default_config: Dict[str, Any]
    models: List[str]


class LLMCurrentConfig(BaseModel):
    """Response model for current LLM configuration."""
    provider: str
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    api_key_configured: bool = True
    additional_config: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "",
    response_model=Dict[str, Any],
    summary="Get current LLM configuration",
    description="Retrieve the current LLM provider configuration. API keys are masked."
)
async def get_llm_config(
    llm_registry: LLMRegistry = Depends(get_llm_registry),
    current_user: User = Depends(require_editor)
):
    """Get current LLM provider configuration."""
    try:
        config = llm_registry.get_active_config()
        provider_type = llm_registry.get_active_provider_type()
        
        return {
            "provider": provider_type,
            "config": config,
            "is_healthy": llm_registry.health_check().get("healthy", False)
        }
    except Exception as e:
        logger.error(f"Error fetching LLM config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch LLM configuration: {str(e)}"
        )


@router.put(
    "",
    response_model=Dict[str, Any],
    summary="Update LLM provider",
    description="Switch to a different LLM provider or update configuration. Requires Super Admin role."
)
async def update_llm_config(
    request: LLMProviderUpdateRequest,
    llm_registry: LLMRegistry = Depends(get_llm_registry),
    current_user: User = Depends(require_super_admin)
):
    """Update LLM provider configuration (hot-swap)."""
    try:
        result = llm_registry.set_active_provider(
            provider_type=request.provider,
            config=request.config,
            persist=True,
            updated_by=current_user.username
        )
        
        logger.info(f"LLM provider updated to {request.provider} by {current_user.username}")
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating LLM config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update LLM configuration: {str(e)}"
        )


@router.get(
    "/providers",
    response_model=List[Dict[str, Any]],
    summary="List available LLM providers",
    description="Get a list of all available LLM providers with their metadata and supported models."
)
async def list_providers(
    llm_registry: LLMRegistry = Depends(get_llm_registry)
):
    """List all available LLM providers."""
    try:
        return llm_registry.list_providers()
    except Exception as e:
        logger.error(f"Error listing LLM providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list providers: {str(e)}"
        )


@router.post(
    "/validate",
    response_model=Dict[str, Any],
    summary="Validate LLM credentials",
    description="Test LLM provider configuration without saving. Useful for validating API keys."
)
async def validate_llm_config(
    request: LLMValidationRequest,
    llm_registry: LLMRegistry = Depends(get_llm_registry),
    current_user: User = Depends(require_editor)
):
    """Validate LLM provider credentials without activating."""
    try:
        result = llm_registry.test_provider(
            provider_type=request.provider,
            config=request.config
        )
        
        if result["success"]:
            logger.info(f"LLM validation successful for {request.provider}")
        else:
            logger.warning(f"LLM validation failed for {request.provider}: {result.get('error')}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error validating LLM config: {e}")
        return {
            "success": False,
            "provider": request.provider,
            "error": str(e)
        }


@router.get(
    "/health",
    response_model=Dict[str, Any],
    summary="Check LLM health",
    description="Perform a health check on the currently active LLM provider."
)
async def check_llm_health(
    llm_registry: LLMRegistry = Depends(get_llm_registry),
    current_user: User = Depends(require_editor)
):
    """Check health of active LLM provider."""
    try:
        return llm_registry.health_check()
    except Exception as e:
        logger.error(f"Error checking LLM health: {e}")
        return {
            "healthy": False,
            "error": str(e)
        }
