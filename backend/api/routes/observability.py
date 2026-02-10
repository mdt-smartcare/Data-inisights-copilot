from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel

from backend.services.observability_service import ObservabilityService, get_observability_service
from backend.api.deps import require_super_admin
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

@router.get("/usage", summary="Get usage statistics from Langfuse")
async def get_usage_statistics(
    period: str = Query("24h", regex="^(1h|24h|7d|30d)$"),
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
):
    """
    Get aggregated usage statistics (costs, tokens, latency) from Langfuse.
    
    Returns:
        - summary: Total traces, observations, generations, cost, tokens
        - by_model: Breakdown by model (calls, tokens, cost, latency)
        - by_operation: Breakdown by operation type (llm, embedding, retrieval)
        - latency_percentiles: p50, p75, p90, p95, p99
    """
    return await service.get_usage_stats(period)

@router.get("/traces", summary="Get recent traces from Langfuse")
async def get_recent_traces(
    limit: int = Query(20, ge=1, le=100),
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
) -> List[Dict[str, Any]]:
    """
    Get recent traces for display in the observability dashboard.
    
    Returns list of traces with:
        - id, name, timestamp
        - latency, tokens, cost
        - status, user_id, session_id
    """
    return await service.get_recent_traces(limit=limit)

@router.get("/traces/{trace_id}", summary="Get trace details from Langfuse")
async def get_trace_detail(
    trace_id: str,
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
) -> Dict[str, Any]:
    """
    Get detailed trace information including all spans and generations.
    """
    trace = await service.get_trace_detail(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace

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

@router.get("/health", summary="Check Langfuse connection health")
async def check_langfuse_health(
    service: ObservabilityService = Depends(get_observability_service),
    current_user: User = Depends(require_super_admin)
) -> Dict[str, Any]:
    """Check if Langfuse is properly configured and reachable."""
    health = {
        "langfuse_enabled": service.langfuse_client.enabled,
        "langfuse_host": service.langfuse_client.host,
        "connection_status": "unknown"
    }
    
    if service.langfuse_client.enabled:
        try:
            # Try to fetch one trace to verify connection
            traces = await service.langfuse_client.get_traces(limit=1)
            health["connection_status"] = "connected"
            health["total_traces"] = traces.get("meta", {}).get("totalItems", 0)
        except Exception as e:
            health["connection_status"] = "error"
            health["error"] = str(e)
    else:
        health["connection_status"] = "disabled"
        
    return health
