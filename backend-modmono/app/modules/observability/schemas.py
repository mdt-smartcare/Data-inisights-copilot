"""
Pydantic schemas for audit log API.

Defines request/response models for audit logs.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel


class AuditAction(str, Enum):
    """Types of auditable actions."""
    # User Management
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DEACTIVATE = "user.deactivate"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_ROLE_SYNC = "user.role.sync"
    
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
    
    # Agent Management
    AGENT_CREATE = "agent.create"
    AGENT_UPDATE = "agent.update"
    AGENT_DELETE = "agent.delete"
    AGENT_USER_ASSIGN = "agent.user.assign"
    AGENT_USER_REVOKE = "agent.user.revoke"


class AuditLogCreate(BaseModel):
    """Schema for creating audit log entries (internal use)."""
    actor_id: Optional[str] = None
    actor_username: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogResponse(BaseModel):
    """Schema for audit log responses."""
    id: int
    timestamp: datetime
    actor_id: Optional[str] = None
    actor_username: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    model_config = {"from_attributes": True}


class AuditLogCountResponse(BaseModel):
    """Schema for audit log count response."""
    count: int
