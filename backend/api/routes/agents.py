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
def check_agent_admin_access(db, agent_id: int, current_user: User) -> bool:
    """
    Check if current user has admin access to a specific agent.
    - Super admin: always has access
    - Admin: must have 'admin' per-agent role in user_agents table
    """
    if current_user.role == Role.SUPER_ADMIN.value:
        return True
    
    user_id = current_user.id
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

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

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
        user_id = current_user.id
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
    Creator is automatically assigned as admin of the new agent.
    """
    db = get_db_service()
    try:
        user_id = current_user.id

        new_agent = db.create_agent(
            name=agent.name,
            description=agent.description,
            agent_type=agent.type,
            db_connection_uri=agent.db_connection_uri,
            system_prompt=agent.system_prompt,
            created_by=user_id
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


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: int, agent_update: AgentUpdate, current_user: User = Depends(require_admin)):
    """
    Update an agent's name and/or description.
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    try:
        updated_agent = db.update_agent(
            agent_id=agent_id,
            name=agent_update.name,
            description=agent_update.description
        )
        
        if not updated_agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.AGENT_UPDATE,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="agent",
            resource_id=str(agent_id),
            resource_name=updated_agent.get('name'),
            details={"name": agent_update.name, "description": agent_update.description}
        )
        
        return updated_agent
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: int, current_user: User = Depends(require_admin)):
    """
    Delete an agent and all related data (cascade deletion).
    
    This will permanently delete:
    - All user assignments (user_agents)
    - All prompts and configurations (system_prompts, prompt_configs)
    - All vector database entries (vector_db_registry, schedules, indexes)
    - Audit log references will be nullified
    
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    # Get agent details for audit log before deletion
    agent = db.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_name = agent.get('name')
    
    try:
        deleted = db.delete_agent(agent_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.AGENT_DELETE,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="agent",
            resource_id=str(agent_id),
            resource_name=agent_name,
            details={"cascade": True}
        )
        
        return None
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
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
    
    granter_id = current_user.id

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


# --- Embedding Configuration Schemas ---
class AgentEmbeddingConfigResponse(BaseModel):
    agent_id: int
    provider: str
    model_name: str
    model_path: Optional[str] = None
    dimension: int
    batch_size: int
    collection_name: str
    last_embedded_at: Optional[str] = None
    document_count: int = 0
    requires_reindex: bool = False


class AgentEmbeddingConfigUpdate(BaseModel):
    provider: str  # 'bge-m3', 'openai', 'sentence-transformers'
    model_name: str  # e.g., 'BAAI/bge-m3', 'text-embedding-3-small'
    dimension: int  # e.g., 1024, 1536
    model_path: Optional[str] = None  # For local models
    batch_size: int = 128


class AgentEmbeddingHistoryResponse(BaseModel):
    previous_provider: Optional[str]
    previous_model: Optional[str]
    previous_dimension: Optional[int]
    new_provider: str
    new_model: str
    new_dimension: int
    change_reason: Optional[str]
    changed_by: Optional[str]
    changed_at: str
    reindex_triggered: bool
    reindex_job_id: Optional[str]


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
    
    granter_id = current_user.id

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


# =============================================================================
# Agent Embedding Configuration Endpoints
# =============================================================================

@router.get("/{agent_id}/embedding", response_model=AgentEmbeddingConfigResponse)
async def get_agent_embedding_config(agent_id: int, current_user: User = Depends(require_admin)):
    """
    Get the embedding model configuration for an agent.
    
    Returns the agent's configured embedding provider, model, dimension,
    and collection information.
    
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    # Verify agent exists
    agent = db.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    try:
        from backend.services.agent_embedding_service import get_agent_embedding_service
        agent_embedding_svc = get_agent_embedding_service()
        config = agent_embedding_svc.get_agent_embedding_config(agent_id)
        return config
    except Exception as e:
        logger.error(f"Error getting embedding config for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{agent_id}/embedding", response_model=AgentEmbeddingConfigResponse)
async def update_agent_embedding_config(
    agent_id: int,
    config: AgentEmbeddingConfigUpdate,
    current_user: User = Depends(require_admin)
):
    """
    Update the embedding model configuration for an agent.
    
    Changing the embedding model will:
    - Create a new vector collection for the agent
    - Mark the agent as requiring reindexing
    - Log the change in embedding history
    
    **Important**: After changing the embedding model, you must reindex
    the agent's documents to use the new model.
    
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    # Verify agent exists
    agent = db.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Validate provider
    valid_providers = ['bge-m3', 'openai', 'sentence-transformers']
    if config.provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider. Must be one of: {valid_providers}"
        )
    
    try:
        from backend.services.agent_embedding_service import get_agent_embedding_service
        agent_embedding_svc = get_agent_embedding_service()
        
        result = agent_embedding_svc.set_agent_embedding_config(
            agent_id=agent_id,
            provider=config.provider,
            model_name=config.model_name,
            dimension=config.dimension,
            model_path=config.model_path,
            batch_size=config.batch_size,
            updated_by=current_user.username
        )
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.AGENT_UPDATE,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="agent",
            resource_id=str(agent_id),
            resource_name=agent.get('name'),
            details={
                "action": "embedding_config_update",
                "provider": config.provider,
                "model_name": config.model_name,
                "dimension": config.dimension,
                "requires_reindex": result.get("requires_reindex", False)
            }
        )
        
        # Return updated config
        return agent_embedding_svc.get_agent_embedding_config(agent_id)
        
    except Exception as e:
        logger.error(f"Error updating embedding config for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/embedding/history", response_model=List[AgentEmbeddingHistoryResponse])
async def get_agent_embedding_history(
    agent_id: int,
    limit: int = 10,
    current_user: User = Depends(require_admin)
):
    """
    Get the embedding model change history for an agent.
    
    Returns a list of past embedding model changes, including
    when the model was changed, by whom, and whether reindexing was triggered.
    
    Requires admin access to the specific agent.
    """
    db = get_db_service()
    
    # Verify current user has admin access to this agent
    if not check_agent_admin_access(db, agent_id, current_user):
        raise HTTPException(
            status_code=403,
            detail="You don't have admin access to this agent"
        )
    
    # Verify agent exists
    agent = db.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    try:
        from backend.services.agent_embedding_service import get_agent_embedding_service
        agent_embedding_svc = get_agent_embedding_service()
        history = agent_embedding_svc.get_embedding_history(agent_id, limit=limit)
        return history
    except Exception as e:
        logger.error(f"Error getting embedding history for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/embedding/reindex-required")
async def list_agents_requiring_reindex(current_user: User = Depends(require_admin)):
    """
    List all agents that require reindexing due to embedding model changes.
    
    Returns agents where the embedding model was changed but documents
    have not yet been reindexed with the new model.
    
    Super Admin sees all agents; Admin sees only their agents.
    """
    db = get_db_service()
    
    try:
        from backend.services.agent_embedding_service import get_agent_embedding_service
        agent_embedding_svc = get_agent_embedding_service()
        
        all_requiring_reindex = agent_embedding_svc.list_agents_requiring_reindex()
        
        # Filter based on user access
        if current_user.role == Role.SUPER_ADMIN.value:
            return {"agents": all_requiring_reindex}
        
        # For admin, filter to only agents they have access to
        user_id = current_user.id
        user_agents = db.get_agents_for_admin(user_id) if user_id else []
        user_agent_ids = {a['id'] for a in user_agents if a.get('user_role') == 'admin'}
        
        filtered = [a for a in all_requiring_reindex if a['agent_id'] in user_agent_ids]
        return {"agents": filtered}
        
    except Exception as e:
        logger.error(f"Error listing agents requiring reindex: {e}")
        raise HTTPException(status_code=500, detail=str(e))
