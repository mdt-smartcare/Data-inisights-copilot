"""
Settings API Routes - CRUD endpoints for system configuration.
Provides REST API for managing all configurable system settings.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal

from backend.services.settings_service import (
    get_settings_service, 
    SettingsService, 
    SettingCategory
)
from backend.core.permissions import require_super_admin, require_editor, get_current_user, User
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SettingUpdateRequest(BaseModel):
    """Request model for updating settings."""
    settings: Dict[str, Any] = Field(..., description="Key-value pairs of settings to update")
    reason: Optional[str] = Field(None, description="Reason for the change")


class SettingHistoryResponse(BaseModel):
    """Response model for settings history."""
    id: int
    setting_id: int
    category: str
    key: str
    previous_value: Optional[str]
    new_value: str
    changed_by: Optional[str]
    change_reason: Optional[str]
    changed_at: str


class RollbackRequest(BaseModel):
    """Request model for rollback operation."""
    history_id: int = Field(..., description="ID of the history record to rollback to")


class ExportRequest(BaseModel):
    """Request model for settings export."""
    format: Literal["json", "yaml"] = Field(default="json", description="Export format")


class ImportRequest(BaseModel):
    """Request model for settings import."""
    data: str = Field(..., description="Settings data to import")
    format: Literal["json", "yaml"] = Field(default="json", description="Import format")


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "",
    response_model=Dict[str, Dict[str, Any]],
    summary="Get all settings",
    description="Retrieve all system settings grouped by category. Sensitive values are masked."
)
async def get_all_settings(
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_editor)
):
    """Get all settings grouped by category."""
    try:
        return settings_service.get_all_settings()
    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch settings: {str(e)}"
        )


@router.get(
    "/{category}",
    response_model=Dict[str, Any],
    summary="Get category settings",
    description="Retrieve all settings for a specific category."
)
async def get_category_settings(
    category: str,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_editor)
):
    """Get settings for a specific category."""
    # Validate category
    valid_categories = [c.value for c in SettingCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {valid_categories}"
        )
    
    try:
        return settings_service.get_category_settings(category)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching {category} settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch settings: {str(e)}"
        )


@router.put(
    "/{category}",
    response_model=Dict[str, Any],
    summary="Update category settings",
    description="Update one or more settings within a category. Requires Super Admin role."
)
async def update_category_settings(
    category: str,
    request: SettingUpdateRequest,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_super_admin)
):
    """Update settings for a specific category."""
    # Validate category
    valid_categories = [c.value for c in SettingCategory]
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of: {valid_categories}"
        )
    
    try:
        result = settings_service.update_category_settings(
            category=category,
            settings=request.settings,
            updated_by=current_user.username,
            change_reason=request.reason
        )
        
        logger.info(f"Settings updated for {category} by {current_user.username}")
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating {category} settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )


@router.get(
    "/history/{category}",
    response_model=List[Dict[str, Any]],
    summary="Get settings history",
    description="Retrieve change history for a category or all categories."
)
async def get_settings_history(
    category: Optional[str] = None,
    limit: int = 50,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_editor)
):
    """Get settings change history."""
    try:
        return settings_service.get_settings_history(category=category, limit=limit)
    except Exception as e:
        logger.error(f"Error fetching settings history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch history: {str(e)}"
        )


@router.post(
    "/rollback",
    response_model=Dict[str, Any],
    summary="Rollback to previous value",
    description="Rollback a setting to a previous value from history. Requires Super Admin role."
)
async def rollback_setting(
    request: RollbackRequest,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_super_admin)
):
    """Rollback a setting to a previous value."""
    try:
        result = settings_service.rollback_setting(
            history_id=request.history_id,
            rolled_back_by=current_user.username
        )
        
        logger.info(f"Setting rolled back by {current_user.username}: {result}")
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error rolling back setting: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback: {str(e)}"
        )


@router.post(
    "/export",
    response_model=Dict[str, str],
    summary="Export all settings",
    description="Export all settings to JSON or YAML format."
)
async def export_settings(
    request: ExportRequest,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_editor)
):
    """Export all settings."""
    try:
        exported = settings_service.export_settings(format=request.format)
        return {
            "format": request.format,
            "data": exported
        }
    except Exception as e:
        logger.error(f"Error exporting settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export: {str(e)}"
        )


@router.post(
    "/import",
    response_model=Dict[str, Any],
    summary="Import settings",
    description="Import settings from JSON or YAML format. Requires Super Admin role."
)
async def import_settings(
    request: ImportRequest,
    settings_service: SettingsService = Depends(get_settings_service),
    current_user: User = Depends(require_super_admin)
):
    """Import settings from JSON or YAML."""
    try:
        result = settings_service.import_settings(
            data=request.data,
            format=request.format,
            imported_by=current_user.username
        )
        
        logger.info(f"Settings imported by {current_user.username}: {result}")
        return {
            "status": "success",
            "imported": result,
            "total": sum(result.values())
        }
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error importing settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import: {str(e)}"
        )


@router.get(
    "/categories",
    response_model=List[str],
    summary="List all categories",
    description="Get list of all valid setting categories."
)
async def list_categories():
    """Get list of all valid setting categories."""
    return [c.value for c in SettingCategory]
