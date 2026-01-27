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
from backend.core.roles import UserRole

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

def require_role(allowed_roles: list[UserRole]):
    """
    Factory for role-based access control dependency.
    
    Usage:
        @router.post("/endpoint", dependencies=[Depends(require_role([UserRole.ADMIN]))])
    """
    def role_checker(user: User = Depends(get_current_user)):
        # Normalize role string to enum or string comparison
        # DB might store 'admin', 'user' etc.
        if user.role not in allowed_roles and user.role != UserRole.ADMIN: 
            # Admin should generally have access to everything, but let's be strict for now 
            # unless allowed_roles explicitly includes it.
            # Actually, let's keep it simple: strict check against allowed list.
            pass

        # Check if user role is in allowed roles
        # allowed_roles is a list of Enum values. user.role is a string.
        if user.role not in [r.value for r in allowed_roles]:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role '{user.role}'"
            )
        return user
    return role_checker
