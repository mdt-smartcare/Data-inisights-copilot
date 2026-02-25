import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.permissions import require_user, get_current_user, require_admin
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import User

router = APIRouter(tags=["Agents"])
logger = logging.getLogger(__name__)

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
    """
    db = get_db_service()
    try:
        # We need the user's ID. 
        # current_user is a Pydantic model from schemas.py.
        # It might not have ID if loaded from token without DB lookup.
        # But let's assume valid user.
        
        # We need to resolve username to ID if ID is missing
        user_id = current_user.id
        if not user_id:
            u = db.get_user_by_username(current_user.username)
            if u:
                user_id = u['id']
            else:
                return []

        agents = db.get_agents_for_user(user_id)
        
        # Clean up response
        results = []
        for a in agents:
            results.append({
                "id": a['id'],
                "name": a['name'],
                "description": a.get('description'),
                "type": a.get('type', 'sql'),
                "db_connection_uri": a.get('db_connection_uri'), # Maybe hide this for non-admins?
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
        # Resolve user ID
        user_id = current_user.id
        if not user_id:
             u = db.get_user_by_username(current_user.username)
             user_id = u['id'] if u else None

        new_agent = db.create_agent(
            name=agent.name,
            description=agent.description,
            agent_type=agent.type,
            db_connection_uri=agent.db_connection_uri,
            system_prompt=agent.system_prompt,
            created_by=user_id
        )
        # Add user_role for response consistency (creator is admin)
        new_agent['user_role'] = 'admin'
        return new_agent
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/all", response_model=List[AgentResponse])
async def list_all_agents(current_user: User = Depends(require_admin)):
    """
    List ALL agents (Admin only).
    """
    db = get_db_service()
    return db.list_all_agents()

class AgentAssignment(BaseModel):
    user_id: int
    role: str = "user"

@router.post("/{agent_id}/users")
async def assign_user(agent_id: int, assignment: AgentAssignment, current_user: User = Depends(require_admin)):
    """
    Assign a user to an agent (Admin only).
    """
    db = get_db_service()
    
    # Resolve granter ID
    granter_id = current_user.id
    if not granter_id:
         u = db.get_user_by_username(current_user.username)
         granter_id = u['id'] if u else None

    success = db.assign_user_to_agent(
        agent_id=agent_id,
        user_id=assignment.user_id,
        role=assignment.role,
        granted_by=granter_id
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to assign user to agent")
    return {"status": "success", "message": f"User {assignment.user_id} assigned to agent {agent_id}"}

@router.delete("/{agent_id}/users/{user_id}")
async def revoke_access(agent_id: int, user_id: int, current_user: User = Depends(require_admin)):
    """
    Revoke a user's access to an agent (Admin only).
    """
    db = get_db_service()
    success = db.revoke_user_access(agent_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Assignment not found or failed to delete")
    return {"status": "success", "message": f"User {user_id} removed from agent {agent_id}"}

class BulkAgentAssignment(BaseModel):
    user_id: int
    agent_ids: List[int]
    role: str = "user"

@router.post("/bulk-assign")
async def bulk_assign_agents(assignment: BulkAgentAssignment, current_user: User = Depends(require_admin)):
    """
    Assign multiple agents to a user at once (Admin only).
    """
    db = get_db_service()
    
    # Resolve granter ID
    granter_id = current_user.id
    if not granter_id:
        u = db.get_user_by_username(current_user.username)
        granter_id = u['id'] if u else None

    assigned = []
    failed = []
    
    for agent_id in assignment.agent_ids:
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
    
    return {
        "status": "success",
        "assigned": assigned,
        "failed": failed,
        "message": f"Assigned {len(assigned)} agents to user {assignment.user_id}"
    }
