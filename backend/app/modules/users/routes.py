"""
User management routes.

Handles user CRUD operations and user search.
Note: Password management is handled by Keycloak/OIDC.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.models.common import BaseResponse, PaginatedResponse
from app.core.auth.permissions import require_admin, require_user, can_manage_users, detect_role_change
from app.modules.audit.helpers import AuditLogger, get_audit_logger
from app.modules.audit.schemas import AuditAction
from app.modules.users.service import UserService
from app.modules.users.schemas import (
    User, UserCreate, UserUpdate
)
from app.modules.agents.service import UserAgentService
from app.modules.agents.schemas import AgentsForUserListResponse

router = APIRouter()


@router.get("", response_model=BaseResponse[PaginatedResponse[User]])
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
    pages = (total + limit - 1) // limit  # Ceiling division
    
    return BaseResponse.ok(data=PaginatedResponse(
        items=users,
        total=total,
        page=skip // limit,
        size=limit,
        pages=pages
    ))


@router.get("/search", response_model=BaseResponse[PaginatedResponse[User]])
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
    pages = (total + limit - 1) // limit  # Ceiling division
    
    return BaseResponse.ok(data=PaginatedResponse(
        items=users,
        total=total,
        page=skip // limit,
        size=limit,
        pages=pages
    ))


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
    
    return BaseResponse.ok(data=user)


@router.post("", response_model=BaseResponse[User], status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    """
    Create a new user.
    
    **Required Permission:** ADMIN
    
    **Note:** This endpoint is not used by the frontend. User creation 
    is handled via Keycloak/OIDC JIT provisioning. Kept for API-based 
    user creation scenarios.
    """
    service = UserService(session)
    user = await service.create_user(data)
    
    return BaseResponse.ok(data=user, message="User created successfully")


@router.put("/{user_id}", response_model=BaseResponse[User])
async def update_user(
    user_id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """
    Update user.
    
    **Required Permission:** ADMIN
    
    **Note:** Only non-null fields will be updated.
    """
    service = UserService(session)
    
    # Get existing user to detect role changes
    existing_user = await service.get_user(user_id)
    old_role = existing_user.role
    
    user = await service.update_user(user_id, data)
    
    # Audit log: Detect role promotion/demotion
    if data.role and data.role != old_role:
        role_change = detect_role_change(old_role, data.role)
        if role_change == "promoted":
            await audit.log(
                action=AuditAction.ROLE_PROMOTED,
                actor=current_user,
                resource_type="user",
                resource_id=str(user.id),
                resource_name=user.username,
                details={
                    "old_role": old_role,
                    "new_role": data.role,
                    "promoted_by": current_user.username
                },
            )
        elif role_change == "demoted":
            await audit.log(
                action=AuditAction.ROLE_DEMOTED,
                actor=current_user,
                resource_type="user",
                resource_id=str(user.id),
                resource_name=user.username,
                details={
                    "old_role": old_role,
                    "new_role": data.role,
                    "demoted_by": current_user.username
                },
            )
    
    return BaseResponse.ok(data=user, message="User updated successfully")


@router.patch("/{user_id}", response_model=BaseResponse[User])
async def patch_user(
    user_id: str,
    data: UserUpdate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """
    Partially update user (PATCH).
    
    **Required Permission:** ADMIN
    
    **Note:** Only provided fields will be updated.
    """
    service = UserService(session)
    
    # Get existing user to detect role changes
    existing_user = await service.get_user(user_id)
    old_role = existing_user.role
    
    user = await service.update_user(user_id, data)
    
    # Audit log: Detect role promotion/demotion
    if data.role and data.role != old_role:
        role_change = detect_role_change(old_role, data.role)
        if role_change == "promoted":
            await audit.log(
                action=AuditAction.ROLE_PROMOTED,
                actor=current_user,
                resource_type="user",
                resource_id=str(user.id),
                resource_name=user.username,
                details={
                    "old_role": old_role,
                    "new_role": data.role,
                    "promoted_by": current_user.username
                },
            )
        elif role_change == "demoted":
            await audit.log(
                action=AuditAction.ROLE_DEMOTED,
                actor=current_user,
                resource_type="user",
                resource_id=str(user.id),
                resource_name=user.username,
                details={
                    "old_role": old_role,
                    "new_role": data.role,
                    "demoted_by": current_user.username
                },
            )
    
    return BaseResponse.ok(data=user, message="User updated successfully")


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
# User Activation/Deactivation
# ============================================

@router.post("/{user_id}/deactivate", response_model=BaseResponse[dict])
async def deactivate_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """
    Deactivate user account.
    
    **Required Permission:** ADMIN
    
    Deactivated users cannot log in but their data is preserved.
    """
    service = UserService(session)
    
    # Get user info for audit logging
    user = await service.get_user(user_id)
    
    await service.deactivate_user(user_id)
    
    # Audit log: Only log if admin/superadmin is being deactivated
    if can_manage_users(user.role):
        await audit.log(
            action=AuditAction.ADMIN_DEACTIVATED,
            actor=current_user,
            resource_type="user",
            resource_id=str(user.id),
            resource_name=user.username,
            details={
                "role": user.role,
                "deactivated_by": current_user.username
            },
        )
    
    return BaseResponse.ok(message="User deactivated successfully")


@router.post("/{user_id}/activate", response_model=BaseResponse[dict])
async def activate_user(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """
    Activate user account.
    
    **Required Permission:** ADMIN
    
    Re-enables a previously deactivated user account.
    """
    service = UserService(session)
    
    # Get user info for audit logging
    user = await service.get_user(user_id)
    
    await service.activate_user(user_id)
    
    # Audit log: Only log if admin/superadmin is being activated
    if can_manage_users(user.role):
        await audit.log(
            action=AuditAction.ADMIN_ACTIVATED,
            actor=current_user,
            resource_type="user",
            resource_id=str(user.id),
            resource_name=user.username,
            details={
                "role": user.role,
                "activated_by": current_user.username
            },
        )
    
    return BaseResponse.ok(message="User activated successfully")


# ============================================
# User Agents
# ============================================

@router.get("/{user_id}/agents", response_model=BaseResponse[AgentsForUserListResponse])
async def get_user_agents(
    user_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    """
    Get all agents a user has access to.
    
    **Required Permission:** ADMIN
    
    Returns a list of agents with the user's role for each agent.
    For super_admin users, returns all agents with admin role.
    """
    from uuid import UUID
    from app.modules.users.repository import UserRepository
    
    # Fetch target user to get their role
    user_repo = UserRepository(session)
    target_user = await user_repo.get_by_id(UUID(user_id))
    target_role = target_user.role if target_user else None
    
    ua_service = UserAgentService(session)
    result = await ua_service.get_user_agents(UUID(user_id), user_role=target_role)
    
    return BaseResponse.ok(data=result)
