"""
Model Configuration API - Cross-cutting endpoints for compatibility mappings
and versioned configuration snapshots.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List, Optional

from backend.core.permissions import require_super_admin, require_editor, User
from backend.services.model_registry_service import (
    get_model_registry_service, ModelRegistryService,
    CompatibilityCreate, ConfigRollbackRequest,
)
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings/models", tags=["Model Configuration"])


# ============================================================================
# Compatibility Endpoints
# ============================================================================

@router.get(
    "/compatibility",
    response_model=List[Dict[str, Any]],
    summary="Get compatibility table",
    description="Get the full embedding→LLM compatibility mapping table."
)
async def get_compatibility_table(
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_editor)
):
    """Get full compatibility table with model names."""
    try:
        return model_registry.get_compatibility_table()
    except Exception as e:
        logger.error(f"Error fetching compatibility table: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch compatibility table: {str(e)}"
        )


@router.post(
    "/compatibility",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Add compatibility mapping",
    description="Add a new embedding↔LLM compatibility mapping. Requires Super Admin."
)
async def add_compatibility_mapping(
    data: CompatibilityCreate,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_super_admin)
):
    """Add a compatibility mapping between an embedding and LLM model."""
    try:
        result = model_registry.add_compatibility(data)
        logger.info(f"Compatibility mapping added by {current_user.username}: emb={data.embedding_model_id} ↔ llm={data.llm_model_id}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding compatibility mapping: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add compatibility mapping: {str(e)}"
        )


@router.delete(
    "/compatibility/{mapping_id}",
    response_model=Dict[str, Any],
    summary="Remove compatibility mapping",
    description="Remove a compatibility mapping by ID. Requires Super Admin."
)
async def remove_compatibility_mapping(
    mapping_id: int,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_super_admin)
):
    """Remove a compatibility mapping."""
    deleted = model_registry.remove_compatibility(mapping_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Mapping {mapping_id} not found")
    logger.info(f"Compatibility mapping {mapping_id} removed by {current_user.username}")
    return {"success": True, "deleted_id": mapping_id}


# ============================================================================
# Config Version Endpoints
# ============================================================================

@router.get(
    "/config/versions",
    response_model=List[Dict[str, Any]],
    summary="List config versions",
    description="List versioned config snapshots for auditing and rollback."
)
async def list_config_versions(
    config_type: Optional[str] = None,
    limit: int = 20,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_editor)
):
    """List versioned config snapshots."""
    try:
        return model_registry.list_config_versions(config_type=config_type, limit=limit)
    except Exception as e:
        logger.error(f"Error listing config versions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list config versions: {str(e)}"
        )


@router.get(
    "/config/versions/{version_id}",
    response_model=Dict[str, Any],
    summary="Get config version detail",
    description="Get the full snapshot for a specific config version."
)
async def get_config_version_detail(
    version_id: int,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_editor)
):
    """Get a specific config version snapshot."""
    version = model_registry.get_config_version(version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Config version {version_id} not found")
    return version


@router.post(
    "/config/rollback",
    response_model=Dict[str, Any],
    summary="Rollback configuration",
    description="Rollback model configuration to a previous version. Requires Super Admin."
)
async def rollback_config(
    request: ConfigRollbackRequest,
    model_registry: ModelRegistryService = Depends(get_model_registry_service),
    current_user: User = Depends(require_super_admin)
):
    """Rollback to a previous config version."""
    try:
        result = model_registry.rollback_to_version(request.version_id, updated_by=current_user.username)
        logger.info(f"Config rolled back to version {request.version_id} by {current_user.username}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error rolling back config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback config: {str(e)}"
        )
