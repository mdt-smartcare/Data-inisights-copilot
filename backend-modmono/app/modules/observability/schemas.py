"""
Pydantic schemas for observability module API.

Defines request/response models for audit logs and system monitoring.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


# ============================================
# Audit Log Schemas
# ============================================

class AuditLogCreate(BaseModel):
    """Schema for creating audit log entries."""
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


class AuditLog(BaseModel):
    """Schema for audit log responses."""
    id: int
    timestamp: datetime
    actor_id: Optional[str]
    actor_username: Optional[str]
    actor_role: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    resource_name: Optional[str]
    details: Optional[str]  # JSON string
    ip_address: Optional[str]
    user_agent: Optional[str]
    
    model_config = {"from_attributes": True}


class AuditLogQueryParams(BaseModel):
    """Schema for audit log query parameters."""
    actor_id: Optional[str] = None
    actor_username: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


# ============================================
# System Health Schemas
# ============================================

class SystemHealth(BaseModel):
    """Schema for system health status."""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    components: Dict[str, str]  # component_name -> status
    message: Optional[str] = None
