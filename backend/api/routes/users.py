"""
User Management API endpoints.
Provides CRUD operations for user accounts.

With OIDC/Keycloak integration:
- Users are created automatically on first login (JIT provisioning)
- This API manages local user attributes (role, active status)
- User creation with password is deprecated (handled by Keycloak)

Only accessible by Admin role.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import require_admin, User
from backend.core.logging import get_logger
from backend.core.roles import get_all_roles, is_valid_role
from backend.services.audit_service import get_audit_service, AuditAction

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


class UserUpdateRequest(BaseModel):
    """Request to update a user."""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = Field(None, description="Role: admin, user")
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """User information response."""
    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: Optional[str] = None
    external_id: Optional[str] = Field(None, description="OIDC subject claim from IdP")


@router.get("", response_model=List[UserResponse], dependencies=[Depends(require_admin)])
async def list_users(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    List all users in the system.
    
    Returns all users that have been provisioned (via OIDC or legacy).
    
    **Requires Admin role.**
    """
    users = db_service.list_all_users()
    return users


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def get_user(
    user_id: int,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get a specific user by ID.
    
    **Requires Admin role.**
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, full_name, role, is_active, created_at 
        FROM users 
        WHERE id = ?
    """, (user_id,))
    
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: User = Depends(require_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Update a user's profile or role.
    
    **Requires Admin role.**
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    # Get current user
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    columns = [desc[0] for desc in cursor.description]
    existing_user = dict(zip(columns, row))
    
    # Build update query
    updates = []
    params = []
    
    if request.email is not None:
        updates.append("email = ?")
        params.append(request.email)
    
    if request.full_name is not None:
        updates.append("full_name = ?")
        params.append(request.full_name)
    
    if request.role is not None:
        # Validate role using centralized role config
        if not is_valid_role(request.role):
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {get_all_roles()}")
        updates.append("role = ?")
        params.append(request.role)
    
    if request.is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if request.is_active else 0)
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)
    conn.commit()
    
    # Log audit event
    audit = get_audit_service()
    audit.log(
        action=AuditAction.USER_UPDATE,
        actor_id=current_user.id,
        actor_username=current_user.username,
        actor_role=current_user.role,
        resource_type="user",
        resource_id=str(user_id),
        resource_name=existing_user['username'],
        details=request.model_dump(exclude_unset=True)
    )
    
    # Return updated user
    return await get_user(user_id, db_service)


@router.post("/{user_id}/deactivate", dependencies=[Depends(require_admin)])
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Deactivate a user (soft delete).
    
    Deactivated users cannot authenticate even with valid Keycloak tokens.
    
    **Requires Admin role.**
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    # Get user to delete
    cursor.execute("SELECT username, role FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    username, role = row
    
    # Prevent self-deletion
    if current_user.username == username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    # Soft delete (deactivate)
    cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    
    # Log audit event
    audit = get_audit_service()
    audit.log(
        action=AuditAction.USER_DEACTIVATE,
        actor_id=current_user.id,
        actor_username=current_user.username,
        actor_role=current_user.role,
        resource_type="user",
        resource_id=str(user_id),
        resource_name=username
    )
    
    return {"status": "success", "message": f"User '{username}' has been deactivated"}


@router.post("/{user_id}/activate", dependencies=[Depends(require_admin)])
async def activate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Reactivate a deactivated user account.
    
    **Requires Admin role.**
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    # Get user to activate
    cursor.execute("SELECT username, is_active FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    username, is_active = row
    
    if is_active:
        return {"status": "success", "message": f"User '{username}' is already active"}
    
    # Activate user
    cursor.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
    conn.commit()
    
    # Log audit event
    audit = get_audit_service()
    audit.log(
        action=AuditAction.USER_UPDATE,
        actor_id=current_user.id,
        actor_username=current_user.username,
        actor_role=current_user.role,
        resource_type="user",
        resource_id=str(user_id),
        resource_name=username,
        details={"is_active": True, "action": "activate"}
    )
    
    logger.info(f"User {user_id} ({username}) activated by {current_user.username}")
    return {"status": "success", "message": f"User '{username}' has been activated"}
