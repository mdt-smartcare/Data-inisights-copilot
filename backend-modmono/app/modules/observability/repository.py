"""
Audit log repository for database operations.

Extends BaseRepository with audit-specific queries.
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base_repository import BaseRepository
from app.modules.observability.models import AuditLogModel
from app.modules.observability.schemas import AuditLog, AuditLogCreate
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class AuditLogRepository(BaseRepository[AuditLogModel, AuditLogCreate, AuditLogCreate, AuditLog]):
    """Repository for audit log database operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(
            session=session,
            model=AuditLogModel,
            response_schema=AuditLog
        )
    
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
    ) -> List[AuditLog]:
        """
        Query audit logs with filters.
        
        Args:
            actor_id: Filter by actor user ID
            actor_username: Filter by actor username
            action: Filter by action type
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            start_date: Filter logs after this date
            end_date: Filter logs before this date
            skip: Pagination offset
            limit: Pagination limit
        
        Returns:
            List of matching audit logs
        """
        try:
            stmt = select(AuditLogModel)
            
            # Build filters
            filters = []
            
            if actor_id:
                filters.append(AuditLogModel.actor_id == actor_id)
            
            if actor_username:
                filters.append(AuditLogModel.actor_username == actor_username)
            
            if action:
                filters.append(AuditLogModel.action == action)
            
            if resource_type:
                filters.append(AuditLogModel.resource_type == resource_type)
            
            if resource_id:
                filters.append(AuditLogModel.resource_id == resource_id)
            
            if start_date:
                filters.append(AuditLogModel.timestamp >= start_date)
            
            if end_date:
                filters.append(AuditLogModel.timestamp <= end_date)
            
            # Apply filters
            if filters:
                stmt = stmt.where(and_(*filters))
            
            # Order by timestamp descending and paginate
            stmt = stmt.order_by(AuditLogModel.timestamp.desc()).offset(skip).limit(limit)
            
            result = await self.session.execute(stmt)
            db_objs = result.scalars().all()
            
            return [self._to_pydantic(obj) for obj in db_objs]
            
        except Exception as e:
            logger.error(f"Error querying audit logs: {e}")
            raise
    
    async def count_logs(
        self,
        actor_id: Optional[str] = None,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Count audit logs matching filters.
        
        Args:
            Same filters as query_logs
        
        Returns:
            Count of matching logs
        """
        try:
            from sqlalchemy import func
            stmt = select(func.count()).select_from(AuditLogModel)
            
            # Build filters (same as query_logs)
            filters = []
            
            if actor_id:
                filters.append(AuditLogModel.actor_id == actor_id)
            
            if actor_username:
                filters.append(AuditLogModel.actor_username == actor_username)
            
            if action:
                filters.append(AuditLogModel.action == action)
            
            if resource_type:
                filters.append(AuditLogModel.resource_type == resource_type)
            
            if resource_id:
                filters.append(AuditLogModel.resource_id == resource_id)
            
            if start_date:
                filters.append(AuditLogModel.timestamp >= start_date)
            
            if end_date:
                filters.append(AuditLogModel.timestamp <= end_date)
            
            # Apply filters
            if filters:
                stmt = stmt.where(and_(*filters))
            
            result = await self.session.execute(stmt)
            return result.scalar()
            
        except Exception as e:
            logger.error(f"Error counting audit logs: {e}")
            raise
    
    async def get_recent_logs(self, limit: int = 100) -> List[AuditLog]:
        """
        Get most recent audit logs.
        
        Args:
            limit: Maximum number of logs to return
        
        Returns:
            List of recent audit logs
        """
        return await self.query_logs(limit=limit)
    
    async def get_logs_by_user(self, actor_id: str, limit: int = 100) -> List[AuditLog]:
        """
        Get audit logs for a specific user.
        
        Args:
            actor_id: User ID
            limit: Maximum number of logs to return
        
        Returns:
            List of audit logs for the user
        """
        return await self.query_logs(actor_id=actor_id, limit=limit)
