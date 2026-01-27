"""
Role-based access control dependencies.
Defines roles, permission utilities, and FastAPI dependencies.
"""
from enum import Enum
from typing import List, Callable
from functools import wraps
from fastapi import Depends, HTTPException, status
from backend.core.security import oauth2_scheme
from backend.config import get_settings
from jose import JWTError, jwt
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import User


# ============================================
# Role Definitions
# ============================================

class UserRole(str, Enum):
    """
    User roles with descending privilege levels.
    SUPER_ADMIN > EDITOR > USER > VIEWER
    """
    SUPER_ADMIN = "super_admin"
    EDITOR = "editor"
    USER = "user"
    VIEWER = "viewer"


# Role hierarchy for permission checks (higher index = less privilege)
# Role hierarchy for permission checks
ROLE_HIERARCHY = [
    UserRole.SUPER_ADMIN.value,
    UserRole.EDITOR.value,
    UserRole.USER.value,
]


def role_at_least(user_role: str, required_role: str) -> bool:
    """
    Check if user_role has at least the privilege level of required_role.
    Returns True if user_role >= required_role in the hierarchy.
    """
    if user_role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY:
        return False
    return ROLE_HIERARCHY.index(user_role) <= ROLE_HIERARCHY.index(required_role)


# ============================================
# Permission Helpers
# ============================================

def can_manage_users(role: str) -> bool:
    """Super Admin can manage users."""
    return role == UserRole.SUPER_ADMIN.value


def can_view_all_audit_logs(role: str) -> bool:
    """Only Super Admin can view all audit logs."""
    return role == UserRole.SUPER_ADMIN.value


def can_manage_connections(role: str) -> bool:
    """Super Admin can manage database connections."""
    return role == UserRole.SUPER_ADMIN.value


def can_edit_config(role: str) -> bool:
    """Super Admin, Admin, and Editor can edit config (schema, dictionary, prompt)."""
    return role_at_least(role, UserRole.EDITOR.value)


def can_publish_prompt(role: str) -> bool:
    """Only Super Admin can publish prompts."""
    return role == UserRole.SUPER_ADMIN.value


def can_execute_queries(role: str) -> bool:
    """Super Admin, Admin, Editor, and User can execute queries."""
    return role_at_least(role, UserRole.USER.value)


def can_view_config(role: str) -> bool:
    """All authenticated users can view config summary."""
    return role in ROLE_HIERARCHY


# ============================================
# FastAPI Dependencies
# ============================================

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Validate the token and return the current user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    db = get_db_service()
    user_dict = db.get_user_by_username(username)
    if user_dict is None:
        raise credentials_exception
        
    # Remove password hash before creating User model
    if 'password_hash' in user_dict:
        del user_dict['password_hash']
        
    return User(**user_dict)


def require_role(allowed_roles: List[str]):
    """
    Dependency to enforce role-based access control.
    Usage: Depends(require_role([UserRole.SUPER_ADMIN.value, UserRole.EDITOR.value]))
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role: {current_user.role}"
            )
        return current_user
    return role_checker


def require_at_least(min_role: str):
    """
    Dependency to enforce minimum role level.
    Usage: Depends(require_at_least(UserRole.EDITOR.value))
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        if not role_at_least(current_user.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least '{min_role}' role. Your role: {current_user.role}"
            )
        return current_user
    return role_checker


# Convenience dependencies
require_super_admin = require_role([UserRole.SUPER_ADMIN.value])
require_editor = require_at_least(UserRole.EDITOR.value)
require_user = require_at_least(UserRole.USER.value)
