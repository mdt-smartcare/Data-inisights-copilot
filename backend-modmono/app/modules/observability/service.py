"""
Audit service for logging and querying system actions.

Provides centralized audit logging for compliance and security monitoring.
"""
from typing import Optional, List
from datetime import datetime
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observability.repository import AuditLogRepository
from app.modules.observability.schemas import AuditLog, AuditLogCreate
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class AuditService:
    """Service for audit logging operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AuditLogRepository(session)
    
    async def log_action(
        self,
        action: str,
        actor_id: Optional[str] = None,
        actor_username: Optional[str] = None,
        actor_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """
        Log an action to the audit trail.
        
        Args:
            action: Action performed (e.g., "user.created", "agent.updated")
            actor_id: ID of user performing action
            actor_username: Username of actor
            actor_role: Role of actor
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            resource_name: Name of resource affected
            details: Additional details (dict, will be JSON-serialized)
            ip_address: IP address of request
            user_agent: User agent string
        
        Returns:
            Created audit log entry
        """
        # Serialize details to JSON string
        details_str = None
        if details:
            try:
                details_str = json.dumps(details)
            except Exception as e:
                logger.warning(f"Failed to serialize audit details: {e}")
                details_str = str(details)
        
        log_data = AuditLogCreate(
            actor_id=actor_id,
            actor_username=actor_username,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=details_str,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        audit_log = await self.repository.create(log_data)
        
        logger.info(
            "Audit log created",
            action=action,
            actor=actor_username,
            resource=f"{resource_type}/{resource_id}" if resource_type else None
        )
        
        return audit_log
    
    async def query_logs(
        self,
        actor_id: Optional[str] = None,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[AuditLog], int]:
        """
        Query audit logs with filters.
        
        Args:
            Various filter parameters
        
        Returns:
            Tuple of (logs list, total count)
        """
        logs = await self.repository.query_logs(
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
        
        total = await self.repository.count_logs(
            actor_id=actor_id,
            actor_username=actor_username,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return logs, total
    
    async def get_recent_logs(self, limit: int = 100) -> List[AuditLog]:
        """Get most recent audit logs."""
        return await self.repository.get_recent_logs(limit=limit)
    
    async def get_user_activity(self, actor_id: str, limit: int = 100) -> List[AuditLog]:
        """Get audit logs for a specific user."""
        return await self.repository.get_logs_by_user(actor_id=actor_id, limit=limit)
