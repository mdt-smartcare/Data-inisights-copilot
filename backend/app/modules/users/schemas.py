"""
Pydantic schemas for users module API.

Defines request/response models for user operations.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.core.models.auth import Role


# ============================================
# User Schemas
# ============================================

class UserBase(BaseModel):
    """Base user schema with common fields."""
    username: str = Field(..., min_length=3, max_length=100)  # Allow email format as username
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=200)


class UserCreate(UserBase):
    """Schema for creating a new user via OIDC/Keycloak JIT provisioning."""
    role: str = Field(default="user")
    external_id: str = Field(..., description="OIDC subject (sub) claim from Keycloak")
    is_active: bool = Field(default=True)
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate role is one of the allowed values."""
        from app.core.auth.permissions import VALID_ROLES
        if v not in VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
        return v


class UserUpdate(BaseModel):
    """Schema for updating an existing user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=200)
    role: Optional[str] = None
    is_active: Optional[bool] = None
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        """Validate role if provided."""
        if v is not None:
            from app.core.auth.permissions import VALID_ROLES
            if v not in VALID_ROLES:
                raise ValueError(f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
        return v


class User(UserBase):
    """Schema for user responses."""
    id: str
    role: str
    is_active: bool
    external_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, UUID):
            return str(v)
        return v
    
    model_config = {"from_attributes": True}


# Note: Password management schemas removed - handled by Keycloak/OIDC


# ============================================
# User Search & List
# ============================================

class UserSearchParams(BaseModel):
    """Schema for user search parameters."""
    query: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
