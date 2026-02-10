from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel

from backend.services.observability_service import ObservabilityService, get_observability_service
from backend.api.deps import get_current_user, require_super_admin
from backend.models.schemas import User

router = APIRouter(prefix="/observability", tags=["observability"])

class ObservabilityConfigUpdate(BaseModel):
    log_level: Optional[str] = None
    langfuse_enabled: Optional[bool] = None
    tracing_provider: Optional[str] = None
    trace_sample_rate: Optional[float] = None
    log_destinations: Optional[list[str]] = None

@router.get("/config", summary="Get observability configuration")
async def get_observability_config(
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
):
    """Get current observability settings."""
    return await service.get_config()

@router.put("/config", summary="Update observability configuration")
async def update_observability_config(
    updates: Dict[str, Any] = Body(...),
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
):
    """Update observability settings and apply changes immediately."""
    try:
        return await service.update_config(updates, updated_by=current_user.username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")

@router.get("/usage", summary="Get usage statistics")
async def get_usage_statistics(
    period: str = Query("24h", regex="^(1h|24h|7d|30d)$"),
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
):
    """
    Get aggregated usage statistics (costs, tokens, latency) for a time period.
    """
    return await service.get_usage_stats(period)

@router.post("/test-log", summary="Emit a test log message")
async def test_log_emission(
    level: str = Query("INFO", regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    message: str = Query("Test log message from admin panel"),
    current_user: User = Depends(require_super_admin)
):
    """Emit a log message to test logging configuration."""
    import logging
    logger = logging.getLogger("backend.api.test")
    
    log_method = getattr(logger, level.lower())
    log_method(f"[TEST] {message} (triggered by {current_user.username})")
    
    return {"status": "success", "level": level, "message": message}
