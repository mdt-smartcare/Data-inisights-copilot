"""
Audit log routes.

Provides endpoints for querying audit logs and system monitoring.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.models.common import PaginatedResponse
from app.core.auth.permissions import require_admin, require_user
from app.modules.observability.service import AuditService
from app.modules.observability.schemas import AuditLog
from app.modules.users.presentation.schemas import User

router = APIRouter()


@router.get("/audit", response_model=PaginatedResponse[AuditLog])
async def query_audit_logs(
    actor_id: Optional[str] = Query(default=None, description="Filter by actor user ID"),
    actor_username: Optional[str] = Query(default=None, description="Filter by actor username"),
    action: Optional[str] = Query(default=None, description="Filter by action type"),
    resource_type: Optional[str] = Query(default=None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(default=None, description="Filter by resource ID"),
    start_date: Optional[datetime] = Query(default=None, description="Filter logs after this date"),
    end_date: Optional[datetime] = Query(default=None, description="Filter logs before this date"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Query audit logs with filters.
    
    **Required Permission:** ADMIN
    
    **Filters:**
    - actor_id: User ID who performed the action
    - actor_username: Username who performed the action
    - action: Type of action (e.g., "user.created", "agent.updated")
    - resource_type: Type of resource affected
    - resource_id: ID of resource affected
    - start_date: Show logs after this timestamp
    - end_date: Show logs before this timestamp
    """
    service = AuditService(session)
    logs, total = await service.query_logs(
        actor_id=actor_id,
        actor_username=actor_username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit
    )
    
    return PaginatedResponse(
        status="success",
        message=f"Retrieved {len(logs)} audit logs",
        data=logs,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/audit/recent", response_model=PaginatedResponse[AuditLog])
async def get_recent_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Get most recent audit logs.
    
    **Required Permission:** ADMIN
    
    Returns the most recent audit log entries, ordered by timestamp descending.
    """
    service = AuditService(session)
    logs = await service.get_recent_logs(limit=limit)
    
    return PaginatedResponse(
        status="success",
        message=f"Retrieved {len(logs)} recent audit logs",
        data=logs,
        total=len(logs),
        skip=0,
        limit=limit
    )


@router.get("/audit/user/{user_id}", response_model=PaginatedResponse[AuditLog])
async def get_user_activity(
    user_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_user)
):
    """
    Get audit logs for a specific user.
    
    **Permission:** Users can view their own activity. Admins can view any user's activity.
    
    Shows all actions performed by the specified user.
    """
    # Users can only view their own activity
    if current_user.id != user_id:
        from app.core.auth.permissions import can_view_all_audit_logs
        if not can_view_all_audit_logs(current_user.role):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot view other users' activity"
            )
    
    service = AuditService(session)
    logs = await service.get_user_activity(actor_id=user_id, limit=limit)
    
    return PaginatedResponse(
        status="success",
        message=f"Retrieved {len(logs)} activity logs for user",
        data=logs,
        total=len(logs),
        skip=0,
        limit=limit
    )
