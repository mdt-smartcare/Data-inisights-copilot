"""
Audit logging helper utilities.

Provides helper functions to extract request context and create audit logs
with consistent formatting across all modules.
"""
from typing import Optional, Dict, Any, Union
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import AuditAction
from app.modules.audit.service import AuditService
from app.modules.users.schemas import User
from app.core.utils.logging import get_logger
from app.core.database.session import get_db_session

logger = get_logger(__name__)


class AuditLogger:
    """
    Audit logger with injected dependencies.
    
    Use as a FastAPI dependency to simplify audit logging in routes.
    Auto-injects database session.
    
    Usage:
        @router.post("/example")
        async def example(
            audit: AuditLogger = Depends(get_audit_logger),
            current_user: User = Depends(get_current_user),
        ):
            await audit.log(
                action=AuditAction.EXAMPLE,
                actor=current_user,
                resource_type="example",
                resource_id="123",
            )
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def log(
        self,
        action: Union[AuditAction, str],
        actor: Optional[User] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Log an audit event.
        
        Args:
            action: Audit action type (AuditAction enum or string)
            actor: User performing the action
            resource_type: Type of resource affected
            resource_id: ID of affected resource
            resource_name: Human-readable name of resource
            details: Additional details to log
            
        Returns:
            Audit log entry ID
        """
        return await log_audit(
            session=self.session,
            action=action,
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=details,
        )


def get_audit_logger(
    db: AsyncSession = Depends(get_db_session),
) -> AuditLogger:
    """
    FastAPI dependency for AuditLogger.
    
    Injects database session automatically.
    """
    return AuditLogger(db)


async def log_audit(
    session: AsyncSession,
    action: Union[AuditAction, str],
    actor: Optional[User] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Log an audit event.
    
    Args:
        session: Database session
        action: Audit action type (AuditAction enum or string)
        actor: User performing the action
        resource_type: Type of resource affected (e.g., 'agent', 'user', 'datasource')
        resource_id: ID of affected resource
        resource_name: Human-readable name of resource
        details: Additional details to log
        
    Returns:
        Audit log entry ID
    """
    # Get actor info
    actor_id = str(actor.id) if actor else None
    actor_username = actor.username if actor else None
    actor_role = actor.role if actor else None
    
    # Create audit log
    service = AuditService(session)
    log_id = await service.log(
        action=action,
        actor_id=actor_id,
        actor_username=actor_username,
        actor_role=actor_role,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        details=details,
    )
    
    logger.debug(
        f"Audit log created: {action}",
        log_id=log_id,
        actor=actor_username,
        resource_type=resource_type,
        resource_id=resource_id
    )
    
    return log_id
