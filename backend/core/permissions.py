"""
Role-based access control dependencies.
"""
from enum import Enum
from typing import List
from fastapi import Depends, HTTPException, status
from backend.core.security import oauth2_scheme
from backend.config import get_settings
from jose import JWTError, jwt
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import User

class UserRole(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    USER = "user"
    VIEWER = "viewer"

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
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role: {current_user.role}"
            )
        return current_user
    return role_checker
