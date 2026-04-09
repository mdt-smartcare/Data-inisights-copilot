"""
API routes for agents and configurations.

Provides endpoints for:
- Agent CRUD with access control
- Configuration management with versioning
- User access (RBAC)

Note: Data source routes are in app.modules.data_sources.routes
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import (
    get_current_user, require_editor, require_admin, can_manage_agents
)
from app.core.utils.exceptions import AppException
from app.core.utils.logging import get_logger
from app.core.models.common import BaseResponse
from app.modules.users.schemas import User
from app.modules.agents.service import (
    AgentService, AgentConfigService, UserAgentService
)
from app.modules.agents.schemas import (
    # Agent schemas
    AgentCreate, AgentUpdate, AgentResponse, AgentDetailResponse,
    AgentListResponse,
    # Config schemas
    AgentConfigCreate, AgentConfigUpdate, AgentConfigResponse,
    AgentConfigListResponse, AgentConfigHistoryResponse, EmbeddingStatusUpdate,
    # Per-step schemas (named steps)
    DataSourceStepRequest, SchemaSelectionStepRequest, DataDictionaryStepRequest,
    SettingsStepRequest, PromptStepRequest, PublishStepRequest, GeneratePromptResponse,
    # User access schemas
    UserAgentGrantRequest, UserAgentResponse, UserAgentListResponse,
)

logger = get_logger(__name__)


# Create routers
router = APIRouter()
agents_router = APIRouter(prefix="/agents", tags=["agents"])
config_router = APIRouter(prefix="/config", tags=["config"])


# ==========================================
# Dependencies
# ==========================================

def get_agent_service(db: AsyncSession = Depends(get_db)) -> AgentService:
    return AgentService(db)

def get_config_service(db: AsyncSession = Depends(get_db)) -> AgentConfigService:
    return AgentConfigService(db)

def get_user_agent_service(db: AsyncSession = Depends(get_db)) -> UserAgentService:
    return UserAgentService(db)


async def verify_agent_access(
    agent_id: UUID,
    user: User,
    service: AgentService,
    min_role: str = "user",
) -> None:
    """Verify user has agent access with minimum role."""
    if can_manage_agents(user.role):
        return
    
    ua_service = UserAgentService(service.db)
    has_access = await ua_service.has_access(user.id, agent_id, min_role)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions for agent {agent_id}",
        )


# ==========================================
# Agent Endpoints
# ==========================================

@agents_router.post("", response_model=BaseResponse[AgentResponse], status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    current_user: User = Depends(require_editor),
    service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentResponse]:
    """Create a new agent. Creator gets admin access."""
    try:
        agent = await service.create_agent(data, current_user.id)
        return BaseResponse.ok(data=agent)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@agents_router.get("", response_model=BaseResponse[AgentListResponse])
async def list_agents(
    query: Optional[str] = Query(None, description="Search in title/description"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentListResponse]:
    """List agents accessible to current user with their roles."""
    result = await service.list_agents(
        user_id=current_user.id,
        query=query,
        skip=skip,
        limit=limit,
    )
    return BaseResponse.ok(data=result)


@agents_router.get("/search", response_model=BaseResponse[AgentListResponse])
async def search_agents_admin(
    query: Optional[str] = Query(None),
    created_by: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentListResponse]:
    """Search all agents (admin only)."""
    agents, total = await service.search_all_agents(
        query=query,
        created_by=created_by,
        skip=skip,
        limit=limit,
    )
    return BaseResponse.ok(data=AgentListResponse(agents=agents, total=total, skip=skip, limit=limit))


@agents_router.get("/{agent_id}", response_model=BaseResponse[AgentResponse])
async def get_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentResponse]:
    """Get agent by ID."""
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    await verify_agent_access(agent_id, current_user, service)
    return BaseResponse.ok(data=agent)


@agents_router.get("/{agent_id}/detail", response_model=BaseResponse[AgentDetailResponse])
async def get_agent_detail(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentDetailResponse]:
    """Get agent with active configuration."""
    await verify_agent_access(agent_id, current_user, service)
    
    agent = await service.get_agent_detail(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return BaseResponse.ok(data=agent)


@agents_router.put("/{agent_id}", response_model=BaseResponse[AgentResponse])
async def update_agent(
    agent_id: UUID,
    data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentResponse]:
    """Update agent. Requires editor access."""
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    
    try:
        agent = await service.update_agent(agent_id, data)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return BaseResponse.ok(data=agent)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@agents_router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
) -> None:
    """Delete agent. Requires admin access."""
    if not can_manage_agents(current_user.role):
        await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    deleted = await service.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")


# ==========================================
# User Access Endpoints
# ==========================================

@agents_router.post("/{agent_id}/users", response_model=BaseResponse[UserAgentResponse])
async def grant_user_access(
    agent_id: UUID,
    data: UserAgentGrantRequest,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    ua_service: UserAgentService = Depends(get_user_agent_service),
) -> BaseResponse[UserAgentResponse]:
    """Grant user access to agent. Requires admin access."""
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    try:
        result = await ua_service.grant_access(
            user_id=data.user_id,
            agent_id=agent_id,
            role=data.role,
            granted_by=current_user.id,
        )
        return BaseResponse.ok(data=result)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@agents_router.delete("/{agent_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_access(
    agent_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    ua_service: UserAgentService = Depends(get_user_agent_service),
) -> None:
    """Revoke user's access to agent. Requires admin access."""
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    revoked = await ua_service.revoke_access(user_id, agent_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="User access not found")


@agents_router.get("/{agent_id}/users", response_model=BaseResponse[UserAgentListResponse])
async def get_agent_users(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    ua_service: UserAgentService = Depends(get_user_agent_service),
) -> BaseResponse[UserAgentListResponse]:
    """Get users with access to agent. Requires editor access."""
    await verify_agent_access(agent_id, current_user, service, min_role="editor")
    result = await ua_service.get_agent_users(agent_id)
    return BaseResponse.ok(data=result)


# ==========================================
# Agent Config Endpoints
# ==========================================

@config_router.post("/{agent_id}", response_model=BaseResponse[AgentConfigResponse], status_code=status.HTTP_201_CREATED)
async def create_agent_config(
    agent_id: UUID,
    data: AgentConfigCreate,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """Create a new configuration version for an agent."""
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        config = await service.create_config(
            agent_id=agent_id,
            data_source_id=data.data_source_id,
            config_data=data.model_dump(exclude={"agent_id", "data_source_id", "is_active"}),
            is_active=data.is_active,
        )
        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.get("/{agent_id}/active", response_model=BaseResponse[AgentConfigResponse])
async def get_active_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """Get active configuration for an agent."""
    await verify_agent_access(agent_id, current_user, agent_service)
    
    config = await service.get_active_config(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail="No active configuration found")
    return BaseResponse.ok(data=config)


@config_router.get("/{agent_id}/history", response_model=BaseResponse[AgentConfigListResponse])
async def get_config_history(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigListResponse]:
    """Get all configuration versions for an agent."""
    await verify_agent_access(agent_id, current_user, agent_service)
    result = await service.get_config_history(agent_id)
    return BaseResponse.ok(data=result)


@config_router.get("/{agent_id}/history/paginated", response_model=BaseResponse[AgentConfigHistoryResponse])
async def get_config_history_paginated(
    agent_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigHistoryResponse]:
    """Get paginated configuration history with summary fields for table view."""
    await verify_agent_access(agent_id, current_user, agent_service)
    result = await service.get_config_history_paginated(agent_id, page, page_size)
    return BaseResponse.ok(data=result)


@config_router.get("/detail/{config_id}", response_model=BaseResponse[AgentConfigResponse])
async def get_config_by_id(
    config_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
) -> BaseResponse[AgentConfigResponse]:
    """Get configuration by ID."""
    config = await service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return BaseResponse.ok(data=config)


@config_router.put("/{config_id}", response_model=BaseResponse[AgentConfigResponse])
async def update_config(
    config_id: int,
    data: AgentConfigUpdate,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """Update a configuration."""
    # Get config to verify access
    config = await service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="editor")
    
    updated = await service.update_config(config_id, data.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return BaseResponse.ok(data=updated)


@config_router.post("/{config_id}/activate", response_model=BaseResponse[dict], status_code=status.HTTP_200_OK)
async def activate_config(
    config_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[dict]:
    """Activate a configuration (deactivates others)."""
    config = await service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="editor")
    
    await service.activate_config(config_id)
    return BaseResponse.ok(message=f"Configuration {config_id} activated")


@config_router.put("/{config_id}/embedding-status", response_model=BaseResponse[dict])
async def update_embedding_status(
    config_id: int,
    data: EmbeddingStatusUpdate,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[dict]:
    """Update embedding status for a configuration."""
    config = await service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="editor")
    
    await service.update_embedding_status(
        config_id=config_id,
        status=data.status,
        embedding_path=data.embedding_path,
        vector_collection_name=data.vector_collection_name,
    )
    return BaseResponse.ok(message="Embedding status updated")


# ==========================================
# Draft Config Endpoints
# ==========================================

@config_router.get("/{agent_id}/draft", response_model=BaseResponse[Optional[AgentConfigResponse]])
async def get_draft_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[Optional[AgentConfigResponse]]:
    """Get draft configuration for an agent if exists. Returns null data if no draft."""
    await verify_agent_access(agent_id, current_user, agent_service)
    
    draft = await service.get_draft(agent_id)
    return BaseResponse.ok(data=draft)


@config_router.delete("/{agent_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> None:
    """Delete/discard the draft configuration for an agent."""
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    draft = await service.get_draft(agent_id)
    if not draft:
        raise HTTPException(status_code=404, detail="No draft configuration found")
    
    try:
        deleted = await service.delete_draft(draft.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Configuration not found")
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ==========================================
# Per-Step Endpoints (named steps with version_id)
# ==========================================

@config_router.put("/{agent_id}/step/data-source", response_model=BaseResponse[AgentConfigResponse])
async def upsert_data_source_step(
    agent_id: UUID,
    data: DataSourceStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: data-source.
    If version_id provided in body, updates that version.
    If not provided, creates a new draft version.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        config = await service.upsert_data_source_step(
            agent_id, 
            data.data_source_id, 
            version_id=data.version_id
        )
        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.put("/{agent_id}/version/{version_id}/step/schema-selection", response_model=BaseResponse[AgentConfigResponse])
async def upsert_schema_selection_step(
    agent_id: UUID,
    version_id: int,
    data: SchemaSelectionStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: schema-selection.
    Select columns/schema for an existing version.
    
    Uses unified format: { table_name: columns[] }
    For files, the table name is the DuckDB table name.
    For databases, can have multiple tables.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        config = await service.upsert_schema_selection_step(
            version_id,
            selected_schema=data.selected_schema,
        )
        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.put("/{agent_id}/version/{version_id}/step/data-dictionary", response_model=BaseResponse[AgentConfigResponse])
async def upsert_data_dictionary_step(
    agent_id: UUID,
    version_id: int,
    data: DataDictionaryStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: data-dictionary.
    Add data dictionary/context for an existing version.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        config = await service.upsert_data_dictionary_step(version_id, data.data_dictionary)
        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.put("/{agent_id}/version/{version_id}/step/settings", response_model=BaseResponse[AgentConfigResponse])
async def upsert_settings_step(
    agent_id: UUID,
    version_id: int,
    data: SettingsStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: settings.
    Configure embedding, chunking, RAG, LLM for an existing version.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        config = await service.upsert_settings_step(
            version_id,
            embedding_config=data.embedding_config.model_dump() if data.embedding_config else None,
            chunking_config=data.chunking_config.model_dump() if data.chunking_config else None,
            rag_config=data.rag_config.model_dump() if data.rag_config else None,
            llm_config=data.llm_config.model_dump() if data.llm_config else None,
            llm_model_id=data.llm_model_id,
            embedding_model_id=data.embedding_model_id,
            reranker_model_id=data.reranker_model_id,
        )
        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.put("/{agent_id}/version/{version_id}/step/prompt", response_model=BaseResponse[AgentConfigResponse])
async def upsert_prompt_step(
    agent_id: UUID,
    version_id: int,
    data: PromptStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: prompt.
    Configure system prompt and example questions for an existing version.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        config = await service.upsert_prompt_step(version_id, data.system_prompt, data.example_questions)
        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.post("/{agent_id}/version/{version_id}/step/generate-prompt", response_model=BaseResponse[GeneratePromptResponse])
async def generate_prompt(
    agent_id: UUID,
    version_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[GeneratePromptResponse]:
    """
    Step: generate-prompt.
    Generate a system prompt based on saved config data (data dictionary, settings).
    This reads from the database and uses LLM to generate a production-ready prompt.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        result = await service.generate_prompt(version_id)
        return BaseResponse.ok(data=GeneratePromptResponse(**result))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ==========================================
# Version Management Endpoints
# ==========================================

@config_router.put("/{agent_id}/version/{version_id}/step/publish", response_model=BaseResponse[AgentConfigResponse])
async def upsert_publish_step(
    agent_id: UUID,
    version_id: int,
    data: PublishStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: publish.
    Save final system prompt and example questions, then publish the configuration.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        published = await service.upsert_publish_step(
            version_id,
            system_prompt=data.system_prompt,
            example_questions=data.example_questions,
        )
        return BaseResponse.ok(data=published)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.delete("/{agent_id}/version/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    agent_id: UUID,
    version_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> None:
    """Delete/discard a version."""
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        deleted = await service.delete_draft(version_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Version not found")
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.get("/{agent_id}/version/{version_id}", response_model=BaseResponse[AgentConfigResponse])
async def get_version(
    agent_id: UUID,
    version_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """Get a specific version."""
    await verify_agent_access(agent_id, current_user, agent_service)
    
    config = await service.get_config(version_id)
    if not config:
        raise HTTPException(status_code=404, detail="Version not found")
    
    return BaseResponse.ok(data=config)


@config_router.post("/{config_id}/clone", response_model=BaseResponse[AgentConfigResponse], status_code=status.HTTP_201_CREATED)
async def clone_config_as_draft(
    config_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """Create a draft by cloning an existing published configuration."""
    config = await service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="editor")
    
    try:
        draft = await service.create_draft_from_config(config_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return BaseResponse.ok(data=draft)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ==========================================
# Include all routers
# ==========================================

router.include_router(agents_router)
router.include_router(config_router)
