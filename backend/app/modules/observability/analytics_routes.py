"""
Query Analytics API Routes.

Provides endpoints for viewing query execution analytics and improvement suggestions.
All endpoints are privacy-safe and do not expose actual query content.

PRIVACY NOTE:
- No actual query text is stored or returned
- No SQL queries are logged
- No result data is exposed
- Only aggregate metrics and patterns are available
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.models.common import BaseResponse
from app.core.auth.permissions import require_admin, get_current_user
from app.modules.users.schemas import User
from app.modules.observability.analytics_service import QueryAnalyticsService

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ============================================
# Pydantic Models
# ============================================

class CategoryStats(BaseModel):
    """Statistics for a query category."""
    count: int
    success_count: int
    success_rate: float


class AnalyticsSummary(BaseModel):
    """Summary of query analytics."""
    period_days: int
    total_queries: int
    success_count: int = 0
    success_rate: float
    sql_generation_rate: float
    sql_execution_rate: float
    avg_execution_time_ms: int
    avg_generation_time_ms: int
    avg_total_time_ms: int = 0
    by_category: Dict[str, CategoryStats]
    by_error_type: Dict[str, int]
    by_complexity: Dict[str, CategoryStats] = {}


class ErrorAnalytics(BaseModel):
    """Analytics for a specific error type."""
    error_type: str
    error_category: str
    count: int
    percentage: float
    suggested_fix: str


class ImprovementSuggestion(BaseModel):
    """A suggestion for improving accuracy."""
    priority: str
    area: str
    issue: str
    suggestion: str
    impact: str
    error_type: Optional[str] = None
    category: Optional[str] = None


class DailyTrend(BaseModel):
    """Daily query trend data point."""
    date: Optional[str]
    total_queries: int
    successful_queries: int
    success_rate: float
    avg_time_ms: int


class LogQueryRequest(BaseModel):
    """Request to log a query execution (for testing/manual logging)."""
    query_category: Optional[str] = Field(None, description="Query category")
    query_complexity: Optional[str] = Field(None, description="simple, medium, or complex")
    sql_generated: bool = Field(False, description="Whether SQL was generated")
    sql_executed: bool = Field(False, description="Whether SQL was executed")
    execution_success: bool = Field(False, description="Whether execution succeeded")
    error_type: Optional[str] = Field(None, description="Error type if failed")
    generation_time_ms: Optional[int] = Field(None, description="SQL generation time")
    execution_time_ms: Optional[int] = Field(None, description="SQL execution time")
    result_row_count: Optional[int] = Field(None, description="Number of rows returned")
    data_source_type: Optional[str] = Field(None, description="Type of data source")


# ============================================
# API Endpoints
# ============================================

@router.get(
    "/summary",
    response_model=BaseResponse[AnalyticsSummary],
    summary="Get analytics summary",
    description="Get summary statistics for recent query executions."
)
async def get_analytics_summary(
    days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> BaseResponse[AnalyticsSummary]:
    """
    Get summary statistics for recent queries.
    
    Returns overall success rates, timing metrics, and breakdowns by category
    and error type. All data is privacy-safe with no actual query content.
    
    **Required Permission:** ADMIN
    """
    try:
        service = QueryAnalyticsService(session)
        summary = await service.get_summary(days=days)
        
        # Convert nested dicts to Pydantic models
        by_category = {
            k: CategoryStats(**v) for k, v in summary.get("by_category", {}).items()
        }
        by_complexity = {
            k: CategoryStats(**v) for k, v in summary.get("by_complexity", {}).items()
        }
        
        result = AnalyticsSummary(
            period_days=summary["period_days"],
            total_queries=summary["total_queries"],
            success_count=summary.get("success_count", 0),
            success_rate=summary["success_rate"],
            sql_generation_rate=summary["sql_generation_rate"],
            sql_execution_rate=summary["sql_execution_rate"],
            avg_execution_time_ms=summary["avg_execution_time_ms"],
            avg_generation_time_ms=summary["avg_generation_time_ms"],
            avg_total_time_ms=summary.get("avg_total_time_ms", 0),
            by_category=by_category,
            by_error_type=summary.get("by_error_type", {}),
            by_complexity=by_complexity
        )
        
        return BaseResponse.ok(data=result)
        
    except Exception as e:
        logger.error(f"Failed to get analytics summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analytics summary: {str(e)}"
        )


@router.get(
    "/errors",
    response_model=BaseResponse[List[ErrorAnalytics]],
    summary="Get error analytics",
    description="Get analytics about common error patterns."
)
async def get_error_analytics(
    days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum error types to return"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> BaseResponse[List[ErrorAnalytics]]:
    """
    Get analytics about common error patterns.
    
    Returns the most frequent error types with their counts, percentages,
    and suggested fixes for each. Useful for prioritizing training improvements.
    
    **Required Permission:** ADMIN
    """
    try:
        service = QueryAnalyticsService(session)
        errors = await service.get_error_analytics(days=days, limit=limit)
        
        result = [ErrorAnalytics(**e) for e in errors]
        
        return BaseResponse.ok(data=result)
        
    except Exception as e:
        logger.error(f"Failed to get error analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get error analytics: {str(e)}"
        )


@router.get(
    "/improvement-suggestions",
    response_model=BaseResponse[List[ImprovementSuggestion]],
    summary="Get improvement suggestions",
    description="Get AI-generated suggestions for improving NL2SQL accuracy."
)
async def get_improvement_suggestions(
    days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> BaseResponse[List[ImprovementSuggestion]]:
    """
    Get suggestions for improving accuracy based on failure patterns.
    
    Analyzes recent query failures and generates prioritized suggestions
    for training improvements. Includes specific action items for each issue.
    
    **Required Permission:** ADMIN
    """
    try:
        service = QueryAnalyticsService(session)
        suggestions = await service.get_improvement_suggestions(days=days)
        
        result = [ImprovementSuggestion(**s) for s in suggestions]
        
        return BaseResponse.ok(data=result)
        
    except Exception as e:
        logger.error(f"Failed to get improvement suggestions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get improvement suggestions: {str(e)}"
        )


@router.get(
    "/trend",
    response_model=BaseResponse[List[DailyTrend]],
    summary="Get daily trend",
    description="Get daily query execution trend data."
)
async def get_daily_trend(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> BaseResponse[List[DailyTrend]]:
    """
    Get daily query trend data.
    
    Returns daily statistics including query counts, success rates,
    and average execution times. Useful for tracking accuracy over time.
    
    **Required Permission:** ADMIN
    """
    try:
        service = QueryAnalyticsService(session)
        trend = await service.get_daily_trend(days=days)
        
        result = [DailyTrend(**t) for t in trend]
        
        return BaseResponse.ok(data=result)
        
    except Exception as e:
        logger.error(f"Failed to get daily trend: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get daily trend: {str(e)}"
        )


@router.post(
    "/log",
    response_model=BaseResponse[Dict[str, int]],
    summary="Log query metrics",
    description="Log query execution metrics (for testing or manual logging)."
)
async def log_query_metrics(
    request: LogQueryRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
) -> BaseResponse[Dict[str, int]]:
    """
    Log query execution metrics.
    
    This endpoint allows manual logging of query metrics for testing
    or integration purposes. Does NOT accept actual query content.
    
    **Required Permission:** ADMIN
    
    **Privacy:** Only metadata is logged, never actual queries or results.
    """
    try:
        service = QueryAnalyticsService(session)
        
        record_id = await service.log_query(
            query_category=request.query_category,
            query_complexity=request.query_complexity,
            sql_generated=request.sql_generated,
            sql_executed=request.sql_executed,
            execution_success=request.execution_success,
            error_type=request.error_type,
            generation_time_ms=request.generation_time_ms,
            execution_time_ms=request.execution_time_ms,
            result_row_count=request.result_row_count,
            data_source_type=request.data_source_type
        )
        
        await session.commit()
        
        logger.info(
            "Query metrics logged via API",
            record_id=record_id,
            user_id=str(current_user.id),
            category=request.query_category
        )
        
        return BaseResponse.ok(
            data={"record_id": record_id},
            message="Query metrics logged successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to log query metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to log query metrics: {str(e)}"
        )


@router.get(
    "/health",
    response_model=BaseResponse[Dict[str, Any]],
    summary="Analytics health check",
    description="Check the health of the analytics system."
)
async def analytics_health_check(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
) -> BaseResponse[Dict[str, Any]]:
    """
    Check the health of the analytics system.
    
    Returns basic statistics and connectivity status.
    """
    try:
        service = QueryAnalyticsService(session)
        summary = await service.get_summary(days=1)
        
        return BaseResponse.ok(data={
            "status": "healthy",
            "queries_last_24h": summary["total_queries"],
            "success_rate_24h": summary["success_rate"],
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Analytics health check failed: {e}", exc_info=True)
        return BaseResponse.ok(data={
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })
