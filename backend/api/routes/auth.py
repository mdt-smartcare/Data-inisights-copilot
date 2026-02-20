"""
Authentication routes for OIDC/Keycloak integration.

Note: User registration and login are handled by Keycloak.
This module provides endpoints for:
- Getting the current authenticated user's profile
- User management (role updates) by admins
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from backend.config import get_settings
from backend.models.schemas import User, UserRoleUpdate, UserListResponse
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import (
    get_current_user,
    require_admin,
)
from backend.core.roles import get_all_roles, is_valid_role

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
logger = get_logger(__name__)


@router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get the current authenticated user's profile.
    
    The user is authenticated via Keycloak OIDC token.
    On first access, the user is automatically provisioned in the local database.
    
    Returns:
        User profile including username, email, role, and external_id (Keycloak sub claim)
    """
    return current_user


@router.get("/users", response_model=UserListResponse)
async def list_users(
    current_user: User = Depends(require_admin),
    db: DatabaseService = Depends(get_db_service)
):
    """
    List all users in the system (Admin only).
    
    Returns all users that have been provisioned (either via OIDC or legacy).
    """
    users = db.list_all_users()
    return UserListResponse(users=users)


@router.patch("/users/{user_id}/role", response_model=User)
async def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    current_user: User = Depends(require_admin),
    db: DatabaseService = Depends(get_db_service)
):
    """
    Update a user's role (Admin only).
    
    This allows local role management independent of Keycloak roles.
    The local role takes precedence over Keycloak role claims.
    
    Args:
        user_id: The user's database ID
        role_update: New role to assign
        
    Returns:
        Updated user profile
    """
    # Validate role using centralized role config
    if not is_valid_role(role_update.role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {get_all_roles()}"
        )
    
    # Prevent self-demotion
    if current_user.id == user_id and role_update.role != current_user.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role"
        )
    
    # Update role
    success = db.update_user_role(user_id, role_update.role)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Fetch updated user
    # Note: We need to get user by ID - let's add this to the response
    logger.info(f"User {user_id} role updated to {role_update.role} by {current_user.username}")
    
    return User(
        id=user_id,
        username="",  # Will be filled by caller if needed
        role=role_update.role
    )


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: DatabaseService = Depends(get_db_service)
):
    """
    Deactivate a user account (Admin only).
    
    Deactivated users cannot authenticate even with valid Keycloak tokens.
    """
    # Prevent self-deactivation
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    success = db.deactivate_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    logger.info(f"User {user_id} deactivated by {current_user.username}")
    return {"message": "User deactivated successfully"}


@router.patch("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: DatabaseService = Depends(get_db_service)
):
    """
    Reactivate a user account (Admin only).
    """
    success = db.activate_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    logger.info(f"User {user_id} activated by {current_user.username}")
    return {"message": "User activated successfully"}
