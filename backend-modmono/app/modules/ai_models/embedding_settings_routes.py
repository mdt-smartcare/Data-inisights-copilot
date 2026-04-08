"""
Embedding Settings API - Compatibility layer for frontend.

Maps /settings/embedding endpoints to the unified AI Models service.
This provides backward compatibility with the frontend while using
the new simplified AI Models architecture.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.auth.permissions import get_current_user, require_admin
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User
from app.modules.ai_models.service import AIModelService
from app.modules.ai_models.schemas import AIModelCreate

logger = get_logger(__name__)

router = APIRouter(prefix="/settings/embedding", tags=["Embedding Settings"])


# =============================================================================
# Main Config Endpoint
# =============================================================================

@router.get(
    "",
    summary="Get current embedding configuration",
    description="Returns the active embedding model configuration."
)
async def get_embedding_config(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current embedding configuration."""
    service = AIModelService(db)
    defaults = await service.get_defaults()
    
    if defaults.embedding:
        return {
            "active_provider": defaults.embedding.provider_name,
            "config": {
                "model_name": defaults.embedding.model_id,
                "display_name": defaults.embedding.display_name,
                "deployment_type": defaults.embedding.deployment_type,
            },
            "dimension": defaults.embedding.dimensions
        }
    
    return {
        "active_provider": None,
        "config": {},
        "dimension": None
    }


# =============================================================================
# Model Registry Endpoints
# =============================================================================

@router.get(
    "/models",
    response_model=List[Dict[str, Any]],
    summary="List registered embedding models",
    description="List all embedding models from the model registry."
)
async def list_embedding_models(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """List all registered embedding models."""
    service = AIModelService(db)
    result = await service.list_models(model_type="embedding")
    
    # Convert to legacy format
    models = []
    for model in result.models:
        models.append({
            "id": model.id,
            "model_name": model.model_id,
            "display_name": model.display_name,
            "provider": model.provider_name,
            "dimensions": model.dimensions,
            "is_active": model.is_default,
            "is_builtin": model.provider_name in ["openai", "sentence-transformers"],
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "deployment_type": model.deployment_type,
            "download_status": model.download_status,
            "is_ready": model.is_ready,
        })
    
    return models


@router.post(
    "/models",
    response_model=Dict[str, Any],
    status_code=201,
    summary="Register a custom embedding model",
    description="Add a new custom embedding model to the registry."
)
async def register_embedding_model(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Register a new custom embedding model."""
    service = AIModelService(db)
    
    try:
        # Map legacy format to new format
        create_data = AIModelCreate(
            model_id=data.get("model_name"),
            display_name=data.get("display_name", data.get("model_name")),
            model_type="embedding",
            provider_name=data.get("provider", "custom"),
            deployment_type=data.get("deployment_type", "cloud"),
            dimensions=data.get("dimensions"),
            api_base_url=data.get("api_base_url"),
            api_key=data.get("api_key"),
            description=data.get("description"),
        )
        
        result = await service.create_model(create_data, str(current_user.id))
        
        return {
            "id": result.id,
            "model_name": result.model_id,
            "display_name": result.display_name,
            "provider": result.provider_name,
            "dimensions": result.dimensions,
            "is_active": result.is_default,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering embedding model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/models/{model_id}/activate",
    response_model=Dict[str, Any],
    summary="Activate an embedding model",
    description="Set a registered embedding model as the default."
)
async def activate_embedding_model(
    model_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Activate an embedding model."""
    service = AIModelService(db)
    
    try:
        # Get current default for comparison
        old_defaults = await service.get_defaults()
        old_dimensions = old_defaults.embedding.dimensions if old_defaults.embedding else None
        
        # Set new default
        new_defaults = await service.set_default("embedding", model_id)
        
        if not new_defaults.embedding:
            raise HTTPException(status_code=404, detail="Model not found")
        
        new_dimensions = new_defaults.embedding.dimensions
        dimension_changed = old_dimensions is not None and old_dimensions != new_dimensions
        
        return {
            "model": {
                "id": new_defaults.embedding.id,
                "model_name": new_defaults.embedding.model_id,
                "display_name": new_defaults.embedding.display_name,
                "dimensions": new_dimensions,
            },
            "dimension_changed": dimension_changed,
            "previous_dimensions": old_dimensions,
            "new_dimensions": new_dimensions,
            "requires_rebuild": dimension_changed,
            "rebuild_warning": f"Dimensions changed from {old_dimensions} to {new_dimensions}. Vector store rebuild required." if dimension_changed else None,
            "system_settings_updated": True,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error activating embedding model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/models/active",
    response_model=Dict[str, Any],
    summary="Get active embedding model",
    description="Get the currently active embedding model."
)
async def get_active_model(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get the currently active embedding model."""
    service = AIModelService(db)
    defaults = await service.get_defaults()
    
    if not defaults.embedding:
        raise HTTPException(status_code=404, detail="No active embedding model configured")
    
    model = defaults.embedding
    return {
        "id": model.id,
        "model_name": model.model_id,
        "display_name": model.display_name,
        "provider": model.provider_name,
        "dimensions": model.dimensions,
        "is_active": True,
        "deployment_type": model.deployment_type,
        "is_ready": model.is_ready,
    }


# =============================================================================
# Model Catalog Endpoints
# =============================================================================

# Curated model catalog for embedding models
EMBEDDING_MODEL_CATALOG = [
    {
        "model_name": "text-embedding-3-small",
        "display_name": "OpenAI Text Embedding 3 Small",
        "provider": "openai",
        "dimensions": 1536,
        "max_tokens": 8191,
        "speed_rating": 5,
        "quality_rating": 4,
        "category": "general",
        "requires_api_key": True,
        "description": "Fast, cost-effective embedding model from OpenAI",
    },
    {
        "model_name": "text-embedding-3-large",
        "display_name": "OpenAI Text Embedding 3 Large",
        "provider": "openai",
        "dimensions": 3072,
        "max_tokens": 8191,
        "speed_rating": 4,
        "quality_rating": 5,
        "category": "general",
        "requires_api_key": True,
        "description": "High-quality embedding model from OpenAI",
    },
    {
        "model_name": "BAAI/bge-base-en-v1.5",
        "display_name": "BGE Base English v1.5",
        "provider": "sentence-transformers",
        "dimensions": 768,
        "max_tokens": 512,
        "speed_rating": 4,
        "quality_rating": 4,
        "category": "general",
        "requires_api_key": False,
        "description": "Strong open-source embedding model, good balance of speed and quality",
    },
    {
        "model_name": "BAAI/bge-large-en-v1.5",
        "display_name": "BGE Large English v1.5",
        "provider": "sentence-transformers",
        "dimensions": 1024,
        "max_tokens": 512,
        "speed_rating": 3,
        "quality_rating": 5,
        "category": "general",
        "requires_api_key": False,
        "description": "High-quality open-source embedding model",
    },
    {
        "model_name": "BAAI/bge-small-en-v1.5",
        "display_name": "BGE Small English v1.5",
        "provider": "sentence-transformers",
        "dimensions": 384,
        "max_tokens": 512,
        "speed_rating": 5,
        "quality_rating": 3,
        "category": "fast",
        "requires_api_key": False,
        "description": "Fast, lightweight embedding model for quick prototyping",
    },
    {
        "model_name": "BAAI/bge-m3",
        "display_name": "BGE M3 (Multilingual)",
        "provider": "sentence-transformers",
        "dimensions": 1024,
        "max_tokens": 8192,
        "speed_rating": 3,
        "quality_rating": 5,
        "category": "multilingual",
        "requires_api_key": False,
        "description": "State-of-the-art multilingual embedding model with long context",
    },
]


@router.get(
    "/catalog",
    response_model=List[Dict[str, Any]],
    summary="Get curated model catalog",
    description="Returns the curated catalog of pre-validated embedding models."
)
async def get_model_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    local_only: bool = Query(False, description="Only return local models"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get the curated model catalog."""
    service = AIModelService(db)
    
    # Get registered models to mark which are already added
    registered = await service.list_models(model_type="embedding")
    registered_names = {m.model_id for m in registered.models}
    
    catalog = []
    for model in EMBEDDING_MODEL_CATALOG:
        # Apply filters
        if category and model.get("category") != category:
            continue
        if local_only and model.get("requires_api_key", False):
            continue
        
        catalog.append({
            **model,
            "is_registered": model["model_name"] in registered_names,
        })
    
    return catalog


@router.post(
    "/catalog/add",
    response_model=Dict[str, Any],
    status_code=201,
    summary="Add model from catalog",
    description="Add a model from the catalog to your registry."
)
async def add_model_from_catalog(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> Dict[str, Any]:
    """Add a model from the catalog."""
    model_name = data.get("model_name")
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name is required")
    
    # Find in catalog
    catalog_model = None
    for m in EMBEDDING_MODEL_CATALOG:
        if m["model_name"] == model_name:
            catalog_model = m
            break
    
    if not catalog_model:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found in catalog")
    
    service = AIModelService(db)
    
    try:
        create_data = AIModelCreate(
            model_id=catalog_model["model_name"],
            display_name=catalog_model["display_name"],
            model_type="embedding",
            provider_name=catalog_model["provider"],
            deployment_type="cloud" if catalog_model.get("requires_api_key") else "local",
            dimensions=catalog_model["dimensions"],
            context_length=catalog_model.get("max_tokens"),
            description=catalog_model.get("description"),
        )
        
        result = await service.create_model(create_data, str(current_user.id))
        
        return {
            "id": result.id,
            "model_name": result.model_id,
            "display_name": result.display_name,
            "provider": result.provider_name,
            "dimensions": result.dimensions,
            "message": f"Model '{model_name}' added successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/catalog/{model_name:path}/validate",
    summary="Validate model availability",
    description="Check if a model can be used."
)
async def validate_model(
    model_name: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Validate model availability."""
    # Find in catalog
    catalog_model = None
    for m in EMBEDDING_MODEL_CATALOG:
        if m["model_name"] == model_name:
            catalog_model = m
            break
    
    if not catalog_model:
        return {
            "model_name": model_name,
            "available": False,
            "message": f"Model '{model_name}' not found in catalog"
        }
    
    # Check if API key required
    if catalog_model.get("requires_api_key"):
        import os
        has_key = bool(os.environ.get("OPENAI_API_KEY"))
        return {
            "model_name": model_name,
            "available": has_key,
            "message": "OpenAI API key configured" if has_key else "OpenAI API key not configured"
        }
    
    return {
        "model_name": model_name,
        "available": True,
        "message": "Local model - no API key required"
    }
