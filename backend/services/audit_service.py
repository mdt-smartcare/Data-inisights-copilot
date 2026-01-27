"""
Audit logging service for tracking user actions.
Provides auditability for all configuration changes.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import json

from backend.sqliteDb.db import get_db_service
from backend.core.logging import get_logger

logger = get_logger(__name__)


class AuditAction(str, Enum):
    """Types of auditable actions."""
    # User Management
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    
    # Connection Management
    CONNECTION_CREATE = "connection.create"
    CONNECTION_UPDATE = "connection.update"
    CONNECTION_DELETE = "connection.delete"
    CONNECTION_TEST = "connection.test"
    
    # Schema/Config
    SCHEMA_SELECT = "schema.select"
    DICTIONARY_UPDATE = "dictionary.update"
    
    # Prompt Engineering
    PROMPT_GENERATE = "prompt.generate"
    PROMPT_EDIT = "prompt.edit"
    PROMPT_PUBLISH = "prompt.publish"
    PROMPT_ROLLBACK = "prompt.rollback"
    
    # System
    CONFIG_EXPORT = "config.export"
    CONFIG_IMPORT = "config.import"


class AuditService:
    """
    Service for logging and querying audit events.
    """
    
    def __init__(self):
        self.db = get_db_service()
        self._ensure_table()
    
    def _ensure_table(self):
        """Create audit_logs table if it doesn't exist."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                actor_id INTEGER,
                actor_username TEXT,
                actor_role TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                resource_name TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_username)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)
        """)
        conn.commit()
    
    def log(
        self,
        action: AuditAction,
        actor_id: Optional[int] = None,
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
            action: The action being performed
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
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        details_json = json.dumps(details) if details else None
        
        cursor.execute("""
            INSERT INTO audit_logs 
            (actor_id, actor_username, actor_role, action, resource_type, 
             resource_id, resource_name, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (actor_id, actor_username, actor_role, action.value if isinstance(action, AuditAction) else action, 
              resource_type, resource_id, resource_name, details_json, ip_address, user_agent))
        
        conn.commit()
        log_id = cursor.lastrowid
        
        logger.info(f"Audit: {action} by {actor_username or 'system'} on {resource_type}/{resource_id}")
        return log_id
    
    def get_logs(
        self,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
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
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        
        if actor_username:
            query += " AND actor_username = ?"
            params.append(actor_username)
        
        if action:
            query += " AND action LIKE ?"
            params.append(f"{action}%")
        
        if resource_type:
            query += " AND resource_type = ?"
            params.append(resource_type)
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            entry = dict(zip(columns, row))
            if entry.get('details'):
                try:
                    entry['details'] = json.loads(entry['details'])
                except:
                    pass
            result.append(entry)
        
        return result
    
    def get_log_count(
        self,
        actor_username: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None
    ) -> int:
        """Get total count of logs matching filters."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) FROM audit_logs WHERE 1=1"
        params = []
        
        if actor_username:
            query += " AND actor_username = ?"
            params.append(actor_username)
        
        if action:
            query += " AND action LIKE ?"
            params.append(f"{action}%")
        
        if resource_type:
            query += " AND resource_type = ?"
            params.append(resource_type)
        
        cursor.execute(query, params)
        return cursor.fetchone()[0]


# Singleton instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get or create the audit service singleton."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service
