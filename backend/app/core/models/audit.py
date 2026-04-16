"""
Audit logging models.

Defines audit events and actions for comprehensive activity tracking
across the system.
"""
from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


class AuditAction(str, Enum):
    """
    Comprehensive audit action enumeration.
    
    Covers all auditable events across the system for compliance
    and security monitoring.
    """
    # Authentication & Authorization
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_LOGIN_FAILED = "user.login_failed"
    TOKEN_REFRESH = "token.refresh"
    PASSWORD_CHANGE = "password.change"
    PASSWORD_RESET = "password.reset"
    
    # User Management
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_ACTIVATE = "user.activate"
    USER_DEACTIVATE = "user.deactivate"
    USER_ROLE_CHANGE = "user.role_change"
    
    # Agent Management
    AGENT_CREATE = "agent.create"
    AGENT_UPDATE = "agent.update"
    AGENT_DELETE = "agent.delete"
    AGENT_ASSIGN = "agent.assign_user"
    AGENT_UNASSIGN = "agent.unassign_user"
    AGENT_BULK_ASSIGN = "agent.bulk_assign"
    
    # Agent Configuration
    CONFIG_CHUNKING_UPDATE = "config.chunking_update"
    CONFIG_PII_UPDATE = "config.pii_update"
    CONFIG_MEDICAL_CONTEXT_UPDATE = "config.medical_context_update"
    CONFIG_VECTOR_STORE_UPDATE = "config.vector_store_update"
    CONFIG_RAG_UPDATE = "config.rag_update"
    CONFIG_EMBEDDING_UPDATE = "config.embedding_update"
    CONFIG_LLM_UPDATE = "config.llm_update"
    
    # System Prompts
    PROMPT_GENERATE = "prompt.generate"
    PROMPT_PUBLISH = "prompt.publish"
    PROMPT_UPDATE = "prompt.update"
    PROMPT_ROLLBACK = "prompt.rollback"
    PROMPT_DELETE = "prompt.delete"
    
    # Embedding & Vector Operations
    EMBEDDING_JOB_START = "embedding.job_start"
    EMBEDDING_JOB_COMPLETE = "embedding.job_complete"
    EMBEDDING_JOB_FAIL = "embedding.job_fail"
    EMBEDDING_JOB_CANCEL = "embedding.job_cancel"
    VECTOR_DB_INGEST = "vector_db.ingest"
    VECTOR_DB_DELETE = "vector_db.delete"
    VECTOR_DB_SEARCH = "vector_db.search"
    
    # Query Operations
    QUERY_EXECUTE = "query.execute"
    SQL_EXECUTE = "sql.execute"
    RAG_QUERY = "rag.query"
    INTENT_ROUTED = "intent.routed"
    
    # Data Management
    FILE_UPLOAD = "file.upload"
    FILE_DELETE = "file.delete"
    DATABASE_CONNECT = "database.connect"
    DATABASE_DISCONNECT = "database.disconnect"
    TABLE_INGEST = "table.ingest"
    
    # System Operations
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    CACHE_INVALIDATE = "cache.invalidate"
    SETTINGS_UPDATE = "settings.update"
    MIGRATION_RUN = "migration.run"
    
    # Feedback & Quality
    FEEDBACK_SUBMIT = "feedback.submit"
    FEEDBACK_UPDATE = "feedback.update"
    
    # Monitoring & Observability
    NOTIFICATION_SEND = "notification.send"
    ALERT_CREATE = "alert.create"
    TRACE_CREATE = "trace.create"


class AuditEvent(BaseModel):
    """
    Audit event model.
    
    Captures comprehensive information about system activities
    for compliance, security, and debugging purposes.
    """
    id: Optional[UUID] = Field(default=None, description="Audit event UUID")
    action: AuditAction = Field(description="Type of action performed")
    
    # Actor information (who performed the action)
    actor_id: Optional[UUID] = Field(default=None, description="ID of user who performed action")
    actor_username: Optional[str] = Field(default=None, description="Username of actor")
    actor_role: Optional[str] = Field(default=None, description="Role of actor at time of action")
    
    # Resource information (what was affected)
    resource_type: Optional[str] = Field(default=None, description="Type of resource affected")
    resource_id: Optional[str] = Field(default=None, description="ID of affected resource")
    resource_name: Optional[str] = Field(default=None, description="Name of affected resource")
    
    # Context information
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional event details")
    ip_address: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client user agent")
    request_id: Optional[str] = Field(default=None, description="Request correlation ID")
    
    # Status & timing
    status: str = Field(default="success", description="Action status (success/failure)")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    
    # Timestamps
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "action": "agent.create",
                "actor_id": "abc-123",
                "actor_username": "admin_user",
                "actor_role": "admin",
                "resource_type": "agent",
                "resource_id": "agent-456",
                "resource_name": "Medical Q&A Agent",
                "details": {
                    "agent_type": "medical",
                    "embedding_model": "bge-base-en-v1.5"
                },
                "ip_address": "192.168.1.100",
                "request_id": "req-789",
                "status": "success",
                "timestamp": "2026-03-30T12:00:00Z"
            }
        }
    )


class AuditEventCreate(BaseModel):
    """
    Audit event creation request.
    
    Used by services to log audit events.
    """
    action: AuditAction
    actor_id: Optional[UUID] = None
    actor_username: Optional[str] = None
    actor_role: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    status: str = "success"
    error_message: Optional[str] = None


class AuditQueryParams(BaseModel):
    """Query parameters for audit log retrieval."""
    action: Optional[AuditAction] = Field(default=None, description="Filter by action type")
    actor_id: Optional[UUID] = Field(default=None, description="Filter by actor")
    resource_type: Optional[str] = Field(default=None, description="Filter by resource type")
    resource_id: Optional[str] = Field(default=None, description="Filter by resource ID")
    start_date: Optional[datetime] = Field(default=None, description="Filter from date")
    end_date: Optional[datetime] = Field(default=None, description="Filter to date")
    status: Optional[str] = Field(default=None, description="Filter by status")
    page: int = Field(default=0, ge=0, description="Page number")
    size: int = Field(default=50, ge=1, le=1000, description="Page size")
