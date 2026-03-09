"""
Embedding Settings API - Endpoints for managing embedding provider configuration.
Provides REST API for switching providers, testing connections, health checks,
and DB-backed model registry operations (list, register, activate).

ENHANCED with Model Catalog endpoints for curated model selection.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

from backend.core.permissions import require_admin, require_editor, get_current_user
from backend.models.schemas import User
from backend.services.embedding_registry import get_embedding_registry, EmbeddingRegistry
from backend.services.model_registry_service import (
    get_model_registry_service, ModelRegistryService,
    EmbeddingModelCreate, ModelActivationResult,
)
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
    models: List[str] = []


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


class AddFromCatalogRequest(BaseModel):
    """Request to add a model from the curated catalog."""
    model_name: str = Field(..., description="Model name from catalog (e.g., BAAI/bge-base-en-v1.5)")


class ModelActivationResponse(BaseModel):
    """Response after activating a model with rebuild warnings."""
    model: Dict[str, Any]
    dimension_changed: bool
    previous_dimensions: Optional[int]
    new_dimensions: int
    requires_rebuild: bool
    rebuild_warning: Optional[str]
    system_settings_updated: bool


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
    description="Switch to a different embedding provider. Requires Admin role or above."
)
async def update_embedding_config(
    config: EmbeddingProviderConfig,
    current_user: User = Depends(require_admin)
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
            persist=True,
            updated_by=current_user.username
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
    current_user: User = Depends(require_admin)
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
    current_user: User = Depends(require_admin)
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


# =============================================================================
# Model Catalog Endpoints (NEW)
# =============================================================================

@router.get(
    "/catalog",
    response_model=List[Dict[str, Any]],
    summary="Get curated model catalog",
    description="Returns the curated catalog of pre-validated embedding models with specifications."
)
async def get_model_catalog(
    category: Optional[str] = Query(None, description="Filter by category: general, multilingual, fast, medical"),
    local_only: bool = Query(False, description="Only return models that run locally (no API key required)"),
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get the curated model catalog with filtering options.
    
    Each model entry includes:
    - dimensions, max_tokens, provider
    - speed_rating (1-5, 5 fastest)
    - quality_rating (1-5, 5 best)
    - description and use case recommendations
    - is_registered: whether already in your registry
    """
    try:
        return model_registry.get_model_catalog(category=category, local_only=local_only)
    except Exception as e:
        logger.error(f"Error fetching model catalog: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch model catalog: {str(e)}"
        )


@router.post(
    "/catalog/add",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Add model from catalog",
    description="Add a pre-validated model from the curated catalog to your registry."
)
async def add_model_from_catalog(
    request: AddFromCatalogRequest,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """
    Add a model from the curated catalog to your registry.
    
    This ensures correct dimensions and settings are used automatically.
    The model will be added but not activated - use the activate endpoint to switch to it.
    """
    try:
        result = model_registry.add_model_from_catalog(
            model_name=request.model_name,
            created_by=current_user.username
        )
        logger.info(f"Catalog model '{request.model_name}' added by {current_user.username}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding model from catalog: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add model from catalog: {str(e)}"
        )


@router.get(
    "/catalog/{model_name:path}/validate",
    summary="Validate model availability",
    description="Check if a model can be loaded (for local models) or if API key is configured (for cloud models)."
)
async def validate_model(
    model_name: str,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Validate that a model can be used.
    
    For local models: checks if model files exist or can be downloaded
    For API models: checks if required API key is configured
    """
    try:
        is_available, message = model_registry.validate_model_availability(model_name)
        return {
            "model_name": model_name,
            "available": is_available,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error validating model: {e}")
        return {
            "model_name": model_name,
            "available": False,
            "message": f"Validation error: {str(e)}"
        }


# =============================================================================
# Model Registry Endpoints (DB-backed) - ENHANCED
# =============================================================================

@router.get(
    "/models",
    response_model=List[Dict[str, Any]],
    summary="List registered embedding models",
    description="List all embedding models from the model registry (built-in + custom)."
)
async def list_embedding_models(
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_editor)
):
    """List all registered embedding models from the DB."""
    try:
        return model_registry.list_embedding_models()
    except Exception as e:
        logger.error(f"Error listing embedding models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list embedding models: {str(e)}"
        )


@router.post(
    "/models",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Register a custom embedding model",
    description="Add a new custom embedding model to the registry. Requires Admin role or above."
)
async def register_embedding_model(
    data: EmbeddingModelCreate,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_admin)
):
    """Register a new custom embedding model."""
    try:
        result = model_registry.add_embedding_model(data, created_by=current_user.username)
        logger.info(f"Embedding model '{data.model_name}' registered by {current_user.username}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering embedding model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register embedding model: {str(e)}"
        )


@router.put(
    "/models/{model_id}/activate",
    response_model=ModelActivationResponse,
    summary="Activate an embedding model",
    description="Set a registered embedding model as active. Returns rebuild warnings if dimensions change."
)
async def activate_embedding_model(
    model_id: int,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_admin)
) -> ModelActivationResponse:
    """
    Activate a registered embedding model by ID.
    
    ENHANCED: Now returns detailed information about:
    - Whether dimensions changed (requires vector DB rebuild)
    - Previous vs new dimensions
    - Warning message if rebuild is required
    - Whether system_settings was updated
    """
    try:
        result = model_registry.activate_embedding_model(model_id, updated_by=current_user.username)
        logger.info(f"Embedding model {model_id} activated by {current_user.username}")
        
        # Log rebuild warning prominently
        if result.requires_rebuild:
            logger.warning(f"REBUILD REQUIRED: {result.rebuild_warning}")
        
        return ModelActivationResponse(
            model=result.model,
            dimension_changed=result.dimension_changed,
            previous_dimensions=result.previous_dimensions,
            new_dimensions=result.new_dimensions,
            requires_rebuild=result.requires_rebuild,
            rebuild_warning=result.rebuild_warning,
            system_settings_updated=result.system_settings_updated,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error activating embedding model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate embedding model: {str(e)}"
        )


@router.get(
    "/models/active",
    response_model=Dict[str, Any],
    summary="Get active embedding model",
    description="Get the currently active embedding model with full details."
)
async def get_active_model(
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get the currently active embedding model."""
    try:
        model = model_registry.get_active_embedding_model()
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active embedding model configured"
            )
        return model
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting active model: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get active model: {str(e)}"
        )

