"""
Pydantic schemas for audit log API.

Defines request/response models for audit logs.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel


class AuditAction(str, Enum):
    """Types of auditable actions (24 total)."""
    
    # User Management (5 actions)
    # Only log for admin/superadmin users, not regular users
    ADMIN_REGISTERED = "admin.registered"  # Admin/Superadmin added
    ROLE_PROMOTED = "role.promoted"  # User promoted to Admin/Superadmin
    ROLE_DEMOTED = "role.demoted"  # Admin/Superadmin demoted
    ADMIN_DEACTIVATED = "admin.deactivated"  # Admin/Superadmin disabled
    ADMIN_ACTIVATED = "admin.activated"  # Admin/Superadmin re-enabled
    
    # Agent Management (4 actions)
    AGENT_CREATED = "agent.created"
    AGENT_DELETED = "agent.deleted"
    AGENT_ADMIN_ACCESS_GRANTED = "agent.admin_access_granted"  # Admin/Superadmin assigned
    AGENT_ADMIN_ACCESS_REVOKED = "agent.admin_access_revoked"  # Admin/Superadmin removed
    
    # Agent Config (4 actions)
    CONFIG_CREATED = "config.created"
    CONFIG_SETTINGS_UPDATED = "config.settings_updated"  # Chunking/LLM/RAG/Embedding changed
    CONFIG_ACTIVATED = "config.activated"
    CONFIG_PARTIALLY_COMPLETED = "config.partially_completed"  # Step 6 reached
    
    # Data Source (3 actions)
    DATASOURCE_CREATED = "datasource.created"
    DATASOURCE_UPDATED = "datasource.updated"
    DATASOURCE_DELETED = "datasource.deleted"
    
    # AI Model (4 actions)
    AIMODEL_REGISTERED = "aimodel.registered"
    AIMODEL_UPDATED = "aimodel.updated"
    AIMODEL_DELETED = "aimodel.deleted"
    AIMODEL_SET_AS_DEFAULT = "aimodel.set_as_default"
    
    # Embedding Job (4 actions)
    EMBEDDING_JOB_STARTED = "embedding.job_started"
    EMBEDDING_JOB_COMPLETED = "embedding.job_completed"
    EMBEDDING_JOB_FAILED = "embedding.job_failed"
    EMBEDDING_JOB_CANCELLED = "embedding.job_cancelled"


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
