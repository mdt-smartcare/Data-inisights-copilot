"""
Dependency injection for FastAPI routes.
Provides reusable dependencies for authentication, services, etc.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import get_settings
from backend.core.security import get_token_username
from backend.models.schemas import User
from backend.sqliteDb.db import get_db_service

# Re-export from core.permissions for convenience
from backend.core.permissions import (
    UserRole,
    require_role,
    require_at_least,
    require_super_admin,
    require_admin,
    require_editor,
    require_user,
    get_current_user as get_current_user_from_token,
)

settings = get_settings()
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to extract and validate the current user from JWT token.
    
    Args:
        credentials: Bearer token from Authorization header
    
    Returns:
        User object with username and role
    
    Raises:
        HTTPException: If token is invalid or user not found
    """
    token = credentials.credentials
    username = get_token_username(token)
    
    # Verify user exists in database
    db_service = get_db_service()
    user_data = db_service.get_user_by_username(username)
    
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in system"
        )
    
    if not user_data.get('is_active'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive"
        )
    
    return User(
        username=username,
        role=user_data.get('role', 'user'),
        id=user_data.get('id'),
        email=user_data.get('email'),
        full_name=user_data.get('full_name')
    )
