"""
Business logic for agents and configurations.

Provides:
- AgentService: Agent CRUD with access control
- UserAgentService: User-agent access control
- AgentConfigService: Configuration versioning and updates

Note: DataSourceService is in app.modules.data_sources.service
"""
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.exceptions import AppException, ErrorCode
from app.core.utils.logging import get_logger
from app.core.models.auth import Role
from app.modules.agents.repository import (
    AgentRepository, AgentConfigRepository, UserAgentRepository,
    _config_to_dict
)
from app.modules.users.repository import UserRepository   
from app.modules.agents.schemas import (
    AgentCreate, AgentUpdate, AgentResponse, AgentWithRole,
    AgentDetailResponse, AgentListResponse,
    AgentConfigResponse, AgentConfigListResponse,
    AgentConfigSummary, AgentConfigHistoryResponse,
    UserAgentResponse, UserAgentListResponse, AgentsForUserListResponse,
    BulkAssignAgentsResponse,
)
# Import data source repository for config validation
from app.modules.data_sources.repository import DataSourceRepository
from app.modules.agents.schema_validator import (
    SchemaValidator, 
    ValidationResult, 
    format_validation_report
)
from app.core.utils.logging import get_logger

logger = get_logger(__name__)

logger = get_logger(__name__)


class AgentService:
    """
    Service for agent management.
    
    Handles:
    - Agent CRUD with creator access
    - Agent listing with user roles
    - Agent deletion (cascades to configs)
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.agents = AgentRepository(db)
        self.user_agents = UserAgentRepository(db)
        self.configs = AgentConfigRepository(db)
        self.user= UserRepository(db)
    
    async def create_agent(
        self,
        data: AgentCreate,
        created_by: UUID,
    ) -> AgentResponse:
        """
        Create a new agent.
        
        Automatically grants creator admin access.
        """
        # Check title uniqueness
        existing = await self.agents.get_by_title(data.title)
        if existing:
            raise AppException(
                error_code=ErrorCode.RESOURCE_ALREADY_EXISTS,
                message=f"Agent with title '{data.title}' already exists",
                status_code=409,
            )
        
        # Create agent
        agent_dict = data.model_dump()
        agent_dict["created_by"] = created_by
        agent = await self.agents.create(data)
        
        # Grant creator admin access
        await self.user_agents.grant_access(
            user_id=created_by,
            agent_id=agent.id,
            role="admin",
            granted_by=created_by,
        )
        
        return agent
    
    async def get_agent(self, agent_id: UUID) -> Optional[AgentResponse]:
        """Get agent by ID."""
        return await self.agents.get_by_id(agent_id)
    
    async def get_agent_detail(self, agent_id: UUID) -> Optional[AgentDetailResponse]:
        """Get agent with active configuration."""
        data = await self.agents.get_with_active_config(agent_id)
        if data:
            return AgentDetailResponse(**data)
        return None
    
    async def update_agent(
        self,
        agent_id: UUID,
        data: AgentUpdate,
    ) -> Optional[AgentResponse]:
        """Update agent fields."""
        existing = await self.agents.get_by_id(agent_id)
        if not existing:
            return None
        
        # Check title uniqueness if changing
        if data.title and data.title != existing.title:
            title_exists = await self.agents.get_by_title(data.title)
            if title_exists:
                raise AppException(
                    error_code=ErrorCode.RESOURCE_ALREADY_EXISTS,
                    message=f"Agent with title '{data.title}' already exists",
                    status_code=409,
                )
        
        return await self.agents.update(agent_id, data)
    
    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete agent and all related data."""
        return await self.agents.delete(agent_id)
    
    async def list_agents(
        self,
        user_id: UUID,
        user_role: Optional[str] = None,
        query: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AgentListResponse:
        """
        List agents accessible to user with their roles.
        
        For super_admin users, returns ALL agents with admin role.
        For other users, filters to only show agents they have access to.
        """
        is_super_admin = user_role == Role.SUPER_ADMIN.value
        
        if is_super_admin:
            # Super admin gets ALL agents with admin role
            all_agents, total = await self.agents.search_agents(
                query=query,
                skip=skip,
                limit=limit,
            )
            # Add admin role to all agents for super_admin
            agents = [
                {**a.model_dump(), "user_role": "admin"}
                for a in all_agents
            ]
        else:
            # Regular users only see agents they have access to
            agents, total = await self.agents.get_accessible_agents(
                user_id=user_id,
                skip=skip,
                limit=limit,
            )
            
            # If query provided, filter results
            if query:
                query_lower = query.lower()
                agents = [
                    a for a in agents
                    if query_lower in a.get("title", "").lower() 
                    or query_lower in (a.get("description") or "").lower()
                ]
                total = len(agents)
        
        return AgentListResponse(
            agents=[AgentWithRole(**a) for a in agents],
            total=total,
            skip=skip,
            limit=limit,
        )
    
    async def search_all_agents(
        self,
        query: Optional[str] = None,
        created_by: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AgentResponse], int]:
        """Search all agents (admin only)."""
        return await self.agents.search_agents(
            query=query,
            created_by=created_by,
            skip=skip,
            limit=limit,
        )


class UserAgentService:
    """Service for user-agent access control."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_agents = UserAgentRepository(db)
        self.agents = AgentRepository(db)
        self.user= UserRepository(db)
    
    async def grant_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        role: str = "user",
        granted_by: Optional[UUID] = None,
    ) -> UserAgentResponse:
        """Grant user access to an agent.""" # Verify agent exists
        agent = await self.agents.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent {agent_id} not found",
                status_code=404,
            )
        
        ua = await self.user_agents.grant_access(
            user_id=user_id,
            agent_id=agent_id,
            role=role,
            granted_by=granted_by,
        )
        
        # Fetch user details to build full response
        user = await self.user.get_by_id(user_id)
        
        return UserAgentResponse(
            id=ua.user_id,
            user_id=ua.user_id,
            agent_id=ua.agent_id,
            username=user.username if user else str(user_id),
            email=user.email if user else None,
            full_name=user.full_name if user else None,
            is_active=user.is_active if user else True,
            role=ua.role,
            granted_at=ua.granted_at,
            granted_by=ua.granted_by,
        )
    
    async def revoke_access(self, user_id: UUID, agent_id: UUID) -> bool:
        """Revoke user's access to an agent."""
        return await self.user_agents.revoke_access(user_id, agent_id)
    
    async def has_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        min_role: str = "user",
        user_role: Optional[str] = None,
    ) -> bool:
        """
        Check if user has access with minimum role.
        
        Super admin users always have access to all agents.
        """
        # Super admin always has access
        if user_role == Role.SUPER_ADMIN.value:
            return True
        
        # Check user-agent access and role level
        from app.core.auth.permissions import role_at_least
        access = await self.user_agents.get_access(user_id, agent_id)
        if not access:
            return False
        
        return role_at_least(access.role, min_role)
    
    async def get_agent_users(
        self,
        agent_id: UUID,
        page: int = 1,
        size: int = 10,
        search: Optional[str] = None
    ) -> UserAgentListResponse:
        """Get all users with access to an agent with pagination and search."""
        skip = (page - 1) * size
        users, total = await self.user_agents.get_agent_users(
            agent_id, 
            skip=skip,
            limit=size,
            search=search
        )
        pages = (total + size - 1) // size if total > 0 else 1
        return UserAgentListResponse(
            users=users,
            total=total,
            page=page,
            size=size,
            pages=pages,
            agent_id=agent_id,
        )
    
    async def get_user_agents(self, user_id: UUID, user_role: Optional[str] = None) -> AgentsForUserListResponse:
        """
        Get all agents a user has access to.
        
        Super admin users get all agents with admin role.
        """
        if user_role == Role.SUPER_ADMIN.value:
            # Super admin gets ALL agents with admin role
            all_agents, _ = await self.agents.search_agents(skip=0, limit=1000)
            
            # Build response with admin role for all agents
            from .schemas import AgentForUserResponse
            agents = [
                AgentForUserResponse(
                    id=a.id,
                    title=a.title,
                    description=a.description,
                    created_by=a.created_by,
                    created_at=a.created_at,
                    updated_at=a.updated_at,
                    role="admin",
                    granted_at=a.created_at,  # Implicit access from creation
                    granted_by=None,
                )
                for a in all_agents
            ]
            return AgentsForUserListResponse(
                agents=agents,
                total=len(agents),
                user_id=user_id,
            )
        
        agents = await self.user_agents.get_user_agents_with_details(user_id)
        return AgentsForUserListResponse(
            agents=agents,
            total=len(agents),
            user_id=user_id,
        )
    
    async def bulk_assign_agents(
        self,
        user_id: UUID,
        agent_ids: List[UUID],
        role: str = "user",
        granted_by: Optional[UUID] = None,
    ) -> BulkAssignAgentsResponse:
        """
        Bulk assign multiple agents to a user.
        
        Returns a response with lists of successfully assigned and failed agent IDs.
        """
        assigned: List[str] = []
        failed: List[str] = []
        
        for agent_id in agent_ids:
            try:
                # Verify agent exists
                agent = await self.agents.get_by_id(agent_id)
                if not agent:
                    failed.append(str(agent_id))
                    continue
                
                await self.user_agents.grant_access(
                    user_id=user_id,
                    agent_id=agent_id,
                    role=role,
                    granted_by=granted_by,
                )
                assigned.append(str(agent_id))
            except Exception:
                failed.append(str(agent_id))
        
        message = f"Assigned {len(assigned)} agent(s)"
        if failed:
            message += f", {len(failed)} failed"
        
        return BulkAssignAgentsResponse(
            status="success" if not failed else "partial",
            assigned=assigned,
            failed=failed,
            message=message,
        )


class AgentConfigService:
    """
    Service for agent configuration management.
    
    Handles:
    - Configuration CRUD with versioning
    - Config activation (only one active per agent)
    - Embedding status updates
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.configs = AgentConfigRepository(db)
        self.agents = AgentRepository(db)
        self.sources = DataSourceRepository(db)
    
    async def create_config(
        self,
        agent_id: UUID,
        data_source_id: UUID,
        config_data: Dict[str, Any],
        is_active: bool = True,
    ) -> AgentConfigResponse:
        """
        Create a new configuration for an agent.
        
        Auto-increments version. If is_active=True, deactivates other configs.
        """
        # Verify agent exists
        agent = await self.agents.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent {agent_id} not found",
                status_code=404,
            )
        
        # Verify data source exists
        source = await self.sources.get_by_id(data_source_id)
        if not source:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Data source {data_source_id} not found",
                status_code=404,
            )
        
        config = await self.configs.create(
            agent_id=agent_id,
            data_source_id=data_source_id,
            config_data=config_data,
            is_active=is_active,
        )
        
        return self._to_response(config)
    
    async def get_config(self, config_id: int) -> Optional[AgentConfigResponse]:
        """Get config by ID (with resolved model info)."""
        config = await self.configs.get_by_id(config_id)
        if config:
            return await self._to_response_with_models(config)
        return None
    
    async def get_active_config(self, agent_id: UUID) -> Optional[AgentConfigResponse]:
        """Get the active configuration for an agent (with resolved model info)."""
        config = await self.configs.get_active_config(agent_id)
        if config:
            return await self._to_response_with_models(config)
        return None
    
    async def get_latest_inactive_config(self, agent_id: UUID) -> Optional[AgentConfigResponse]:
        """Get the latest published config that is NOT active for an agent.
        
        Used to show alerts about newer versions that could be activated.
        Returns None if there's no inactive published config.
        """
        config = await self.configs.get_latest_inactive_published(agent_id)
        if config:
            return await self._to_response_with_models(config)
        return None
    
    async def update_config(
        self,
        config_id: int,
        config_data: Dict[str, Any],
    ) -> Optional[AgentConfigResponse]:
        """Update a configuration."""
        config = await self.configs.update(config_id, config_data)
        if config:
            return self._to_response(config)
        return None
    
    async def activate_config(self, config_id: int) -> bool:
        """Activate a config (deactivates others)."""
        return await self.configs.activate_config(config_id)
    
    async def get_config_history(self, agent_id: UUID) -> AgentConfigListResponse:
        """Get all config versions for an agent."""
        configs = await self.configs.get_config_history(agent_id)
        return AgentConfigListResponse(
            configs=[self._to_response(c) for c in configs],
            total=len(configs),
        )
    
    async def get_config_history_paginated(
        self,
        agent_id: UUID,
        page: int = 1,
        page_size: int = 10,
    ) -> AgentConfigHistoryResponse:
        """Get paginated config summaries for an agent.
        
        Returns limited fields suitable for table view.
        """
        from sqlalchemy import select
        from ..ai_models.models import AIModel
        
        configs, total = await self.configs.get_config_history_paginated(
            agent_id, page, page_size
        )
        
        # Collect all model IDs to fetch in one query
        all_model_ids = set()
        for config in configs:
            if config.llm_model_id:
                all_model_ids.add(config.llm_model_id)
            if config.embedding_model_id:
                all_model_ids.add(config.embedding_model_id)
        
        # Fetch all model names at once
        model_names = {}
        if all_model_ids:
            stmt = select(AIModel.id, AIModel.display_name).where(AIModel.id.in_(all_model_ids))
            result = await self.configs.db.execute(stmt)
            model_names = {row.id: row.display_name for row in result.all()}
        
        # Build summaries
        summaries = []
        for config in configs:
            summary = AgentConfigSummary(
                id=config.id,
                agent_id=config.agent_id,
                version=config.version,
                is_active=bool(config.is_active),
                status=config.status or "draft",
                embedding_status=config.embedding_status or "not_started",
                data_source_name=config.data_source.title if config.data_source else None,
                llm_model_name=model_names.get(config.llm_model_id) if config.llm_model_id else None,
                embedding_model_name=model_names.get(config.embedding_model_id) if config.embedding_model_id else None,
                created_at=config.created_at,
                updated_at=config.updated_at,
            )
            summaries.append(summary)
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        
        return AgentConfigHistoryResponse(
            configs=summaries,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    
    async def update_embedding_status(
        self,
        config_id: int,
        status: str,
        embedding_path: Optional[str] = None,
        vector_collection_name: Optional[str] = None,
    ) -> bool:
        """Update embedding status for a config."""
        return await self.configs.update_embedding_status(
            config_id=config_id,
            status=status,
            embedding_path=embedding_path,
            vector_collection_name=vector_collection_name,
        )
    
    async def get_or_create_draft(
        self,
        agent_id: UUID,
        data_source_id: UUID,
    ) -> AgentConfigResponse:
        """
        Get existing draft or create a new one.
        
        If a draft exists for this agent, returns it.
        Otherwise creates a new draft config.
        """
        # Check for existing draft
        draft = await self.configs.get_draft_config(agent_id)
        if draft:
            return self._to_response(draft)
        
        # Verify agent exists
        agent = await self.agents.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent {agent_id} not found",
                status_code=404,
            )
        
        # Verify data source exists
        source = await self.sources.get_by_id(data_source_id)
        if not source:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Data source {data_source_id} not found",
                status_code=404,
            )
        
        # Create new draft
        draft = await self.configs.create_draft(
            agent_id=agent_id,
            data_source_id=data_source_id,
        )
        
        return await self._to_response_with_models(draft)
    
    async def get_draft(self, agent_id: UUID) -> Optional[AgentConfigResponse]:
        """Get draft config for an agent if exists (with resolved model info)."""
        draft = await self.configs.get_draft_config(agent_id)
        if draft:
            return await self._to_response_with_models(draft)
        return None
    
    async def save_step(
        self,
        config_id: int,
        step: int,
        data: Dict[str, Any],
    ) -> Optional[AgentConfigResponse]:
        """
        Save step-specific data for a draft config.
        
        Only saves fields relevant to the specified step.
        Updates completed_step if progressing forward.
        """
        config = await self.configs.get_by_id(config_id)
        if not config:
            return None
        
        # Only allow saving to draft configs
        if config.status != "draft":
            raise AppException(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Cannot update a published config. Create a new draft first.",
                status_code=400,
            )
        
        # If step 1 contains data_source_id, validate it
        if step == 1 and "data_source_id" in data:
            source = await self.sources.get_by_id(data["data_source_id"])
            if not source:
                raise AppException(
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    message=f"Data source {data['data_source_id']} not found",
                    status_code=404,
                )
        
        updated = await self.configs.update_step_data(config_id, step, data)
        if updated:
            return self._to_response(updated)
        return None
    
    async def publish_draft(self, config_id: int) -> Optional[AgentConfigResponse]:
        """
        Publish a draft config.
        
        Changes status from draft to published and activates it.
        Deactivates any other active config for the agent.
        """
        config = await self.configs.get_by_id(config_id)
        if not config:
            return None
        
        if config.status != "draft":
            raise AppException(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Config is not a draft",
                status_code=400,
            )
        
        published = await self.configs.publish_draft(config_id)
        if published:
            return self._to_response(published)
        return None
    
    async def create_draft_from_config(
        self,
        config_id: int,
    ) -> Optional[AgentConfigResponse]:
        """
        Create a new draft by cloning an existing config.
        
        Used for "Edit Config" functionality - creates a draft
        copy to modify without affecting the published version.
        """
        config = await self.configs.get_by_id(config_id)
        if not config:
            return None
        
        # Check if there's already a draft for this agent
        existing_draft = await self.configs.get_draft_config(config.agent_id)
        if existing_draft:
            raise AppException(
                error_code=ErrorCode.RESOURCE_ALREADY_EXISTS,
                message="A draft already exists for this agent. Delete or publish it first.",
                status_code=409,
            )
        
        draft = await self.configs.clone_config_as_draft(config_id)
        if draft:
            return self._to_response(draft)
        return None
    
    async def delete_draft(self, config_id: int) -> bool:
        """Delete a draft config."""
        config = await self.configs.get_by_id(config_id)
        if not config:
            return False
        
        if config.status != "draft":
            raise AppException(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Cannot delete a published config",
                status_code=400,
            )
        
        await self.db.delete(config)
        await self.db.flush()
        return True
    
    # ==========================================
    # Per-Step Upsert Methods (named steps)
    # ==========================================
    
    async def upsert_data_source_step(
        self,
        agent_id: UUID,
        data_source_id: UUID,
        version_id: Optional[int] = None,
    ) -> AgentConfigResponse:
        """
        Step: data-source.
        If version_id provided, updates that version.
        If not provided, creates a new draft version.
        """
        # Verify agent exists
        agent = await self.agents.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent {agent_id} not found",
                status_code=404,
            )
        
        # Verify data source exists
        source = await self.sources.get_by_id(data_source_id)
        if not source:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Data source {data_source_id} not found",
                status_code=404,
            )
        
        # Data source lockdown: If agent has any published configs, data source cannot be changed
        history = await self.configs.get_config_history(agent_id)
        published_configs = [c for c in history if c.status != 'draft']
        
        if published_configs:
            # Latest published config (history is ordered by version DESC)
            latest_published = published_configs[0]
            if str(latest_published.data_source_id) != str(data_source_id):
                raise AppException(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Data source cannot be changed for an agent with existing published configurations. Please create a new agent if you need to use a different data source.",
                    status_code=400,
                )

        
        if version_id:
            # Update existing version
            config = await self.configs.get_by_id(version_id)
            if not config:
                raise AppException(
                    error_code=ErrorCode.RESOURCE_NOT_FOUND,
                    message=f"Version {version_id} not found",
                    status_code=404,
                )
            # Verify version belongs to this agent
            if config.agent_id != agent_id:
                raise AppException(
                    error_code=ErrorCode.FORBIDDEN,
                    message="Version does not belong to this agent",
                    status_code=403,
                )
            updated = await self.configs.update(version_id, {
                "data_source_id": data_source_id,
                "completed_step": max(1, config.completed_step),
            })
            return self._to_response(updated)
        else:
            # Create new draft version
            draft = await self.configs.create_draft(
                agent_id=agent_id,
                data_source_id=data_source_id,
            )
            return self._to_response(draft)
    
    async def upsert_schema_selection_step(
        self,
        version_id: int,
        selected_schema: Dict[str, List[str]],
    ) -> AgentConfigResponse:
        """
        Step: schema-selection.
        Updates selected columns for an existing version.
        
        Args:
            selected_schema: Table to columns mapping { "table_name": ["col1", "col2"] }
                            For files, uses the DuckDB table name.
                            For databases, can have multiple tables.
        """
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )
        
        # Build the update data
        update_data: Dict[str, Any] = {
            "completed_step": max(2, config.completed_step),
            "selected_columns": selected_schema,
        }
        
        updated = await self.configs.update(version_id, update_data)
        return self._to_response(updated)
    
    async def upsert_data_dictionary_step(
        self,
        version_id: int,
        data_dictionary: Dict[str, Any],
    ) -> AgentConfigResponse:
        """
        Step: data-dictionary.
        Updates data dictionary for an existing version.
        """
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )

        updated = await self.configs.update(version_id, {
            "data_dictionary": data_dictionary,
            "completed_step": max(3, config.completed_step),
        })
        return self._to_response(updated)

    async def upsert_agent_definition_step(
        self,
        version_id: int,
        agent_definition,
    ) -> AgentConfigResponse:
        """
        Step 4.5: persist user-edited (or AI-drafted) agent definition.

        Sample questions flagged with use_as_few_shot=true are indexed into
        the agent's few-shot store after the row is updated.
        """
        import json as _json

        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )

        # Accept either pydantic AgentDefinition or plain dict.
        if hasattr(agent_definition, "model_dump"):
            payload = agent_definition.model_dump()
        else:
            payload = dict(agent_definition)

        updated = await self.configs.update(version_id, {
            "agent_definition": _json.dumps(payload),
            "agent_definition_status": "completed",
            "completed_step": max(4, config.completed_step),
        })

        # Promote sample_questions to the agent's few-shot store (best effort).
        try:
            from app.modules.sql_examples.store import upsert_agent_examples
            sample_qs = [
                q for q in payload.get("sample_questions") or []
                if isinstance(q, dict) and q.get("question") and q.get("use_as_few_shot", True)
            ]
            if sample_qs and updated and updated.agent_id:
                await upsert_agent_examples(str(updated.agent_id), sample_qs)
        except Exception as exc:
            logger.warning(f"Failed to index sample_questions as few-shot: {exc}")

        return self._to_response(updated)

    async def validate_data_dictionary(
        self,
        version_id: int,
    ) -> Dict[str, Any]:
        """
        Validate a data dictionary against the actual database schema.
        
        This helps catch schema-dictionary drift that can cause NL2SQL errors.
        
        Returns:
            Dict with validation_result, errors, warnings, and report
        """
        import json
        import yaml
        
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )
        
        # Get data source to get database URL
        db_url = None
        if config.data_source_id:
            source = await self.sources.get_by_id(config.data_source_id)
            if source and source.source_type == "database" and source.db_url:
                db_url = source.db_url
        
        # Parse data dictionary
        data_dict = {}
        if config.data_dictionary:
            try:
                data_dict_raw = json.loads(config.data_dictionary)
                # Handle wrapper format
                if isinstance(data_dict_raw, dict) and "content" in data_dict_raw:
                    content = data_dict_raw["content"]
                    if isinstance(content, str):
                        # Try YAML first, then JSON
                        try:
                            data_dict = yaml.safe_load(content)
                        except:
                            data_dict = json.loads(content)
                    else:
                        data_dict = content
                else:
                    data_dict = data_dict_raw
            except (json.JSONDecodeError, yaml.YAMLError) as e:
                return {
                    "is_valid": False,
                    "errors": [{"error_type": "parse_error", "message": f"Failed to parse data dictionary: {e}"}],
                    "warnings": [],
                    "report": f"Failed to parse data dictionary: {e}"
                }
        
        if not data_dict:
            return {
                "is_valid": True,
                "errors": [],
                "warnings": [{"error_type": "empty", "message": "No data dictionary configured"}],
                "report": "No data dictionary to validate"
            }
        
        # Create validator
        try:
            validator = SchemaValidator(db_url=db_url) if db_url else SchemaValidator()
            result = validator.validate_data_dictionary(data_dict)
            
            return {
                "is_valid": result.is_valid,
                "errors": [
                    {
                        "error_type": e.error_type,
                        "location": e.location,
                        "message": e.message,
                        "suggested_fix": e.suggested_fix
                    }
                    for e in result.errors
                ],
                "warnings": [
                    {
                        "error_type": w.error_type,
                        "location": w.location,
                        "message": w.message,
                        "suggested_fix": w.suggested_fix
                    }
                    for w in result.warnings
                ],
                "report": format_validation_report(result),
                "validated_tables": list(result.validated_tables)
            }
        except Exception as e:
            logger.warning(f"Schema validation failed: {e}")
            return {
                "is_valid": True,  # Don't block on validation errors
                "errors": [],
                "warnings": [{"error_type": "validation_error", "message": f"Could not validate against schema: {e}"}],
                "report": f"Validation skipped: {e}"
            }
    
    async def upsert_settings_step(
        self,
        version_id: int,
        embedding_config: Optional[Dict[str, Any]] = None,
        chunking_config: Optional[Dict[str, Any]] = None,
        rag_config: Optional[Dict[str, Any]] = None,
        llm_config: Optional[Dict[str, Any]] = None,
        llm_model_id: Optional[int] = None,
        embedding_model_id: Optional[int] = None,
        reranker_model_id: Optional[int] = None,
    ) -> AgentConfigResponse:
        """
        Step: settings.
        Updates configs for an existing version.
        Stores model IDs (foreign keys to ai_models.id) for easy querying.
        When model IDs are provided, the redundant model name fields are stripped.
        """
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )
        
        update_data: Dict[str, Any] = {
            "completed_step": max(4, config.completed_step),
        }
        
        # Strip redundant model fields when model IDs are provided
        if embedding_config is not None:
            clean_embedding = {k: v for k, v in embedding_config.items() if k != "model" or not embedding_model_id}
            update_data["embedding_config"] = clean_embedding
        if chunking_config is not None:
            update_data["chunking_config"] = chunking_config
        if rag_config is not None:
            clean_rag = {k: v for k, v in rag_config.items() if k != "reranker_model" or not reranker_model_id}
            update_data["rag_config"] = clean_rag
        if llm_config is not None:
            clean_llm = {k: v for k, v in llm_config.items() if k != "model" or not llm_model_id}
            update_data["llm_config"] = clean_llm
        
        # Store model IDs (foreign keys to ai_models.id)
        if llm_model_id is not None:
            update_data["llm_model_id"] = llm_model_id
        if embedding_model_id is not None:
            update_data["embedding_model_id"] = embedding_model_id
        if reranker_model_id is not None:
            update_data["reranker_model_id"] = reranker_model_id
        
        updated = await self.configs.update(version_id, update_data)
        return self._to_response(updated)
    
    async def upsert_prompt_step(
        self,
        version_id: int,
        system_prompt: str,
        example_questions: Optional[List[str]] = None,
    ) -> AgentConfigResponse:
        """
        Step: prompt.
        Updates prompt for an existing version.
        """
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )
        
        updated = await self.configs.update(version_id, {
            "system_prompt": system_prompt,
            "example_questions": example_questions or [],
            "completed_step": max(5, config.completed_step),
        })
        return self._to_response(updated)

    async def upsert_publish_step(
        self,
        version_id: int,
        system_prompt: str,
        example_questions: Optional[List[str]] = None,
    ) -> AgentConfigResponse:
        """
        Step: publish.
        Saves final prompt and publishes the configuration.
        """
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )
        
        if config.status != "draft":
            raise AppException(
                error_code=ErrorCode.VALIDATION_ERROR,
                message="Config is not a draft",
                status_code=400,
            )
        
        # Update prompt data
        await self.configs.update(version_id, {
            "system_prompt": system_prompt,
            "example_questions": example_questions or [],
            "completed_step": 5,
        })
        
        # Publish the draft
        published = await self.configs.publish_draft(version_id)
        if not published:
            raise AppException(
                error_code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="Failed to publish configuration",
                status_code=500,
            )
        
        return await self._to_response_with_models(published)

    @staticmethod
    def _has_clinical_scope(selected_columns: Any) -> bool:
        """
        Heuristic: does the selected schema include clinical/FHIR tables?

        Returns True when the user's table selection contains at least one
        table that signals healthcare/NCD analytics. Used by `generate_prompt`
        to gate FHIR rules, healthcare SQL examples, and M&E sections so that
        admin-only agents don't get prompts teeming with references to tables
        they cannot query.
        """
        if not isinstance(selected_columns, dict):
            return False
        keys = {str(k).lower() for k in selected_columns.keys()}
        clinical_markers = {
            "patient_tracker_gold", "patient_gold", "bp_log_gold",
            "bp_log_latest_gold", "condition_gold", "encounter_gold",
            "patient_diagnosis_gold", "glucose_log_gold",
            "glucose_log_latest_gold",
            "patient_confirmed_diagnosis_gold",
            "patient_provisional_diagnosis_gold",
            "careplan_gold", "appointment_gold", "screening_log_gold",
        }
        if keys & clinical_markers:
            return True
        clinical_substrings = ("patient", "bp_log", "glucose", "condition", "encounter")
        return any(
            k.endswith("_gold") and any(s in k for s in clinical_substrings)
            for k in keys
        )

    @staticmethod
    def _render_agent_definition_sections(definition: Dict[str, Any]) -> str:
        """
        Render the persisted AgentDefinition JSON as labelled prompt sections.

        Placed early in the assembled system prompt so intent steers all
        downstream sections (FHIR rules, SQL rules, data dictionary, etc.).
        """
        if not isinstance(definition, dict):
            return ""

        def _bullets(items: List[Any]) -> str:
            return "\n".join(f"- {str(i).strip()}" for i in items if str(i).strip())

        out: List[str] = []

        role = (definition.get("role") or "").strip()
        responsibilities = definition.get("responsibilities") or []
        if role or responsibilities:
            parts = ["# AGENT ROLE"]
            if role:
                parts.append(role)
            if responsibilities:
                parts.append("\n## Responsibilities")
                parts.append(_bullets(responsibilities))
            out.append("\n".join(parts))

        personas = definition.get("target_personas") or []
        if personas:
            out.append("# TARGET USERS\n" + _bullets(personas))

        objectives = definition.get("business_objectives") or []
        if objectives:
            out.append("# BUSINESS OBJECTIVES\n" + _bullets(objectives))

        capabilities = definition.get("analytical_capabilities") or []
        limitations = definition.get("limitations") or []
        if capabilities or limitations:
            cap_parts = ["# CAPABILITIES & LIMITATIONS"]
            if capabilities:
                cap_parts.append("## Can Do")
                cap_parts.append(_bullets(capabilities))
            if limitations:
                cap_parts.append("## Must Refuse Or Caveat")
                cap_parts.append(_bullets(limitations))
            out.append("\n".join(cap_parts))

        kpis = definition.get("kpis_metrics") or []
        if kpis:
            out.append("# PRIORITY METRICS\n" + _bullets(kpis))

        domain_rules = definition.get("domain_rules") or []
        guardrails = definition.get("guardrails") or []
        if domain_rules or guardrails:
            rule_parts = ["# DOMAIN RULES & GUARDRAILS (follow exactly)"]
            if domain_rules:
                rule_parts.append("## Domain Rules")
                rule_parts.append(_bullets(domain_rules))
            if guardrails:
                rule_parts.append("## Guardrails")
                rule_parts.append(_bullets(guardrails))
            out.append("\n".join(rule_parts))

        style = definition.get("response_style") or {}
        if isinstance(style, dict) and any(style.values()):
            style_lines = [f"- {k}: {v}" for k, v in style.items() if v]
            if style_lines:
                out.append("# RESPONSE STYLE\n" + "\n".join(style_lines))

        sample_qs = definition.get("sample_questions") or []
        if sample_qs:
            # Split into "has SQL" (worth inlining) vs "question-only".
            with_sql: List[Dict[str, Any]] = []
            no_sql: List[str] = []
            for q in sample_qs:
                if isinstance(q, dict) and q.get("question"):
                    qtext = str(q["question"]).strip()
                    sql = str(q.get("sql") or "").strip()
                    if sql:
                        with_sql.append({
                            "question": qtext,
                            "sql": sql,
                            "expected": str(q.get("expected_summary") or "").strip(),
                        })
                    else:
                        no_sql.append(qtext)
                elif isinstance(q, str) and q.strip():
                    no_sql.append(q.strip())

            # Take up to 3 full Q+SQL exemplars inline — guaranteed seen by the
            # LLM (not behind vector retrieval). High-value stakeholder
            # patterns belong here so they ground every relevant query.
            inline = with_sql[:3]
            remaining_with_sql = [q["question"] for q in with_sql[3:]]
            bullet_questions = remaining_with_sql + no_sql

            section_parts = [
                "# SAMPLE QUESTIONS THIS AGENT SHOULD HANDLE",
                "",
                "The agent should be able to answer questions like the following.",
                "For the patterns shown below the validated SQL is provided as",
                "authoritative reference — match this style when the user asks",
                "a semantically similar question.",
                "",
            ]

            for idx, item in enumerate(inline, 1):
                section_parts.append(f"## Q{idx}: {item['question']}")
                section_parts.append("```sql")
                section_parts.append(item["sql"])
                section_parts.append("```")
                if item["expected"]:
                    section_parts.append(f"**Expected**: {item['expected']}")
                section_parts.append("")

            if bullet_questions:
                section_parts.append("## Additional question patterns the agent should handle")
                for bq in bullet_questions:
                    section_parts.append(f"- {bq}")
                section_parts.append("")

            section_parts.append(
                "(Sample questions are also indexed in the few-shot example "
                "store and surfaced via vector retrieval for related queries.)"
            )

            out.append("\n".join(section_parts).rstrip())

        return "\n\n".join(out)

    def _to_response(self, config) -> AgentConfigResponse:
        """Convert config model to response schema (without model info lookup)."""
        data = _config_to_dict(config)
        # Convert is_active int to bool
        data["is_active"] = bool(data.get("is_active", 0))
        # Add data_source_type from related data_source if available
        if hasattr(config, 'data_source') and config.data_source:
            data["data_source_type"] = config.data_source.source_type
        return AgentConfigResponse(**data)
    
    async def _to_response_with_models(self, config) -> AgentConfigResponse:
        """Convert config model to response schema WITH resolved model info."""
        from sqlalchemy import select
        from ..ai_models.models import AIModel
        from .schemas import ModelInfo
        
        response = self._to_response(config)
        
        # If data_source_type not set, fetch from data source
        if not response.data_source_type and config.data_source_id:
            source = await self.sources.get_by_id(config.data_source_id)
            if source:
                response.data_source_type = source.source_type
        
        # Fetch model info for each model ID
        model_ids = [
            config.llm_model_id,
            config.embedding_model_id,
            config.reranker_model_id
        ]
        model_ids = [mid for mid in model_ids if mid is not None]
        
        if model_ids:
            stmt = select(AIModel).where(AIModel.id.in_(model_ids))
            result = await self.configs.db.execute(stmt)
            models = {m.id: m for m in result.scalars().all()}
            
            # Set model info on response
            if config.llm_model_id and config.llm_model_id in models:
                m = models[config.llm_model_id]
                response.llm_model = ModelInfo(
                    id=m.id,
                    provider_name=m.provider_name,
                    display_name=m.display_name,
                    model_id=m.model_id,
                    model_type=m.model_type
                )
            
            if config.embedding_model_id and config.embedding_model_id in models:
                m = models[config.embedding_model_id]
                response.embedding_model = ModelInfo(
                    id=m.id,
                    provider_name=m.provider_name,
                    display_name=m.display_name,
                    model_id=m.model_id,
                    model_type=m.model_type
                )
            
            if config.reranker_model_id and config.reranker_model_id in models:
                m = models[config.reranker_model_id]
                response.reranker_model = ModelInfo(
                    id=m.id,
                    provider_name=m.provider_name,
                    display_name=m.display_name,
                    model_id=m.model_id,
                    model_type=m.model_type
                )
        
        return response

    async def generate_prompt(
        self,
        version_id: int,
    ) -> Dict[str, Any]:
        """
        Generate a system prompt using deterministic template composition.
        
        Uses direct template concatenation for reproducible, complete prompts.
        LLM is only used to generate example questions (where it adds value).
        
        Returns:
            Dict with draft_prompt, reasoning, and example_questions
        """
        import json
        import os
        from langchain.schema import HumanMessage, SystemMessage
        from app.core.llm import create_llm_provider
        from app.core.prompts import (
            get_chart_generator_prompt,
            get_base_system_prompt,
            get_fhir_rules_prompt,
            get_sql_generator_prompt,
            get_sql_generator_rules_only,
            get_generic_sql_generator_prompt,
            get_duckdb_sql_rules_prompt,
            get_reasoning_generator_prompt,
        )
        
        config = await self.configs.get_by_id(version_id)
        if not config:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Version {version_id} not found",
                status_code=404,
            )
        
        # Parse JSON fields (stored as strings in DB)
        data_dictionary = json.loads(config.data_dictionary) if config.data_dictionary else {}
        selected_columns = json.loads(config.selected_columns) if config.selected_columns else {}
        llm_config = json.loads(config.llm_config) if config.llm_config else {}
        agent_definition = (
            json.loads(config.agent_definition)
            if getattr(config, "agent_definition", None)
            else None
        )
        
        # Get data source type (database or file) from the config's data source
        data_source_type = "database"  # default
        if config.data_source_id:
            source = await self.sources.get_by_id(config.data_source_id)
            if source:
                data_source_type = source.source_type
        
        # =========================================================================
        # DETERMINISTIC TEMPLATE COMPOSITION
        # =========================================================================
        
        # Build schema context (only included ONCE)
        schema_parts = []
        if selected_columns:
            compressed_schema = self._compress_schema_for_prompt(selected_columns)
            schema_parts.append(compressed_schema)
        
        # Extract data dictionary content
        data_dict_content = ""
        if data_dictionary:
            if isinstance(data_dictionary, dict) and "content" in data_dictionary:
                dict_content = data_dictionary["content"]
                if isinstance(dict_content, str):
                    data_dict_content = dict_content
                else:
                    data_dict_content = json.dumps(dict_content, indent=2)
            else:
                data_dict_content = json.dumps(data_dictionary, indent=2)
        
        # Compose the system prompt from templates (deterministic, no LLM)
        prompt_sections = []
        
        # Section 1: Core Identity (domain-neutral skeleton).
        # The actual role + responsibilities come from `# AGENT ROLE` below,
        # which is populated by the AI-bootstrapped Agent Definition.
        prompt_sections.append("""# CORE IDENTITY & PIPELINE

You are an analytics agent for a relational database. Follow the role,
responsibilities, target users, and domain rules declared in `# AGENT ROLE`
and `# DOMAIN RULES & GUARDRAILS` below as your primary identity and
operating contract — do not contradict them.

Pipeline order (apply on every request):
1. Intent Parser
2. Schema Mapper
3. Query Planner
4. SQL Generator
5. Validator

Operational principles:
- Read-only, deterministic, auditable analytical SQL.
- Use ONLY tables and columns present in `# DATA DICTIONARY & SCHEMA`.
- Never invent tables, columns, joins, values, or semantics not grounded
  in the schema or in the explicitly stated domain rules.
- Never expose credentials, secrets, or tokens stored in any column.
- For any user request, return an executable SQL answer + concise
  interpretation when the response style asks for it — never a narrative
  approximation.""")
        
        # Section 1.5: Agent Definition (Step 5) — intent before mechanics.
        # Only injected when present so legacy agents without a definition still
        # produce a working prompt via the generic identity above.
        if agent_definition:
            ad_sections = self._render_agent_definition_sections(agent_definition)
            if ad_sections:
                prompt_sections.append(ad_sections)

        # Detect clinical scope ONCE — gates the next several healthcare-specific
        # sections so admin/operational agents don't get prompts polluted with
        # references to tables (patient_tracker_gold, bp_log_gold, etc.) they
        # cannot query.
        has_clinical_scope = self._has_clinical_scope(selected_columns)

        # Section 2: FHIR Rules — only when clinical tables are in scope
        if has_clinical_scope:
            prompt_sections.append(
                "# FHIR IDENTIFIER RULES - CRITICAL\n\n" + get_fhir_rules_prompt()
            )
        
        # Section 3: Schema & Data Dictionary (injected ONCE here)
        if schema_parts or data_dict_content:
            schema_section = "# DATA DICTIONARY & SCHEMA\n\n"
            if schema_parts:
                schema_section += "## SELECTED SCHEMA\n" + "\n".join(schema_parts) + "\n\n"
            if data_dict_content:
                schema_section += "## DATA DICTIONARY\n" + data_dict_content
            prompt_sections.append(schema_section)
        
        # Section 4: SQL Generation Rules — scope-aware.
        # Clinical scope: full FHIR-flavoured SQL prompt MINUS the duplicate
        # FHIR-rules preamble (FHIR section already emitted above).
        # Non-clinical scope: domain-agnostic SQL rules (no `*_gold` examples,
        # no M&E patterns) so the LLM isn't pointed at tables out of scope.
        if has_clinical_scope:
            prompt_sections.append(
                "# SQL GENERATION RULES\n\n" + get_sql_generator_rules_only()
            )
        else:
            prompt_sections.append(get_generic_sql_generator_prompt())
        
        # Section 5: DuckDB-specific rules (if applicable)
        # Note: At runtime, sql_service will add these based on actual DB type
        # We include a placeholder instruction here
        prompt_sections.append("""# DATABASE DIALECT

The SQL dialect will be determined at runtime. Follow standard PostgreSQL syntax by default.
For DuckDB connections, additional dialect-specific rules will be injected at query time.""")
        
        # Section 6: Chart Visualization Rules
        prompt_sections.append("# CHART VISUALIZATION RULES\n\n" + get_chart_generator_prompt())
        
        # Section 7: Data Quality & Validation
        prompt_sections.append("""# DATA QUALITY & VALIDATION RULES

## SQL Style Guidelines
- Use lowercase for SQL keywords for consistency
- Use explicit column names (never SELECT *)
- Use consistent table aliasing (e.g., first letter or meaningful abbreviation)
- Apply appropriate soft-delete filters based on table type

## Aggregation Rules
- Use COUNT(DISTINCT entity_id) for unique entity counts to prevent fan-out bugs
- Ensure all non-aggregated SELECT columns appear in GROUP BY
- Filter NULL values appropriately for aggregate functions

## Validation Checklist
Before returning SQL:
1. Verify all tables and columns exist in the schema
2. Check join conditions are correct and won't cause Cartesian products
3. Ensure GROUP BY includes all non-aggregated columns
4. Confirm soft-delete filters are applied where appropriate
5. Validate the query answers the user's original intent""")
        
        # Combine all sections
        prompt_content = "\n\n---\n\n".join(prompt_sections)
        
        logger.info(f"Generated deterministic prompt with {len(prompt_sections)} sections, {len(prompt_content)} chars")
        
        # =========================================================================
        # LLM CALL: Only for generating example questions (value-add task)
        # =========================================================================
        
        # Get LLM configuration
        from ..ai_models.models import AIModel
        from app.core.encryption import decrypt_value
        from app.core.config import get_settings
        from sqlalchemy import select
        
        settings = get_settings()
        
        # Fetch AI model from database
        ai_model = None
        if config.llm_model_id:
            stmt = select(AIModel).where(AIModel.id == config.llm_model_id)
            result = await self.configs.db.execute(stmt)
            ai_model = result.scalar_one_or_none()
        
        # Get model name, provider, and API key
        if ai_model:
            model_id = ai_model.model_id
            provider_name = ai_model.provider_name.lower()
            api_base_url = ai_model.api_base_url
            
            api_key = None
            if ai_model.api_key_env_var:
                api_key = os.environ.get(ai_model.api_key_env_var)
            if not api_key and ai_model.api_key_encrypted:
                api_key = decrypt_value(ai_model.api_key_encrypted)
            if not api_key:
                api_key = settings.openai_api_key
        else:
            model_id = llm_config.get("model", "openai/gpt-4o-mini")
            provider_name = "openai"
            api_key = settings.openai_api_key
            api_base_url = None
        
        temperature = llm_config.get("temperature", 0.0)
        
        # Generate example questions using LLM (optional - graceful degradation)
        reasoning = {}
        questions = []
        
        if api_key:
            try:
                if "/" in model_id:
                    model_name = model_id.split("/", 1)[1]
                else:
                    model_name = model_id
                
                provider_config = {
                    "model": model_name,
                    "temperature": temperature,
                    "api_key": api_key,
                }
                if api_base_url:
                    provider_config["base_url"] = api_base_url
                
                provider = create_llm_provider(provider_name, provider_config)
                raw_llm = provider.get_langchain_llm()
                
                # Wrap with PHI protection
                from app.core.llm.base import wrap_llm_with_phi_protection
                llm = wrap_llm_with_phi_protection(raw_llm)
                
                # Build concise context for question generation (not the full schema)
                table_names = list(selected_columns.keys()) if selected_columns else []
                table_summary = ", ".join(table_names[:20])  # First 20 tables
                if len(table_names) > 20:
                    table_summary += f", ... and {len(table_names) - 20} more"
                
                reasoning_instruction = f"""Based on this healthcare analytics database schema, generate example questions.

Available tables: {table_summary}

Data dictionary summary:
{data_dict_content[:2000] if data_dict_content else 'Healthcare patient and clinical data'}

Return a JSON object with:
{{
  "selection_reasoning": {{
    "key_column_1": "Why important",
    "key_column_2": "Why important"
  }},
  "example_questions": [
    "Question 1 about aggregations",
    "Question 2 about distributions", 
    "Question 3 about trends",
    "Question 4 about comparisons",
    "Question 5 about filtering/cohorts"
  ]
}}

Return ONLY valid JSON, no markdown formatting."""

                reasoning_messages = [
                    SystemMessage(content="You are a healthcare data analyst. Return only valid JSON."),
                    HumanMessage(content=reasoning_instruction)
                ]
                
                logger.info("Invoking LLM for example questions generation...")
                reasoning_response = llm.invoke(reasoning_messages)
                reasoning_text = reasoning_response.content.strip()
                
                # Clean and parse JSON
                reasoning_text = reasoning_text.replace("```json", "").replace("```", "").strip()
                import re
                json_match = re.search(r'\{[\s\S]*\}', reasoning_text)
                if json_match:
                    reasoning_text = json_match.group()
                
                parsed = json.loads(reasoning_text)
                reasoning = parsed.get("selection_reasoning", {})
                questions = parsed.get("example_questions", [])
                logger.info(f"Generated {len(questions)} example questions")
                
            except Exception as e:
                logger.warning(f"Example question generation failed (non-fatal): {e}")
                # Provide default questions as fallback
                questions = [
                    "How many patients are currently enrolled?",
                    "What is the distribution of patients by CVD risk level?",
                    "Show the trend of blood pressure readings over the past year",
                    "Which facilities have the highest patient volume?",
                    "What percentage of patients have controlled hypertension?"
                ]
        else:
            logger.warning("No API key configured - using default example questions")
            questions = [
                "How many patients are currently enrolled?",
                "What is the distribution of patients by CVD risk level?",
                "Show the trend of blood pressure readings over the past year",
                "Which facilities have the highest patient volume?",
                "What percentage of patients have controlled hypertension?"
            ]
        
        # Run schema validation
        validation_result = None
        try:
            validation_result = await self.validate_data_dictionary(version_id)
            if not validation_result.get("is_valid"):
                logger.warning(f"Data dictionary validation found issues: {validation_result.get('report', 'Unknown')}")
        except Exception as e:
            logger.warning(f"Schema validation skipped: {e}")
        
        return {
            "draft_prompt": prompt_content,
            "reasoning": reasoning,
            "example_questions": questions,
            "validation": validation_result,
        }

    def _compress_schema_for_prompt(self, selected_columns: Dict[str, List[str]]) -> str:
        """
        Compress schema representation by grouping tables with identical column structures.
        
        This reduces token usage when many tables share the same columns (e.g., partitioned tables).
        """
        from collections import defaultdict
        
        column_signature_to_tables: Dict[tuple, List[str]] = defaultdict(list)
        
        for table_name, columns in selected_columns.items():
            signature = tuple(sorted(columns))
            column_signature_to_tables[signature].append(table_name)
        
        output_parts = []
        
        for signature, tables in column_signature_to_tables.items():
            columns = list(signature)
            
            if len(tables) == 1:
                output_parts.append(f"- `{tables[0]}`: {', '.join(f'`{c}`' for c in columns)}")
            else:
                common_prefix = self._find_common_prefix(tables)
                if common_prefix and len(common_prefix) > 5:
                    output_parts.append(
                        f"- `{common_prefix}*` ({len(tables)} tables with identical structure): "
                        f"{', '.join(f'`{c}`' for c in columns)}"
                    )
                    example_tables = tables[:3]
                    if len(tables) > 3:
                        output_parts.append(f"  (Examples: {', '.join(example_tables)}, ... and {len(tables) - 3} more)")
                else:
                    output_parts.append(
                        f"- Tables with shared structure ({len(tables)} tables): "
                        f"{', '.join(f'`{c}`' for c in columns)}"
                    )
                    output_parts.append(f"  Tables: {', '.join(tables[:10])}" + (", ..." if len(tables) > 10 else ""))
        
        return "\n".join(output_parts)
    
    def _find_common_prefix(self, strings: List[str]) -> str:
        """Find the longest common prefix among a list of strings."""
        if not strings:
            return ""
        prefix = strings[0]
        for s in strings[1:]:
            while not s.startswith(prefix) and prefix:
                prefix = prefix[:-1]
            if not prefix:
                return ""
        return prefix
