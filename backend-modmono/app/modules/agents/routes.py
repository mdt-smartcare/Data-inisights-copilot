"""
API routes for agent management.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth.permissions import (
    get_current_user, require_role, require_admin,
    require_editor, can_manage_agents
)
from app.core.exceptions import AppException
from app.modules.users.schemas import User
from app.modules.agents.service import AgentService
from app.modules.agents.schemas import (
    Agent, AgentCreate, AgentUpdate, AgentWithConfig, AgentListResponse,
    UserAgentAccess, UserAgentResponse,
    SystemPromptCreate, SystemPromptResponse,
    PromptConfigCreate, PromptConfigResponse,
    ChunkingConfig, EmbeddingConfig, RAGConfig, LLMConfig,
)


router = APIRouter()


# ==========================================
# Helper Functions
# ==========================================

def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    """Dependency: Get agent service instance."""
    return AgentService(db)


async def verify_agent_access(
    agent_id: UUID,
    user: User,
    service: AgentService,
    min_role: str = "user",
) -> None:
    """
    Verify user has access to agent with minimum role.
    
    Raises:
        HTTPException: If user lacks access
    """
    # Super admins and admins have access to all agents
    if can_manage_agents(user):
        return
    
    has_access = await service.user_has_access(user.id, agent_id, min_role)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for agent {agent_id}",
        )


# ==========================================
# Agent CRUD Endpoints
# ==========================================

@router.post("/agents", response_model=Agent, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(require_editor),
    service: AgentService = Depends(get_agent_service),
) -> Agent:
    """
    Create a new agent with default configuration.
    
    Requires EDITOR role or higher.
    Creator is automatically granted admin access to the agent.
    """
    try:
        agent = await service.create_agent(
            agent_data=agent_data,
            created_by=current_user.id,
            initialize_defaults=True,
        )
        return agent
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    query: Optional[str] = Query(None, description="Search in name/description"),
    type: Optional[str] = Query(None, description="Filter by agent type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> AgentListResponse:
    """
    List agents accessible to current user.
    
    - Regular users see only agents they have access to
    - Admins see all agents
    """
    if can_manage_agents(current_user):
        # Admins see all agents
        agents, total = await service.search_agents(
            query=query,
            agent_type=type,
            skip=skip,
            limit=limit,
        )
    else:
        # Regular users see only accessible agents
        agents, total = await service.get_accessible_agents(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
        )
    
    return AgentListResponse(agents=agents, total=total, skip=skip, limit=limit)


@router.get("/agents/search", response_model=AgentListResponse)
async def search_agents(
    query: Optional[str] = Query(None, description="Search term"),
    type: Optional[str] = Query(None, description="Agent type filter"),
    created_by: Optional[UUID] = Query(None, description="Creator user ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    service: AgentService = Depends(get_agent_service),
) -> AgentListResponse:
    """
    Advanced agent search (ADMIN only).
    
    Supports filtering by query, type, and creator.
    """
    agents, total = await service.search_agents(
        query=query,
        agent_type=type,
        created_by=created_by,
        skip=skip,
        limit=limit,
    )
    return AgentListResponse(agents=agents, total=total, skip=skip, limit=limit)


@router.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> Agent:
    """
    Get agent by ID.
    
    User must have access to the agent.
    """
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Verify access
    await verify_agent_access(agent_id, current_user, service)
    
    return agent


@router.get("/agents/{agent_id}/full", response_model=AgentWithConfig)
async def get_agent_with_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> AgentWithConfig:
    """
    Get agent with full active configuration.
    
    Includes active system prompt and all config types.
    User must have access to the agent.
    """
    # Verify access
    await verify_agent_access(agent_id, current_user, service)
    
    agent = await service.get_agent_with_config(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return agent


@router.put("/agents/{agent_id}", response_model=Agent)
async def update_agent(
    agent_id: UUID,
    agent_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> Agent:
    """
    Update agent fields.
    
    User must have editor or admin access to the agent.
    """
    # Verify access (editor or higher)
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    try:
        agent = await service.update_agent(agent_id, agent_data)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> None:
    """
    Delete an agent (cascades to configs and user access).
    
    Requires admin access to the agent or system ADMIN role.
    """
    # Check if user is system admin or has agent admin access
    if not can_manage_agents(current_user):
        await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    deleted = await service.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")


# ==========================================
# User Access Management
# ==========================================

@router.post("/agents/{agent_id}/users", status_code=status.HTTP_201_CREATED)
async def grant_user_access(
    agent_id: UUID,
    access_data: UserAgentAccess,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """
    Grant a user access to an agent.
    
    User must have admin access to the agent.
    """
    # Verify the requester has admin access
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    # Verify agent_id in path matches body
    if access_data.agent_id != agent_id:
        raise HTTPException(status_code=400, detail="Agent ID mismatch")
    
    try:
        await service.grant_access(
            user_id=access_data.user_id,
            agent_id=agent_id,
            role=access_data.role,
            granted_by=current_user.id,
        )
        return {"message": f"Access granted to user {access_data.user_id}"}
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/agents/{agent_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_access(
    agent_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> None:
    """
    Revoke a user's access to an agent.
    
    User must have admin access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    deleted = await service.revoke_access(user_id, agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User access not found")


@router.put("/agents/{agent_id}/users/{user_id}/role")
async def update_user_role(
    agent_id: UUID,
    user_id: UUID,
    role: str = Query(..., description="New role: user, editor, or admin"),
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """
    Update a user's role on an agent.
    
    User must have admin access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    if role not in ["user", "editor", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    updated = await service.update_access_role(user_id, agent_id, role)
    if not updated:
        raise HTTPException(status_code=404, detail="User access not found")
    
    return {"message": f"Role updated to {role}"}


@router.get("/agents/{agent_id}/users", response_model=List[UserAgentResponse])
async def get_agent_users(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> List[UserAgentResponse]:
    """
    Get all users with access to an agent.
    
    User must have editor access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    return await service.get_agent_users(agent_id)


# ==========================================
# Configuration Management
# ==========================================

@router.get("/agents/{agent_id}/config", response_model=PromptConfigResponse)
async def get_agent_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> PromptConfigResponse:
    """
    Get active configuration for an agent.
    
    User must have access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service)
    
    config = await service.get_agent_config(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail="No configuration found for agent")
    
    return config


@router.put("/agents/{agent_id}/config", response_model=PromptConfigResponse)
async def update_agent_config(
    agent_id: UUID,
    config_data: PromptConfigCreate,
    create_version: bool = Query(False, description="Create new prompt version"),
    version: Optional[int] = Query(None, description="Version number if creating new"),
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> PromptConfigResponse:
    """
    Update agent configuration.
    
    User must have editor access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    try:
        config = await service.update_agent_config(
            agent_id=agent_id,
            config_data=config_data,
            create_new_version=create_version,
            version=version,
            created_by=current_user.username,
        )
        return config
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/agents/{agent_id}/config/chunking")
async def get_chunking_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Get chunking configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service)
    
    config = await service.get_config_by_type(agent_id, "chunking")
    if config is None:
        raise HTTPException(status_code=404, detail="Chunking config not found")
    
    return config


@router.put("/agents/{agent_id}/config/chunking")
async def update_chunking_config(
    agent_id: UUID,
    config: ChunkingConfig,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Update chunking configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    return await service.update_config_by_type(
        agent_id, "chunking", config.model_dump()
    )


@router.get("/agents/{agent_id}/config/embedding")
async def get_embedding_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Get embedding configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service)
    
    config = await service.get_config_by_type(agent_id, "embedding")
    if config is None:
        raise HTTPException(status_code=404, detail="Embedding config not found")
    
    return config


@router.put("/agents/{agent_id}/config/embedding")
async def update_embedding_config(
    agent_id: UUID,
    config: EmbeddingConfig,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Update embedding configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    return await service.update_config_by_type(
        agent_id, "embedding", config.model_dump()
    )


@router.get("/agents/{agent_id}/config/rag")
async def get_rag_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Get RAG/retriever configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service)
    
    config = await service.get_config_by_type(agent_id, "retriever")
    if config is None:
        raise HTTPException(status_code=404, detail="RAG config not found")
    
    return config


@router.put("/agents/{agent_id}/config/rag")
async def update_rag_config(
    agent_id: UUID,
    config: RAGConfig,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Update RAG/retriever configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    return await service.update_config_by_type(
        agent_id, "retriever", config.model_dump()
    )


@router.get("/agents/{agent_id}/config/llm")
async def get_llm_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Get LLM configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service)
    
    config = await service.get_config_by_type(agent_id, "llm")
    if config is None:
        raise HTTPException(status_code=404, detail="LLM config not found")
    
    return config


@router.put("/agents/{agent_id}/config/llm")
async def update_llm_config(
    agent_id: UUID,
    config: LLMConfig,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Update LLM configuration for an agent."""
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    return await service.update_config_by_type(
        agent_id, "llm", config.model_dump()
    )


# ==========================================
# System Prompt Management
# ==========================================

@router.post("/agents/{agent_id}/prompts", status_code=status.HTTP_201_CREATED)
async def create_system_prompt(
    agent_id: UUID,
    prompt_data: SystemPromptCreate,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """
    Create a new system prompt version for an agent.
    
    User must have editor access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    try:
        prompt_id = await service.create_system_prompt(
            agent_id=agent_id,
            prompt_data=prompt_data,
            created_by=current_user.username,
        )
        return {"prompt_id": prompt_id, "message": "System prompt created"}
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/agents/{agent_id}/prompts/{prompt_id}/activate")
async def activate_system_prompt(
    agent_id: UUID,
    prompt_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> dict:
    """
    Activate a system prompt (deactivates all others).
    
    User must have editor access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    await service.activate_system_prompt(agent_id, prompt_id)
    return {"message": f"Prompt {prompt_id} activated"}


@router.get("/agents/{agent_id}/prompts/active", response_model=SystemPromptResponse)
async def get_active_prompt(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> SystemPromptResponse:
    """
    Get the active system prompt for an agent.
    
    User must have access to the agent.
    """
    await verify_agent_access(agent_id, current_user, service)
    
    prompt = await service.get_active_prompt(agent_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="No active prompt found")
    
    return prompt
