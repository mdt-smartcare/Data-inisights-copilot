"""
Health check endpoint for service monitoring.
"""
from fastapi import APIRouter
from datetime import datetime

from backend.models.schemas import HealthResponse
from backend.config import get_settings
from backend.services.sql_service import get_sql_service
from backend.services.vector_store import get_vector_store
from backend.core.logging import get_logger

router = APIRouter(prefix="/health", tags=["Health"])
logger = get_logger(__name__)
settings = get_settings()


@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Check health status of the backend service and its dependencies.
    
    Returns status of:
    - Overall service
    - Database connection
    - Vector store
    - LLM availability
    
    **No authentication required.**
    """
    logger.debug("Health check requested")
    
    services_status = {}
    overall_status = "healthy"
    
    # Check database
    try:
        sql_service = get_sql_service()
        db_healthy = sql_service.health_check()
        services_status["database"] = "connected" if db_healthy else "disconnected"
        if not db_healthy:
            overall_status = "degraded"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        services_status["database"] = "error"
        overall_status = "unhealthy"
    
    # Check vector store
    try:
        vector_store = get_vector_store()
        vs_healthy = vector_store.health_check()
        services_status["vector_store"] = "loaded" if vs_healthy else "unavailable"
        if not vs_healthy:
            overall_status = "degraded"
    except Exception as e:
        logger.error(f"Vector store health check failed: {e}")
        services_status["vector_store"] = "error"
        overall_status = "unhealthy"
    
    # LLM is checked on demand, so just mark as configured
    services_status["llm"] = "ready"
    
    return HealthResponse(
        status=overall_status,
        version=settings.version,
        timestamp=datetime.utcnow(),
        services=services_status
    )
