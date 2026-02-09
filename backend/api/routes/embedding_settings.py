"""
Embedding Settings API - Endpoints for managing embedding provider configuration.
Provides REST API for switching providers, testing connections, and health checks.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from backend.core.permissions import require_super_admin, get_current_user
from backend.models.schemas import User
from backend.services.embedding_registry import get_embedding_registry, EmbeddingRegistry
from backend.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/settings/embedding", tags=["Embedding Settings"])


# =============================================================================
# Request/Response Models
# =============================================================================

class EmbeddingProviderConfig(BaseModel):
    """Configuration for an embedding provider."""
    provider: str = Field(..., description="Provider type: bge-m3, openai, sentence-transformers")
    model_name: Optional[str] = Field(None, description="Model name or path")
    model_path: Optional[str] = Field(None, description="Local model path (for bge-m3)")
    batch_size: Optional[int] = Field(128, ge=1, le=1024, description="Batch size for embedding")
    api_key: Optional[str] = Field(None, description="API key for cloud providers")


class ProviderTestRequest(BaseModel):
    """Request to test a provider configuration."""
    provider: str = Field(..., description="Provider type to test")
    config: Optional[Dict[str, Any]] = Field(None, description="Provider-specific config")


class ProviderInfo(BaseModel):
    """Information about an available provider."""
    name: str
    display_name: str
    description: str
    requires_api_key: bool
    is_active: bool
    default_config: Dict[str, Any]


class HealthResponse(BaseModel):
    """Health check response."""
    healthy: bool
    provider: str
    dimension: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class SwitchProviderResponse(BaseModel):
    """Response after switching providers."""
    success: bool
    provider: str
    config: Dict[str, Any]
    requires_reindex: bool
    message: str


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    summary="Get current embedding configuration",
    description="Returns the active embedding provider configuration and status."
)
async def get_embedding_config(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current embedding provider configuration."""
    registry = get_embedding_registry()
    
    return {
        "active_provider": registry.get_active_provider_type(),
        "config": registry.get_active_config(),
        "dimension": registry.get_active_provider().dimension
    }


@router.get(
    "/providers",
    response_model=List[ProviderInfo],
    summary="List available embedding providers",
    description="Returns all available embedding providers with their metadata."
)
async def list_providers(
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """List all available embedding providers."""
    registry = get_embedding_registry()
    return registry.list_providers()


@router.put(
    "",
    response_model=SwitchProviderResponse,
    summary="Switch embedding provider",
    description="Switch to a different embedding provider. Requires super admin role."
)
async def update_embedding_config(
    config: EmbeddingProviderConfig,
    current_user: User = Depends(require_super_admin)
) -> SwitchProviderResponse:
    """
    Switch the active embedding provider (hot-swap).
    
    Note: Switching providers may require reindexing your vector store
    if the new provider has different dimensions or embeddings.
    """
    registry = get_embedding_registry()
    
    # Validate provider
    available = [p["name"] for p in registry.list_providers()]
    if config.provider not in available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider: {config.provider}. Available: {available}"
        )
    
    # Build provider config
    provider_config = {}
    if config.model_name:
        provider_config["model_name"] = config.model_name
    if config.model_path:
        provider_config["model_path"] = config.model_path
    if config.batch_size:
        provider_config["batch_size"] = config.batch_size
    if config.api_key:
        provider_config["api_key"] = config.api_key
    
    try:
        result = registry.set_active_provider(
            config.provider,
            provider_config,
            persist=True
        )
        
        logger.info(f"Embedding provider switched to {config.provider} by {current_user.username}")
        
        return SwitchProviderResponse(
            success=True,
            provider=config.provider,
            config=result["config"],
            requires_reindex=result.get("requires_reindex", True),
            message=f"Successfully switched to {config.provider}"
        )
        
    except Exception as e:
        logger.error(f"Failed to switch provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to switch provider: {str(e)}"
        )


@router.post(
    "/test",
    summary="Test a provider configuration",
    description="Test a provider configuration without activating it."
)
async def test_provider(
    request: ProviderTestRequest,
    current_user: User = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Test a provider configuration before switching to it.
    
    This allows you to validate API keys and connectivity before
    making a change that could affect the system.
    """
    registry = get_embedding_registry()
    
    try:
        result = registry.test_provider(request.provider, request.config)
        return result
        
    except Exception as e:
        logger.error(f"Provider test failed: {e}")
        return {
            "success": False,
            "provider": request.provider,
            "error": str(e)
        }


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Get embedding provider health",
    description="Perform a health check on the active embedding provider."
)
async def get_health(
    current_user: User = Depends(get_current_user)
) -> HealthResponse:
    """Check health of the active embedding provider."""
    registry = get_embedding_registry()
    health = registry.health_check()
    
    return HealthResponse(
        healthy=health.get("healthy", False),
        provider=health.get("provider", "unknown"),
        dimension=health.get("dimension"),
        latency_ms=health.get("latency_ms"),
        error=health.get("error")
    )


@router.post(
    "/reindex",
    summary="Trigger vector store reindex",
    description="Trigger a full reindex of the vector store with the current embedding provider."
)
async def trigger_reindex(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Trigger a full reindex of the vector store.
    
    This is typically needed after switching embedding providers,
    as different providers produce different embedding dimensions.
    
    The reindex runs as a background task.
    """
    # This would integrate with the existing embedding job service
    # For now, return a placeholder response
    logger.info(f"Reindex triggered by {current_user.username}")
    
    # TODO: Integrate with embedding_job_service to trigger reindex
    # For now, return guidance
    return {
        "status": "pending",
        "message": "Reindex requested. Use the existing RAG reindex API to trigger the full reindex process.",
        "guidance": "POST /api/v1/config/reindex to trigger embedding job"
    }
