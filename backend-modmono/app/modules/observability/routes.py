"""
Audit log API endpoints.
Only accessible by Admin.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.auth.permissions import require_admin
from app.modules.observability.service import AuditService
from app.modules.observability.schemas import AuditLogResponse, AuditLogCountResponse, AuditAction
from app.modules.users.schemas import User
from app.core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor username"),
    action: Optional[str] = Query(None, description="Filter by action prefix (e.g., 'prompt')"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[str] = Query(None, description="Filter logs after this date (ISO format)"),
    end_date: Optional[str] = Query(None, description="Filter logs before this date (ISO format)"),
    limit: int = Query(100, ge=1, le=500, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Get audit logs with optional filters.
    
    **Requires Admin role.**
    
    Returns paginated list of audit log entries with details about:
    - Who performed the action
    - What action was taken
    - Which resource was affected
    - When it happened
    """
    service = AuditService(session)
    return await service.get_logs(
        actor_username=actor,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )


@router.get("/logs/count", response_model=AuditLogCountResponse)
async def get_audit_log_count(
    actor: Optional[str] = Query(None, description="Filter by actor username"),
    action: Optional[str] = Query(None, description="Filter by action prefix"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Get total count of audit logs matching filters.
    
    **Requires Admin role.**
    """
    service = AuditService(session)
    count = await service.get_log_count(
        actor_username=actor,
        action=action,
        resource_type=resource_type
    )
    return AuditLogCountResponse(count=count)


@router.get("/actions", response_model=List[str])
async def get_audit_action_types(
    current_user: User = Depends(require_admin)
):
    """
    Get list of all possible audit action types.
    
    **Requires Admin role.**
    """
    return [action.value for action in AuditAction]
