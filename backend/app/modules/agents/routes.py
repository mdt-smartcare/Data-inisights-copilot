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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import (
    get_current_user, require_admin, can_manage_agents, can_manage_users
)
from app.core.utils.exceptions import AppException
from app.core.utils.logging import get_logger
from app.modules.audit.helpers import AuditLogger, get_audit_logger
from app.core.models.common import BaseResponse
from app.modules.audit.schemas import AuditAction
from app.modules.users.schemas import User
from app.modules.users.service import UserService

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
    # Agent Definition (Step 4.5)
    AgentDefinition, AgentDefinitionStepRequest, AgentDefinitionPollResponse,
    BootstrapAgentDefinitionResponse,
    # User access schemas
    UserAgentGrantRequest, UserAgentResponse, UserAgentListResponse,
    BulkAssignAgentsRequest, BulkAssignAgentsResponse,
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

def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


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
    has_access = await ua_service.has_access(user.id, agent_id, min_role, user_role=user.role)
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
    current_user: User = Depends(require_admin),
    service: AgentService = Depends(get_agent_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[AgentResponse]:
    """Create a new agent. Creator gets admin access."""
    try:
        agent = await service.create_agent(data, current_user.id)
        
        # Audit log: agent.created
        await audit.log(
            action=AuditAction.AGENT_CREATED,
            actor=current_user,
            resource_type="agent",
            resource_id=str(agent.id),
            resource_name=agent.title,
            details={
                "description": agent.description,
                "created_by": current_user.username
            },
        )
        
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
        user_role=current_user.role,
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
    """Update agent. Requires admin access."""
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
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
    audit: AuditLogger = Depends(get_audit_logger),
) -> None:
    """Delete agent. Requires admin access."""
    if not can_manage_agents(current_user.role):
        await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    # Get agent info before deletion for audit log
    agent = await service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    deleted = await service.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Audit log: agent.deleted
    await audit.log(
        action=AuditAction.AGENT_DELETED,
        actor=current_user,
        resource_type="agent",
        resource_id=str(agent_id),
        resource_name=agent.title,
        details={
            "deleted_by": current_user.username
        },
    )


# ==========================================
# User Access Endpoints
# ==========================================

@agents_router.post("/bulk-assign", response_model=BaseResponse[BulkAssignAgentsResponse])
async def bulk_assign_agents(
    data: BulkAssignAgentsRequest,
    current_user: User = Depends(require_admin),
    ua_service: UserAgentService = Depends(get_user_agent_service),
    service: AgentService = Depends(get_agent_service),
    audit: AuditLogger = Depends(get_audit_logger),
    db: AsyncSession = Depends(get_db),
) -> BaseResponse[BulkAssignAgentsResponse]:
    """Bulk assign multiple agents to a user. Admin only."""
    from app.modules.users.service import UserService
    
    result = await ua_service.bulk_assign_agents(
        user_id=data.user_id,
        agent_ids=data.agent_ids,
        role=data.role,
        granted_by=current_user.id,
    )
    
    # Audit log
    if result.assigned:
        # Fetch target user info for audit log
        user_service = UserService(db)
        target_user = await user_service.get_user(str(data.user_id))
        
        # Fetch agent details for assigned agents
        assigned_agent_details = []
        for agent_id_str in result.assigned:
            agent = await service.get_agent(UUID(agent_id_str))
            if agent:
                assigned_agent_details.append({
                    "agent_id": agent_id_str,
                    "agent_name": agent.title,
                    "role": data.role
                })
        
        await audit.log(
            action=AuditAction.AGENT_BULK_ASSIGN,
            actor=current_user,
            resource_type="user",
            resource_id=str(data.user_id),
            resource_name=target_user.username if target_user else str(data.user_id),
            details={
                "total_assigned": len(result.assigned),
                "total_failed": len(result.failed),
                "assigned_agents": assigned_agent_details,
                "failed_agent_ids": result.failed,
                "assigned_by": current_user.username
            },
        )
    
    return BaseResponse.ok(data=result)


@agents_router.post("/{agent_id}/users", response_model=BaseResponse[UserAgentResponse])
async def grant_user_access(
    agent_id: UUID,
    data: UserAgentGrantRequest,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    ua_service: UserAgentService = Depends(get_user_agent_service),
    user_service: UserService = Depends(get_user_service),
    audit: AuditLogger = Depends(get_audit_logger),
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
        
        # Audit log: Only log if current user is admin/superadmin
        if can_manage_users(current_user.role):
            agent = await service.get_agent(agent_id)
            user= await user_service.get_user(str(data.user_id))
            await audit.log(
                action=AuditAction.AGENT_ADMIN_ACCESS_GRANTED,
                actor=current_user,
                resource_type="agent",
                resource_id=str(agent_id),
                resource_name=agent.title if agent else str(agent_id),
                details={
                    "user_id": user.id if user else str(data.user_id),
                    "user_name": user.username if user else str(data.user_id),
                    "agent_access_level": data.role,
                    "granted_by": current_user.username
                },
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
    user_service: UserService = Depends(get_user_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> None:
    """Revoke user's access to agent. Requires admin access."""
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    revoked = await ua_service.revoke_access(user_id, agent_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="User access not found")
    
    # Audit log: Only log if current user is admin/superadmin
    if can_manage_users(current_user.role):
        agent = await service.get_agent(agent_id)
        user = await user_service.get_user(str(user_id))
        await audit.log(
            action=AuditAction.AGENT_ADMIN_ACCESS_REVOKED,
            actor=current_user,
            resource_type="agent",
            resource_id=str(agent_id),
            resource_name=agent.title if agent else str(agent_id),
            details={
                "user_id": user.id if user else str(user_id),
                "user_name": user.username if user else str(user_id),
                "revoked_by": current_user.username
            },
        )


@agents_router.get("/{agent_id}/users", response_model=BaseResponse[UserAgentListResponse])
async def get_agent_users(
    agent_id: UUID,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(default=10, ge=1, le=100, description="Items per page"),
    q: str = Query(default=None, description="Search query (username, email, or name)"),
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    ua_service: UserAgentService = Depends(get_user_agent_service),
) -> BaseResponse[UserAgentListResponse]:
    """
    Get users with access to agent. Requires admin access.
    
    **Query Parameters:**
    - page: Page number (1-indexed, default: 1)
    - size: Items per page (default: 10, max: 100)
    - q: Optional search query (searches username, email, full_name)
    """
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    result = await ua_service.get_agent_users(
        agent_id, 
        page=page, 
        size=size, 
        search=q
    )
    return BaseResponse.ok(data=result)


@agents_router.get("/{agent_id}/users/available", response_model=BaseResponse[list[User]])
async def search_available_users_for_agent(
    agent_id: UUID,
    query: str = Query(default=None, description="Search query (username, email, or name)"),
    skip: int = Query(default=0, ge=0, description="Number of results to skip (for pagination)"),
    size: int = Query(default=10, ge=1, le=100, description="Max results per page"),
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    user_service: UserService = Depends(get_user_service),
) -> BaseResponse[list[User]]:
    """
    Search users available for assignment to this agent.
    
    Returns users NOT already assigned to the agent, excluding super_admin users.
    
    **Required Permission:** admin access to the agent
    
    **Query Parameters:**
    - query (or q): Search query (username, email, full_name)
    - skip: Offset for pagination (default: 0)
    - size: Max results per page (default: 10, max: 100)
    """
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    users = await user_service.search_users_for_agent(
        agent_id=agent_id,
        query=query,
        skip=skip,
        limit=size
    )
    
    return BaseResponse.ok(data=users)


@agents_router.post("/{agent_id}/users/lookup-by-emails", response_model=BaseResponse[list[User]])
async def lookup_available_users_by_emails(
    agent_id: UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
    user_service: UserService = Depends(get_user_service),
) -> BaseResponse[list[User]]:
    """
    Lookup users by emails, excluding those already assigned to the agent.
    
    Returns users NOT already assigned to the agent, excluding super_admin users.
    
    **Required Permission:** admin access to the agent
    
    **Request Body:**
    - emails: List of email addresses to look up
    """
    await verify_agent_access(agent_id, current_user, service, min_role="admin")
    
    emails = payload.get("emails", [])
    if not emails or not isinstance(emails, list):
        return BaseResponse.ok(data=[])
    
    users = await user_service.get_users_by_emails_for_agent(
        agent_id=agent_id,
        emails=emails
    )
    
    return BaseResponse.ok(data=users)


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
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[AgentConfigResponse]:
    """Create a new configuration version for an agent."""
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
    try:
        config = await service.create_config(
            agent_id=agent_id,
            data_source_id=data.data_source_id,
            config_data=data.model_dump(exclude={"agent_id", "data_source_id", "is_active"}),
            is_active=data.is_active,
        )
        
        # Audit log: config.created
        agent = await agent_service.get_agent(agent_id)
        await audit.log(
            action=AuditAction.CONFIG_CREATED,
            actor=current_user,
            resource_type="agent_config",
            resource_id=str(config.id),
            resource_name=f"{agent.title if agent else 'Agent'} v{config.version}",
            details={
                "agent_id": str(agent_id),
                "config_version": config.version,
                "created_by": current_user.username
            },
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
    config = await service.get_active_config(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail="No active configuration found")
    return BaseResponse.ok(data=config)


@config_router.get("/{agent_id}/latest-inactive", response_model=BaseResponse[Optional[AgentConfigResponse]])
async def get_latest_inactive_config(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[Optional[AgentConfigResponse]]:
    """Get the latest published config that is NOT active for an agent.
    
    Used to show alerts about newer versions that could be activated.
    Returns null data if there's no inactive published config.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
    config = await service.get_latest_inactive_config(agent_id)
    return BaseResponse.ok(data=config)


@config_router.get("/{agent_id}/history", response_model=BaseResponse[AgentConfigListResponse])
async def get_config_history(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigListResponse]:
    """Get all configuration versions for an agent."""
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
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
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="admin")
    
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
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[dict]:
    """Activate a configuration (deactivates others)."""
    config = await service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="admin")
    
    # Get previous active config for audit log
    previous_active = await service.get_active_config(config.agent_id)
    
    await service.activate_config(config_id)
    
    # Audit log: config.activated
    agent = await agent_service.get_agent(config.agent_id)
    await audit.log(
        action=AuditAction.CONFIG_ACTIVATED,
        actor=current_user,
        resource_type="agent_config",
        resource_id=str(config_id),
        resource_name=f"{agent.title if agent else 'Agent'} v{config.version}",
        details={
            "agent_id": str(config.agent_id),
            "config_version": config.version,
            "previous_active_version": previous_active.version if previous_active and previous_active.id != config_id else None,
            "activated_by": current_user.username
        },
    )
    
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
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="admin")
    
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: data-dictionary.

    Persists the data dictionary, then kicks off the AI Agent Definition
    bootstrap in the background so the user lands on Step 4.5 with fields
    pre-populated.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")

    try:
        config = await service.upsert_data_dictionary_step(version_id, data.data_dictionary)

        # Fire-and-forget bootstrap. Failures inside the task are caught and
        # surfaced via agent_definition_status='failed' on the config row.
        from app.modules.agents.agent_definition_generator import (
            bootstrap_agent_definition_background,
        )
        background_tasks.add_task(bootstrap_agent_definition_background, version_id)

        return BaseResponse.ok(data=config)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@config_router.post(
    "/{agent_id}/version/{version_id}/step/bootstrap-definition",
    response_model=BaseResponse[BootstrapAgentDefinitionResponse],
)
async def bootstrap_agent_definition_route(
    agent_id: UUID,
    version_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[BootstrapAgentDefinitionResponse]:
    """
    Step 4.5: kick off AI Agent Definition bootstrap.

    Idempotent w.r.t. status — if a bootstrap is already pending, we report
    that and skip scheduling another one.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")

    config = await service.configs.get_by_id(version_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")

    current_status = getattr(config, "agent_definition_status", "not_started")
    if current_status == "pending":
        return BaseResponse.ok(data=BootstrapAgentDefinitionResponse(
            status="already_pending",
            version_id=version_id,
            message="Bootstrap is already running.",
        ))

    from app.modules.agents.agent_definition_generator import (
        bootstrap_agent_definition_background,
    )
    background_tasks.add_task(bootstrap_agent_definition_background, version_id)

    return BaseResponse.ok(data=BootstrapAgentDefinitionResponse(
        status="started",
        version_id=version_id,
    ))


@config_router.get(
    "/{agent_id}/version/{version_id}/agent-definition",
    response_model=BaseResponse[AgentDefinitionPollResponse],
)
async def get_agent_definition(
    agent_id: UUID,
    version_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentDefinitionPollResponse]:
    """
    Poll the agent definition status + payload.

    Status values: not_started | pending | completed | failed
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="user")

    config = await service.configs.get_by_id(version_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")

    raw_definition = getattr(config, "agent_definition", None)
    parsed: Optional[AgentDefinition] = None
    if raw_definition:
        try:
            import json as _json
            parsed_dict = _json.loads(raw_definition) if isinstance(raw_definition, str) else raw_definition
            parsed = AgentDefinition.model_validate(parsed_dict)
        except Exception as exc:
            logger.warning(f"Failed to parse persisted agent_definition for v{version_id}: {exc}")

    payload = AgentDefinitionPollResponse(
        status=getattr(config, "agent_definition_status", "not_started"),
        data=parsed,
        error=None,
    )
    return BaseResponse.ok(data=payload)


@config_router.put(
    "/{agent_id}/version/{version_id}/step/agent-definition",
    response_model=BaseResponse[AgentConfigResponse],
)
async def upsert_agent_definition_step(
    agent_id: UUID,
    version_id: int,
    data: AgentDefinitionStepRequest,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step 4.5: persist user-confirmed agent definition.

    On save, sample_questions flagged with use_as_few_shot=true are indexed
    into the agent's few-shot example store so they ground future SQL
    generation.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")

    try:
        config = await service.upsert_agent_definition_step(version_id, data.agent_definition)
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
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: settings.
    Configure embedding, chunking, RAG, LLM for an existing version.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
    try:
        # Determine which sections are being updated
        sections_updated = []
        if data.embedding_config:
            sections_updated.append("embedding")
        if data.chunking_config:
            sections_updated.append("chunking")
        if data.rag_config:
            sections_updated.append("rag")
        if data.llm_config:
            sections_updated.append("llm")
        
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
        
        # Audit log: config.settings_updated
        if sections_updated:
            agent = await agent_service.get_agent(agent_id)
            await audit.log(
                action=AuditAction.CONFIG_SETTINGS_UPDATED,
                actor=current_user,
                resource_type="agent_config",
                resource_id=str(version_id),
                resource_name=f"{agent.title if agent else 'Agent'} v{config.version}",
                details={
                    "agent_id": str(agent_id),
                    "sections": sections_updated,
                    "updated_by": current_user.username
                },
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[AgentConfigResponse]:
    """
    Step: publish.
    Save final system prompt and example questions, then publish the configuration.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
    try:
        published = await service.upsert_publish_step(
            version_id,
            system_prompt=data.system_prompt,
            example_questions=data.example_questions,
        )
        
        # Audit log: config.partially_completed (step 6 - SQL ready, embedding pending)
        agent = await agent_service.get_agent(agent_id)
        await audit.log(
            action=AuditAction.CONFIG_PARTIALLY_COMPLETED,
            actor=current_user,
            resource_type="agent_config",
            resource_id=str(version_id),
            resource_name=f"{agent.title if agent else 'Agent'} v{published.version}",
            details={
                "agent_id": str(agent_id),
                "config_version": published.version,
                "completed_by": current_user.username,
                "status": "sql_ready_embedding_pending"
            },
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    await verify_agent_access(agent_id, current_user, agent_service, min_role="admin")
    
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
    
    await verify_agent_access(config.agent_id, current_user, agent_service, min_role="admin")
    
    try:
        draft = await service.create_draft_from_config(config_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return BaseResponse.ok(data=draft)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ==========================================
# Schema Cache Management
# ==========================================

@config_router.post("/cache/invalidate", response_model=BaseResponse[dict])
async def invalidate_schema_cache(
    source_id: Optional[UUID] = Query(None, description="Specific data source to invalidate, or all if not provided"),
    current_user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[dict]:
    """
    Invalidate schema caches to force refresh on next query.
    
    Use when:
    - Database schema has been modified (new tables, columns)
    - Data dictionary has been updated
    - Experiencing stale schema issues in SQL generation
    
    Requires admin role.
    """
    from app.modules.agents.schema_cache_manager import schema_cache_manager
    
    if source_id:
        callbacks_invoked = schema_cache_manager.invalidate_source(str(source_id))
        message = f"Invalidated schema caches for source {source_id}"
    else:
        callbacks_invoked = schema_cache_manager.invalidate_all()
        message = "Invalidated all schema caches"
    
    # Audit log
    await audit.log(
        action=AuditAction.CONFIG_SETTINGS_UPDATED,
        actor=current_user,
        resource_type="schema_cache",
        resource_id=str(source_id) if source_id else "all",
        resource_name="Schema Cache",
        details={
            "action": "invalidate",
            "source_id": str(source_id) if source_id else None,
            "callbacks_invoked": callbacks_invoked,
        },
    )
    
    logger.info(f"{message} ({callbacks_invoked} cache callbacks invoked) by user {current_user.email}")
    
    return BaseResponse.ok(data={
        "message": message,
        "callbacks_invoked": callbacks_invoked,
    })


@config_router.post("/{agent_id}/version/{version_id}/validate-dictionary", response_model=BaseResponse[dict])
async def validate_data_dictionary(
    agent_id: UUID,
    version_id: int,
    current_user: User = Depends(get_current_user),
    service: AgentConfigService = Depends(get_config_service),
    agent_service: AgentService = Depends(get_agent_service),
) -> BaseResponse[dict]:
    """
    Validate the data dictionary against the actual database schema.
    
    Returns validation errors and warnings for:
    - Tables referenced in data dictionary that don't exist in the database
    - Columns referenced that don't exist in their tables
    - Incorrect FHIR identifier patterns (e.g., using patient_id on patient_gold)
    
    Use this before generating prompts to catch schema-dictionary drift.
    """
    await verify_agent_access(agent_id, current_user, agent_service, min_role="editor")
    
    try:
        validation_result = await service.validate_data_dictionary(version_id)
        return BaseResponse.ok(data=validation_result)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ==========================================
# Include all routers
# ==========================================

router.include_router(agents_router)
router.include_router(config_router)
