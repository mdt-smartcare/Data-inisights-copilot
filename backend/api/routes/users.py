"""
User Management API endpoints.
Provides CRUD operations for user accounts.

With OIDC/Keycloak integration:
- Users are created automatically on first login (JIT provisioning)
- This API manages local user attributes (role, active status)
- User creation with password is deprecated (handled by Keycloak)

Access levels:
- Super Admin: Can edit/deactivate admins and users, promote to any role
- Admin: Can only assign agents to users (via agents API), cannot edit/deactivate
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.database.db import get_db_service, DatabaseService
from backend.core.permissions import require_admin, require_super_admin, User
from backend.core.logging import get_logger
from backend.core.roles import get_all_roles, is_valid_role, Role, role_at_least
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


@router.get("/search", response_model=List[UserResponse], dependencies=[Depends(require_admin)])
async def search_users(
    q: str = "",
    limit: int = 20,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Search users by username or email.
    
    - **q**: Search query (matches username or email)
    - **limit**: Maximum number of results (default 20)
    
    **Requires Admin role.**
    """
    users = db_service.search_users(query=q, limit=limit)
    return users


class EmailLookupRequest(BaseModel):
    """Request to lookup users by email addresses."""
    emails: List[str] = Field(..., description="List of email addresses to look up")


@router.post("/lookup-by-emails", response_model=List[UserResponse], dependencies=[Depends(require_admin)])
async def lookup_users_by_emails(
    request: EmailLookupRequest,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Look up users by a list of email addresses.
    
    Returns users that match the provided emails. Invalid/non-existent emails are ignored.
    
    **Requires Admin role.**
    """
    users = db_service.get_users_by_emails(request.emails)
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
        WHERE id = %s
    """, (user_id,))
    
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Update a user's profile or role.
    
    **Requires Super Admin role.**
    
    Role restrictions:
    - Cannot edit other super_admin users
    - Cannot promote users to super_admin (must be done via Keycloak)
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    # Get target user
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    columns = [desc[0] for desc in cursor.description]
    existing_user = dict(zip(columns, row))
    
    # Prevent editing other super_admins
    if existing_user['role'] == Role.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=403, 
            detail="Cannot edit super_admin users. Super admin role is managed via identity provider."
        )
    
    # Prevent promotion to super_admin
    if request.role == Role.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=403, 
            detail="Cannot promote users to super_admin. Super admin role must be assigned via identity provider."
        )
    
    # Build update query
    updates = []
    params = []
    
    if request.email is not None:
        updates.append("email = %s")
        params.append(request.email)
    
    if request.full_name is not None:
        updates.append("full_name = %s")
        params.append(request.full_name)
    
    if request.role is not None:
        # Validate role using centralized role config
        if not is_valid_role(request.role):
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {get_all_roles()}")
        updates.append("role = %s")
        params.append(request.role)
        
        # Clean up per-agent roles when demoting from admin to user
        # Users with system role 'user' cannot have per-agent role 'admin'
        if existing_user['role'] == Role.ADMIN.value and request.role == Role.USER.value:
            cursor.execute("""
                UPDATE user_agents SET role = 'user' 
                WHERE user_id = %s AND role = 'admin'
            """, (user_id,))
            logger.info(f"Downgraded per-agent roles for user {user_id} (demoted from admin to user)")
    
    if request.is_active is not None:
        updates.append("is_active = %s")
        params.append(1 if request.is_active else 0)
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
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


@router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Deactivate a user (soft delete).
    
    Deactivated users cannot authenticate even with valid Keycloak tokens.
    
    **Requires Super Admin role.**
    
    Cannot deactivate other super_admin users.
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    # Get user to deactivate
    cursor.execute("SELECT username, role FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    username, role = row
    
    # Prevent self-deactivation
    if current_user.username == username:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
    
    # Prevent deactivating other super_admins
    if role == Role.SUPER_ADMIN.value:
        raise HTTPException(
            status_code=403, 
            detail="Cannot deactivate super_admin users. Super admin accounts are managed via identity provider."
        )
    
    # Soft delete (deactivate)
    cursor.execute("UPDATE users SET is_active = 0 WHERE id = %s", (user_id,))
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


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: int,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Reactivate a deactivated user account.
    
    **Requires Super Admin role.**
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    
    # Get user to activate
    cursor.execute("SELECT username, is_active FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    username, is_active = row
    
    if is_active:
        return {"status": "success", "message": f"User '{username}' is already active"}
    
    # Activate user
    cursor.execute("UPDATE users SET is_active = 1 WHERE id = %s", (user_id,))
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


@router.get("/{user_id}/agents", dependencies=[Depends(require_admin)])
async def get_user_agents(
    user_id: int,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get all agents assigned to a specific user.
    
    Returns agents with their per-agent role (admin = configure, user = chat only).
    
    **Requires Admin role.**
    """
    # Get user to validate they exist
    conn = db_service.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    target_user_id, username, role = row
    
    # Super admin has access to all agents
    if role == Role.SUPER_ADMIN.value:
        all_agents = db_service.list_all_agents()
        # Super admin has admin (configure) access to all
        for a in all_agents:
            a['user_role'] = 'admin'
        return {"agents": all_agents, "role": role}
    
    # Admin users: return agents they created + assigned (with per-agent roles)
    if role == Role.ADMIN.value:
        agents = db_service.get_agents_for_admin(target_user_id)
        return {"agents": agents, "role": role}
    
    # Regular users: return only assigned agents
    agents = db_service.get_agents_for_user(target_user_id)
    return {"agents": agents, "role": role}
