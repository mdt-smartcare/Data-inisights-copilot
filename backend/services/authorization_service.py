"""
Authorization service for enhanced RBAC enforcement.
Provides Admin-only access control for RAG operations.
"""
from typing import Optional, List
from datetime import datetime
import json

from fastapi import HTTPException, status, Request

from backend.models.schemas import User
from backend.models.rag_models import RAGAuditAction
from backend.core.roles import Role
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service

logger = get_logger(__name__)


class AuthorizationService:
    """
    Service for enforcing role-based access control on RAG operations.
    
    Key responsibilities:
    - Check if users have required roles for RAG operations
    - Log unauthorized access attempts to audit trail
    - Provide helper methods for common authorization checks
    """
    
    def __init__(self):
        self.db = get_db_service()
    
    def require_admin(self, user: User, action: str = None) -> None:
        """
        Verify user has Admin role. Raises 403 if not.
        
        Args:
            user: The user to check
            action: Optional action description for audit logging
            
        Raises:
            HTTPException: 403 Forbidden if user is not Admin
        """
        if user.role != Role.ADMIN.value:
            # Log unauthorized attempt
            self._log_unauthorized_attempt(user, action or "rag_access")
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Access Denied",
                    "message": "This feature is only available to Admin users.",
                    "your_role": user.role,
                    "required_role": Role.ADMIN.value,
                    "action": action
                }
            )
    
    # Backward compatibility alias
    require_super_admin = require_admin
    
    def check_rag_access(self, user: User, action: str) -> bool:
        """
        Check if user can perform a specific RAG action.
        
        Args:
            user: The user to check
            action: The RAG action being requested
            
        Returns:
            True if user has permission, False otherwise
        """
        # All RAG configuration actions require Admin
        rag_actions_requiring_admin = [
            "wizard_access",
            "schema_select",
            "dictionary_upload",
            "embedding_generate",
            "config_publish",
            "config_rollback",
            "embedding_cancel"
        ]
        
        if action in rag_actions_requiring_admin:
            return user.role == Role.ADMIN.value
        
        # Read-only actions for Admin and above
        rag_read_actions = [
            "config_view",
            "embedding_status",
            "audit_view"
        ]
        
        if action in rag_read_actions:
            return user.role == Role.ADMIN.value
        
        return False
    
    def can_access_rag_wizard(self, user: User) -> bool:
        """Check if user can access the RAG configuration wizard."""
        return user.role == Role.ADMIN.value
    
    def can_generate_embeddings(self, user: User) -> bool:
        """Check if user can trigger embedding generation."""
        return user.role == Role.ADMIN.value
    
    def can_publish_config(self, user: User) -> bool:
        """Check if user can publish RAG configurations."""
        return user.role == Role.ADMIN.value
    
    def can_rollback_config(self, user: User) -> bool:
        """Check if user can rollback to previous configurations."""
        return user.role == Role.ADMIN.value
    
    def can_view_config_status(self, user: User) -> bool:
        """Check if user can view config status (read-only)."""
        return user.role in [UserRole.SUPER_ADMIN.value, UserRole.EDITOR.value]
    
    def _log_unauthorized_attempt(
        self, 
        user: User, 
        action: str,
        request: Optional[Request] = None
    ) -> None:
        """
        Log unauthorized access attempt to the RAG audit log.
        
        Args:
            user: The user who attempted access
            action: The action that was attempted
            request: Optional request object for IP/user-agent
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
            
            cursor.execute("""
                INSERT INTO rag_audit_log 
                (action, performed_by, performed_by_email, performed_by_role, 
                 ip_address, user_agent, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                RAGAuditAction.UNAUTHORIZED_ACCESS.value,
                user.id,
                user.email or user.username,
                user.role,
                ip_address,
                user_agent,
                0,  # success = False
                f"Unauthorized attempt to access: {action}"
            ))
            
            conn.commit()
            conn.close()
            
            logger.warning(
                f"Unauthorized access attempt: user={user.username}, "
                f"role={user.role}, action={action}"
            )
            
        except Exception as e:
            logger.error(f"Failed to log unauthorized attempt: {e}")
    
    def log_rag_action(
        self,
        user: User,
        action: RAGAuditAction,
        config_id: Optional[int] = None,
        changes: Optional[dict] = None,
        reason: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        request: Optional[Request] = None
    ) -> int:
        """
        Log a RAG-related action to the audit trail.
        
        Args:
            user: The user performing the action
            action: The action being performed
            config_id: Optional related configuration ID
            changes: Optional dict of changes being made
            reason: Optional reason/justification for the action
            success: Whether the action succeeded
            error_message: Error message if action failed
            request: Optional request object for context
            
        Returns:
            The ID of the created audit log entry
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
            
            changes_json = json.dumps(changes) if changes else None
            
            cursor.execute("""
                INSERT INTO rag_audit_log 
                (config_id, action, performed_by, performed_by_email, performed_by_role, 
                 ip_address, user_agent, changes, reason, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config_id,
                action.value if isinstance(action, RAGAuditAction) else action,
                user.id,
                user.email or user.username,
                user.role,
                ip_address,
                user_agent,
                changes_json,
                reason,
                1 if success else 0,
                error_message
            ))
            
            conn.commit()
            log_id = cursor.lastrowid
            conn.close()
            
            logger.info(
                f"RAG audit log: action={action}, user={user.username}, "
                f"success={success}, config_id={config_id}"
            )
            
            return log_id
            
        except Exception as e:
            logger.error(f"Failed to log RAG action: {e}")
            return -1
    
    def get_rag_audit_logs(
        self,
        config_id: Optional[int] = None,
        action: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """
        Query RAG audit logs with optional filters.
        
        Args:
            config_id: Filter by configuration ID
            action: Filter by action type
            user_id: Filter by user ID
            limit: Maximum results to return
            offset: Pagination offset
            
        Returns:
            List of audit log entries as dicts
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM rag_audit_log WHERE 1=1"
        params = []
        
        if config_id is not None:
            query += " AND config_id = ?"
            params.append(config_id)
        
        if action:
            query += " AND action = ?"
            params.append(action)
        
        if user_id is not None:
            query += " AND performed_by = ?"
            params.append(user_id)
        
        query += " ORDER BY performed_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            entry = dict(zip(columns, row))
            if entry.get('changes'):
                try:
                    entry['changes'] = json.loads(entry['changes'])
                except:
                    pass
            result.append(entry)
        
        return result


# Singleton instance
_authorization_service: Optional[AuthorizationService] = None


def get_authorization_service() -> AuthorizationService:
    """Get or create the authorization service singleton."""
    global _authorization_service
    if _authorization_service is None:
        _authorization_service = AuthorizationService()
    return _authorization_service
