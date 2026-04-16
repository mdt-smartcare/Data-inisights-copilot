"""
Authentication and authorization models.

Defines user-related models, roles, and token structures
used throughout the authentication system.
"""
from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from uuid import UUID, uuid4


class Role(str, Enum):
    """
    User role hierarchy.
    
    Roles are ordered by permission level (lowest to highest):
    USER < EDITOR < ADMIN < SUPER_ADMIN
    """
    USER = "user"                    # Can view and query
    EDITOR = "editor"                # Can edit configurations
    ADMIN = "admin"                  # Can manage users and agents
    SUPER_ADMIN = "super_admin"      # Full system access
    
    @classmethod
    def get_hierarchy_level(cls, role: 'Role') -> int:
        """Get numeric level for role comparison."""
        hierarchy = {
            cls.USER: 0,
            cls.EDITOR: 1,
            cls.ADMIN: 2,
            cls.SUPER_ADMIN: 3
        }
        return hierarchy.get(role, -1)
    
    def has_permission(self, required_role: 'Role') -> bool:
        """Check if this role meets the required permission level."""
        return self.get_hierarchy_level(self) >= self.get_hierarchy_level(required_role)


class UserBase(BaseModel):
    """Base user fields shared across create/update/response."""
    username: str = Field(min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(description="User email address")
    full_name: Optional[str] = Field(default=None, max_length=100, description="User's full name")
    is_active: bool = Field(default=True, description="Whether user account is active")


class UserCreate(UserBase):
    """User creation request model for OIDC/Keycloak JIT provisioning."""
    role: Role = Field(default=Role.USER, description="User role")
    external_id: str = Field(description="OIDC subject (sub) claim from Keycloak")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "external_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "role": "user",
                "is_active": True
            }
        }
    )


class UserUpdate(BaseModel):
    """User update request model. All fields optional."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "newemail@example.com",
                "full_name": "John Michael Doe",
                "role": "admin"
            }
        }
    )


class User(UserBase):
    """
    User response model.
    
    Returned by API endpoints. Never includes password.
    """
    id: UUID = Field(default_factory=uuid4, description="Unique user identifier")
    role: Role = Field(description="User role")
    external_id: Optional[str] = Field(default=None, description="OIDC subject (sub) claim from Keycloak")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Account creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Last update timestamp")
    last_login: Optional[datetime] = Field(default=None, description="Last login timestamp")
    
    model_config = ConfigDict(
        from_attributes=True,  # Allow creation from ORM models
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "username": "john_doe",
                "email": "john@example.com",
                "full_name": "John Doe",
                "role": "admin",
                "external_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "is_active": True,
                "created_at": "2026-03-30T12:00:00Z",
                "updated_at": "2026-03-30T14:30:00Z",
                "last_login": "2026-03-30T14:00:00Z"
            }
        }
    )


class TokenData(BaseModel):
    """
    JWT token payload structure.
    
    Used for token creation and validation.
    """
    sub: str = Field(description="Subject (username)")
    user_id: UUID = Field(description="User UUID")
    role: Role = Field(description="User role")
    exp: Optional[datetime] = Field(default=None, description="Expiration time")
    iat: Optional[datetime] = Field(default=None, description="Issued at time")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sub": "john_doe",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "role": "editor",
                "exp": "2026-03-30T16:00:00Z",
                "iat": "2026-03-30T14:00:00Z"
            }
        }
    )


# Note: TokenResponse and LoginRequest removed - authentication handled by Keycloak
# Users authenticate via Keycloak and receive tokens directly from the identity provider