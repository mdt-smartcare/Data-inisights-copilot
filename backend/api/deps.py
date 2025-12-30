"""
Dependency injection for FastAPI routes.
Provides reusable dependencies for authentication, services, etc.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import get_settings, DEFAULT_USERS
from backend.core.security import get_token_username
from backend.models.schemas import User

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
    
    # Verify user exists in our system (temporary - will be DB later)
    if username not in DEFAULT_USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found in system"
        )
    
    return User(username=username, role="user")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[User]:
    """
    Optional authentication dependency.
    Returns user if authenticated, None otherwise.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
