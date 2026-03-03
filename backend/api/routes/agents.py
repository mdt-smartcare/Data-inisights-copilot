import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.permissions import require_user, get_current_user, require_admin, require_super_admin
from backend.core.roles import Role
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import User
from backend.services.audit_service import get_audit_service, AuditAction

router = APIRouter(tags=["Agents"])
logger = logging.getLogger(__name__)


# --- Helper Functions ---
def resolve_user_id(db, current_user: User) -> Optional[int]:
    """Resolve the user ID from current_user, falling back to database lookup."""
    if current_user.id:
        return current_user.id
    user_record = db.get_user_by_username(current_user.username)
    return user_record['id'] if user_record else None


def check_agent_admin_access(db, agent_id: int, current_user: User) -> bool:
    """
    Check if current user has admin access to a specific agent.
    - Super admin: always has access
    - Admin: must have 'admin' per-agent role OR be the creator
    """
    if current_user.role == Role.SUPER_ADMIN.value:
        return True
    
    user_id = resolve_user_id(db, current_user)
    if not user_id:
        return False
    
    # Check if user has admin per-agent role
    agents = db.get_agents_for_admin(user_id)
    for agent in agents:
        if agent['id'] == agent_id and agent.get('user_role') == 'admin':
            return True
    return False


# --- Schemas ---
class AgentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    type: str
    db_connection_uri: Optional[str] = None
    created_at: Optional[str] = None
    user_role: Optional[str] = None # Role of the current user for this agent

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    type: str = "sql"
    db_connection_uri: Optional[str] = None # Optional, normally created by svc or admin
    system_prompt: Optional[str] = None

# --- Routes ---

@router.get("", response_model=List[AgentResponse])
async def list_agents(current_user: User = Depends(require_user)):
    """
    List all agents available to the current user.
    
    - Super Admin: sees ALL agents with admin access to all
    - Admin: sees agents they created OR are assigned to (per-agent role determines access)
    - User: sees only assigned agents (chat only)
    """
    db = get_db_service()
    try:
        user_id = resolve_user_id(db, current_user)
        if not user_id:
            return []

        # Fetch agents based on system role
        if current_user.role == Role.SUPER_ADMIN.value:
            # Super admin sees all agents with admin access to all
            agents = db.list_all_agents()
            # Inject user_role='admin' for super admin (full access)
            for a in agents:
                a['user_role'] = 'admin'
        elif current_user.role == Role.ADMIN.value:
            # Admin sees created + assigned agents with per-agent role preserved
            agents = db.get_agents_for_admin(user_id)
        else:
            # Regular user sees only assigned agents
            agents = db.get_agents_for_user(user_id)
        
        # Clean up response
        results = []
        for a in agents:
            results.append({
                "id": a['id'],
                "name": a['name'],
                "description": a.get('description'),
                "type": a.get('type', 'sql'),
                "db_connection_uri": a.get('db_connection_uri'),
                "created_at": a.get('created_at'),
                "user_role": a.get('user_role')
            })
            
        return results
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=AgentResponse)
async def create_agent(agent: AgentCreate, current_user: User = Depends(require_admin)):
    """
    Create a new agent (Admin only).
    """
    db = get_db_service()
    try:
        user_id = resolve_user_id(db, current_user)

        new_agent = db.create_agent(
            name=agent.name,
            description=agent.description,
            agent_type=agent.type,
            db_connection_uri=agent.db_connection_uri,
            system_prompt=agent.system_prompt,
            created_by=user_id
        )
        
        # Automatically assign the creator as admin of the new agent (per-agent role)
        if user_id and new_agent.get('id'):
            db.assign_user_to_agent(
                agent_id=new_agent['id'],
                user_id=user_id,
                role='admin',
                granted_by=user_id
            )
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.AGENT_CREATE,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="agent",
            resource_id=str(new_agent.get('id')),
            resource_name=agent.name,
            details={"type": agent.type, "description": agent.description}
        )

        new_agent['user_role'] = 'admin'
        return new_agent
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all", response_model=List[AgentResponse], deprecated=True)
async def list_all_agents(current_user: User = Depends(require_super_admin)):
    """
    List ALL agents (Super Admin only).
    
    DEPRECATED: Use GET /agents instead - super admins see all agents automatically.
    """
    db = get_db_service()
    agents = db.list_all_agents()
    for a in agents:
        a['user_role'] = 'admin'
    return agents


class AgentAssignment(BaseModel):
    user_id: int
    role: str = "user"


@router.get("/{agent_id}/users")
async def get_agent_users(agent_id: int, current_user: User = Depends(require_admin)):
    """
    Get all users assigned to an agent.
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    users = db.get_agent_users(agent_id)
    return {"users": users, "agent_id": agent_id}

@router.post("/{agent_id}/users")
async def assign_user(agent_id: int, assignment: AgentAssignment, current_user: User = Depends(require_admin)):
    """
    Assign a user to an agent.
    - Super admin can assign with any per-agent role (admin or user)
    - Admin can only assign with per-agent role = 'user' (chat access only)
    - User-role targets can only receive 'user' per-agent role (chat access)
    
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    # Enforce: admins can only assign 'user' per-agent role
    if current_user.role != Role.SUPER_ADMIN.value and assignment.role == "admin":
        raise HTTPException(
            status_code=403, 
            detail="Only super admin can grant admin access to agents. Admin can only assign chat-only access."
        )
    
    # Enforce: user-role targets can only receive 'user' per-agent role
    target_user = db.get_user_by_id(assignment.user_id)
    if target_user and target_user.get('role') == 'user' and assignment.role == 'admin':
        raise HTTPException(
            status_code=400,
            detail="Cannot grant configure access to user-role users. Only admin-role users can have configure access."
        )
    
    granter_id = resolve_user_id(db, current_user)

    success = db.assign_user_to_agent(
        agent_id=agent_id,
        user_id=assignment.user_id,
        role=assignment.role,
        granted_by=granter_id
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to assign user to agent")
    
    # Log audit event
    audit = get_audit_service()
    audit.log(
        action=AuditAction.AGENT_USER_ASSIGN,
        actor_id=current_user.id,
        actor_username=current_user.username,
        actor_role=current_user.role,
        resource_type="agent",
        resource_id=str(agent_id),
        details={
            "assigned_user_id": assignment.user_id,
            "assigned_user_name": target_user.get('username') if target_user else None,
            "per_agent_role": assignment.role
        }
    )
    
    return {"status": "success", "message": f"User {assignment.user_id} assigned to agent {agent_id}"}

@router.delete("/{agent_id}/users/{user_id}")
async def revoke_access(agent_id: int, user_id: int, current_user: User = Depends(require_admin)):
    """
    Revoke a user's access to an agent.
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    # Get target user info for audit log
    target_user = db.get_user_by_id(user_id)
    
    success = db.revoke_user_access(agent_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Assignment not found or failed to delete")
    
    # Log audit event
    audit = get_audit_service()
    audit.log(
        action=AuditAction.AGENT_USER_REVOKE,
        actor_id=current_user.id,
        actor_username=current_user.username,
        actor_role=current_user.role,
        resource_type="agent",
        resource_id=str(agent_id),
        details={
            "revoked_user_id": user_id,
            "revoked_user_name": target_user.get('username') if target_user else None
        }
    )
    
    return {"status": "success", "message": f"User {user_id} removed from agent {agent_id}"}


class BulkAgentAssignment(BaseModel):
    user_id: int
    agent_ids: List[int]
    role: str = "user"


@router.post("/bulk-assign")
async def bulk_assign_agents(assignment: BulkAgentAssignment, current_user: User = Depends(require_admin)):
    """
    Assign multiple agents to a user at once.
    - Super admin can assign any agent with any per-agent role
    - Admin can only assign agents they have admin access to, with role = 'user' only
    - User-role targets can only receive 'user' per-agent role
    """
    db = get_db_service()
    
    # Enforce: admins can only assign 'user' per-agent role
    if current_user.role != Role.SUPER_ADMIN.value and assignment.role == "admin":
        raise HTTPException(
            status_code=403, 
            detail="Only super admin can grant admin access to agents. Admin can only assign chat-only access."
        )
    
    # Enforce: user-role targets can only receive 'user' per-agent role
    target_user = db.get_user_by_id(assignment.user_id)
    if target_user and target_user.get('role') == 'user' and assignment.role == 'admin':
        raise HTTPException(
            status_code=400,
            detail="Cannot grant configure access to user-role users. Only admin-role users can have configure access."
        )
    
    granter_id = resolve_user_id(db, current_user)

    assigned = []
    failed = []
    unauthorized = []
    
    for agent_id in assignment.agent_ids:
        # Check authorization for each agent
        if not check_agent_admin_access(db, agent_id, current_user):
            unauthorized.append(agent_id)
            continue
            
        try:
            success = db.assign_user_to_agent(
                agent_id=agent_id,
                user_id=assignment.user_id,
                role=assignment.role,
                granted_by=granter_id
            )
            if success:
                assigned.append(agent_id)
            else:
                failed.append(agent_id)
        except Exception as e:
            logger.error(f"Failed to assign agent {agent_id} to user {assignment.user_id}: {e}")
            failed.append(agent_id)
    
    # Log audit event for bulk assignment
    if assigned:
        audit = get_audit_service()
        audit.log(
            action=AuditAction.AGENT_USER_ASSIGN,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="agent",
            resource_id="bulk",
            details={
                "assigned_user_id": assignment.user_id,
                "assigned_user_name": target_user.get('username') if target_user else None,
                "per_agent_role": assignment.role,
                "agent_ids": assigned,
                "failed_agent_ids": failed,
                "unauthorized_agent_ids": unauthorized if 'unauthorized' in dir() else []
            }
        )
    
    response = {
        "status": "success",
        "assigned": assigned,
        "failed": failed,
        "message": f"Assigned {len(assigned)} agents to user {assignment.user_id}"
    }
    
    if unauthorized:
        response["unauthorized"] = unauthorized
        response["message"] += f" ({len(unauthorized)} skipped - no admin access)"
    
    return response
