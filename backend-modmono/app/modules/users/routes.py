"""
User management routes.

Handles user CRUD operations, password management, and user search.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.models.common import BaseResponse, PaginatedResponse
from app.core.auth.permissions import require_admin, require_user, get_current_user
from app.modules.users.service import UserService
from app.modules.users.schemas import (
    User, UserCreate, UserUpdate, UserSearchParams,
    PasswordChangeRequest, PasswordResetRequest
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[User])
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_user)
):
    """
    List all users with pagination.
    
    **Required Permission:** USER (any authenticated user)
    """
    service = UserService(session)
    users = await service.list_users(skip=skip, limit=limit)
    total = await service.repository.count()
    
    return PaginatedResponse(
        status="success",
        message=f"Retrieved {len(users)} users",
        data=users,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/search", response_model=PaginatedResponse[User])
async def search_users(
    query: str = Query(default=None, description="Search query (username, email, or name)"),
    role: str = Query(default=None, description="Filter by role"),
    is_active: bool = Query(default=None, description="Filter by active status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_user)
):
    """
    Search users with filters.
    
    **Required Permission:** USER (any authenticated user)
    
    **Filters:**
    - query: Search in username, email, or full name
    - role: Filter by specific role
    - is_active: Filter by active/inactive status
    """
    service = UserService(session)
    users, total = await service.search_users(
        query=query,
        role=role,
        is_active=is_active,
        skip=skip,
        limit=limit
    )
    
    return PaginatedResponse(
        status="success",
        message=f"Found {total} matching users",
        data=users,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{user_id}", response_model=BaseResponse[User])
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_user)
):
    """
    Get user by ID.
    
    **Required Permission:** USER (any authenticated user)
    """
    service = UserService(session)
    user = await service.get_user(user_id)
    
    return BaseResponse(
        status="success",
        message="User retrieved",
        data=user
    )


@router.post("", response_model=BaseResponse[User], status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Create a new user.
    
    **Required Permission:** ADMIN
    
    **Note:** Password must be at least 8 characters.
    """
    service = UserService(session)
    user = await service.create_user(data)
    
    return BaseResponse(
        status="success",
        message="User created successfully",
        data=user
    )


@router.put("/{user_id}", response_model=BaseResponse[User])
async def update_user(
    user_id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Update user.
    
    **Required Permission:** ADMIN
    
    **Note:** Only non-null fields will be updated.
    """
    service = UserService(session)
    user = await service.update_user(user_id, data)
    
    return BaseResponse(
        status="success",
        message="User updated successfully",
        data=user
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Delete user.
    
    **Required Permission:** ADMIN
    
    **Warning:** This permanently deletes the user.
    """
    service = UserService(session)
    await service.delete_user(user_id)


# ============================================
# Password Management
# ============================================

@router.post("/{user_id}/change-password", response_model=BaseResponse[dict])
async def change_password(
    user_id: str,
    data: PasswordChangeRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Change user password.
    
    **Permission:** Users can change their own password, admins can change any user's password.
    
    **Note:** Requires current password for verification (unless admin).
    """
    # Users can only change their own password
    if current_user.id != user_id:
        from app.core.auth.permissions import can_manage_users
        if not can_manage_users(current_user.role):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change password for other users"
            )
    
    service = UserService(session)
    await service.change_password(
        user_id=user_id,
        current_password=data.current_password,
        new_password=data.new_password
    )
    
    return BaseResponse(
        status="success",
        message="Password changed successfully",
        data={}
    )


@router.post("/{user_id}/reset-password", response_model=BaseResponse[dict])
async def reset_password(
    user_id: str,
    data: PasswordResetRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Admin password reset (no current password required).
    
    **Required Permission:** ADMIN
    
    **Use case:** When user forgets password and admin needs to reset it.
    """
    service = UserService(session)
    await service.reset_password(user_id, data.new_password)
    
    return BaseResponse(
        status="success",
        message="Password reset successfully",
        data={}
    )


# ============================================
# User Activation/Deactivation
# ============================================

@router.post("/{user_id}/deactivate", response_model=BaseResponse[dict])
async def deactivate_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Deactivate user account.
    
    **Required Permission:** ADMIN
    
    Deactivated users cannot log in but their data is preserved.
    """
    service = UserService(session)
    await service.deactivate_user(user_id)
    
    return BaseResponse(
        status="success",
        message="User deactivated successfully",
        data={}
    )


@router.post("/{user_id}/activate", response_model=BaseResponse[dict])
async def activate_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin)
):
    """
    Activate user account.
    
    **Required Permission:** ADMIN
    
    Re-enables a previously deactivated user account.
    """
    service = UserService(session)
    await service.activate_user(user_id)
    
    return BaseResponse(
        status="success",
        message="User activated successfully",
        data={}
    )
