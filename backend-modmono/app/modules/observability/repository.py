"""
Audit log repository for database operations.
"""
from typing import Optional, List
from datetime import datetime
import json

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observability.models import AuditLogModel
from app.modules.observability.schemas import AuditLogResponse, AuditLogCreate
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class AuditLogRepository:
    """Repository for audit log database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, data: AuditLogCreate) -> int:
        """
        Create a new audit log entry.
        
        Args:
            data: Audit log data
            
        Returns:
            ID of the created log entry
        """
        try:
            details_json = json.dumps(data.details) if data.details else None
            
            db_obj = AuditLogModel(
                actor_id=data.actor_id,
                actor_username=data.actor_username,
                actor_role=data.actor_role,
                action=data.action,
                resource_type=data.resource_type,
                resource_id=data.resource_id,
                resource_name=data.resource_name,
                details=details_json,
                ip_address=data.ip_address,
                user_agent=data.user_agent
            )
            
            self.session.add(db_obj)
            await self.session.flush()
            
            logger.info(f"Audit: {data.action} by {data.actor_username or 'system'} on {data.resource_type}/{data.resource_id}")
            return db_obj.id
            
        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
            raise
    
    async def get_logs(
        self,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuditLogResponse]:
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
            List of audit log entries
        """
        try:
            stmt = select(AuditLogModel)
            filters = []
            
            if actor_username:
                filters.append(AuditLogModel.actor_username == actor_username)
            
            if action:
                # Prefix match for action filter
                filters.append(AuditLogModel.action.like(f"{action}%"))
            
            if resource_type:
                filters.append(AuditLogModel.resource_type == resource_type)
            
            if start_date:
                filters.append(AuditLogModel.timestamp >= start_date)
            
            if end_date:
                filters.append(AuditLogModel.timestamp <= end_date)
            
            if filters:
                stmt = stmt.where(and_(*filters))
            
            stmt = stmt.order_by(AuditLogModel.timestamp.desc()).limit(limit).offset(offset)
            
            result = await self.session.execute(stmt)
            rows = result.scalars().all()
            
            logs = []
            for row in rows:
                log_dict = {
                    "id": row.id,
                    "timestamp": row.timestamp,
                    "actor_id": str(row.actor_id) if row.actor_id else None,
                    "actor_username": row.actor_username,
                    "actor_role": row.actor_role,
                    "action": row.action,
                    "resource_type": row.resource_type,
                    "resource_id": row.resource_id,
                    "resource_name": row.resource_name,
                    "details": json.loads(row.details) if row.details else None,
                    "ip_address": row.ip_address,
                    "user_agent": row.user_agent
                }
                logs.append(AuditLogResponse(**log_dict))
            
            return logs
            
        except Exception as e:
            logger.error(f"Error querying audit logs: {e}")
            raise
    
    async def get_log_count(
        self,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None
    ) -> int:
        """
        Get total count of logs matching filters.
        
        Args:
            actor_username: Filter by username
            action: Filter by action type (prefix match)
            resource_type: Filter by resource type
            
        Returns:
            Count of matching logs
        """
        try:
            stmt = select(func.count()).select_from(AuditLogModel)
            filters = []
            
            if actor_username:
                filters.append(AuditLogModel.actor_username == actor_username)
            
            if action:
                filters.append(AuditLogModel.action.like(f"{action}%"))
            
            if resource_type:
                filters.append(AuditLogModel.resource_type == resource_type)
            
            if filters:
                stmt = stmt.where(and_(*filters))
            
            result = await self.session.execute(stmt)
            return result.scalar() or 0
            
        except Exception as e:
            logger.error(f"Error counting audit logs: {e}")
            raise
