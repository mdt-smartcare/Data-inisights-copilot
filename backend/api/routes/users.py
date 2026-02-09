"""
User Management API endpoints.
Only accessible by Super Admin.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import require_super_admin, User
from backend.core.logging import get_logger
from backend.services.audit_service import get_audit_service, AuditAction

logger = get_logger(__name__)

router = APIRouter(prefix="/users", tags=["User Management"])


class UserUpdateRequest(BaseModel):
    """Request to update a user."""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = Field(None, description="Role: super_admin, editor, user, viewer")
    is_active: Optional[bool] = None


class UserCreateRequest(BaseModel):
    """Request to create a new user."""
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = Field("user", description="Role: super_admin, editor, user, viewer")


class UserResponse(BaseModel):
    """User information response."""
    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool = True
    created_at: Optional[str] = None



@router.post("", response_model=UserResponse, dependencies=[Depends(require_super_admin)])
async def create_user(
    request: UserCreateRequest,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Create a new user.
    
    **Requires Super Admin role.**
    """
    try:
        # Validate role
        valid_roles = ['super_admin', 'editor', 'user', 'viewer']
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")
        
        user = db_service.create_user(
            username=request.username,
            password=request.password,
            email=request.email,
            full_name=request.full_name,
            role=request.role
        )
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.USER_CREATE,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="user",
            resource_id=str(user['id']),
            resource_name=user['username'],
            details={"role": request.role}
        )
        
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")


@router.get("", response_model=List[UserResponse], dependencies=[Depends(require_super_admin)])
async def list_users(
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    List all users in the system.
    
    **Requires Super Admin role.**
    """
    conn = db_service.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, email, full_name, role, is_active, created_at 
        FROM users 
        ORDER BY created_at DESC
    """)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    return [dict(zip(columns, row)) for row in rows]


@router.get("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_super_admin)])
async def get_user(
    user_id: int,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get a specific user by ID.
    
    **Requires Super Admin role.**
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


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_super_admin)])
async def update_user(
    user_id: int,
    request: UserUpdateRequest,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Update a user's profile or role.
    
    **Requires Super Admin role.**
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
        # Validate role
        valid_roles = ['super_admin', 'editor', 'user', 'viewer']
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")
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


@router.delete("/{user_id}", dependencies=[Depends(require_super_admin)])
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_super_admin),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Delete a user (soft delete by deactivating).
    
    **Requires Super Admin role.**
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
