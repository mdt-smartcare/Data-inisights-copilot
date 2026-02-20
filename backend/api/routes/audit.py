"""
Audit log API endpoints.
Only accessible by Super Admin.
"""
from fastapi import APIRouter, Depends, Query
from typing import List, Dict, Any, Optional

from backend.services.audit_service import get_audit_service, AuditService
from backend.core.permissions import require_admin, User
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit Logs"])


@router.get("/logs", response_model=List[Dict[str, Any]], dependencies=[Depends(require_admin)])
async def get_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor username"),
    action: Optional[str] = Query(None, description="Filter by action prefix (e.g., 'prompt')"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[str] = Query(None, description="Filter logs after this date (ISO format)"),
    end_date: Optional[str] = Query(None, description="Filter logs before this date (ISO format)"),
    limit: int = Query(100, ge=1, le=500, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    audit_service: AuditService = Depends(get_audit_service)
):
    """
    Get audit logs with optional filters.
    
    **Requires Super Admin role.**
    
    Returns paginated list of audit log entries with details about:
    - Who performed the action
    - What action was taken
    - Which resource was affected
    - When it happened
    """
    return audit_service.get_logs(
        actor_username=actor,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )


@router.get("/logs/count", response_model=Dict[str, int], dependencies=[Depends(require_admin)])
async def get_audit_log_count(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    audit_service: AuditService = Depends(get_audit_service)
):
    """
    Get total count of audit logs matching filters.
    
    **Requires Super Admin role.**
    """
    count = audit_service.get_log_count(
        actor_username=actor,
        action=action,
        resource_type=resource_type
    )
    return {"count": count}


@router.get("/actions", response_model=List[str], dependencies=[Depends(require_admin)])
async def get_audit_action_types():
    """
    Get list of all possible audit action types.
    
    **Requires Admin role.**
    """
    from backend.services.audit_service import AuditAction
    return [action.value for action in AuditAction]
