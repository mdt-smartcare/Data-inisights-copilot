"""
Audit logging service for tracking user actions.
Provides auditability for all configuration changes.
"""
from typing import Optional, List, Dict, Any, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.repository import AuditLogRepository
from app.modules.audit.schemas import AuditLogResponse, AuditLogCreate, AuditAction, AuditLogListResponse
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class AuditService:
    """Service for logging and querying audit events."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AuditLogRepository(session)
    
    async def log(
        self,
        action: Union[AuditAction, str],
        actor_id: Optional[str] = None,
        actor_username: Optional[str] = None,
        actor_role: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> int:
        """
        Log an audit event.
        
        Args:
            action: The action being performed (AuditAction enum or string)
            actor_id: User ID performing the action
            actor_username: Username of the actor
            actor_role: Role of the actor
            resource_type: Type of resource affected (e.g., 'prompt', 'connection')
            resource_id: ID of the affected resource
            resource_name: Human-readable name of the resource
            details: Additional details as a dictionary
            ip_address: Client IP address
            user_agent: Client user agent
            
        Returns:
            ID of the created log entry
        """
        action_str = action.value if isinstance(action, AuditAction) else action
        
        log_data = AuditLogCreate(
            actor_id=actor_id,
            actor_username=actor_username,
            actor_role=actor_role,
            action=action_str,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return await self.repository.create(log_data)
    
    async def get_logs(
        self,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> AuditLogListResponse:
        """
        Query audit logs with optional filters.
        
        Args:
            actor_username: Filter by username
            action: Filter by action type (prefix match)
            resource_type: Filter by resource type
            start_date: Filter logs after this date (ISO format)
            end_date: Filter logs before this date (ISO format)
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            AuditLogListResponse with logs and total count
        """
        logs = await self.repository.get_logs(
            actor_username=actor_username,
            action=action,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset
        )
        
        total = await self.repository.get_log_count(
            actor_username=actor_username,
            action=action,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date
        )
        
        return AuditLogListResponse(logs=logs, total=total)
    
    async def get_log_count(
        self,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> int:
        """
        Get total count of logs matching filters.
        
        Args:
            actor_username: Filter by username
            action: Filter by action type (prefix match)
            resource_type: Filter by resource type
            start_date: Filter logs after this date (ISO format)
            end_date: Filter logs before this date (ISO format)
            
        Returns:
            Count of matching logs
        """
        return await self.repository.get_log_count(
            actor_username=actor_username,
            action=action,
            resource_type=resource_type,
            start_date=start_date,
            end_date=end_date
        )
