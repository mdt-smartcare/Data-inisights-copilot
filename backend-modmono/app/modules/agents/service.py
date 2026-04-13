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
        query: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> AgentListResponse:
        """
        List agents accessible to user with their roles.
        
        Filters to only show agents the user has access to.
        """
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
    ) -> bool:
        """Check if user has access with minimum role."""
        return await self.user_agents.has_access(user_id, agent_id, min_role)
    
    async def get_agent_users(self, agent_id: UUID) -> UserAgentListResponse:
        """Get all users with access to an agent."""
        users = await self.user_agents.get_agent_users(agent_id)
        return UserAgentListResponse(
            users=users,
            total=len(users),
            agent_id=agent_id,
        )
    
    async def get_user_agents(self, user_id: UUID) -> AgentsForUserListResponse:
        """Get all agents a user has access to."""
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
        Generate a system prompt based on saved config data.
        
        Reads data_dictionary, selected_columns, and llm_config from DB,
        then uses LLM to generate a production-ready system prompt.
        
        Returns:
            Dict with draft_prompt, reasoning, and example_questions
        """
        import json
        import os
        from langchain.schema import HumanMessage, SystemMessage
        from app.core.llm import create_llm_provider
        from app.core.prompts import get_chart_generator_prompt, get_database_generator_prompt, get_file_generator_prompt, get_reasoning_generator_prompt
        
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
        
        # Get data source type (database or file) from the config's data source
        data_source_type = "database"  # default
        if config.data_source_id:
            source = await self.sources.get_by_id(config.data_source_id)
            if source:
                data_source_type = source.source_type
        
        # Build context for prompt generation
        context_parts = []
        
        if selected_columns:
            context_parts.append("SELECTED SCHEMA:")
            context_parts.append(json.dumps(selected_columns, indent=2))
        
        if data_dictionary:
            context_parts.append("\nDATA DICTIONARY:")
            # Extract content from wrapper if present (frontend stores as {"content": "..."})
            if isinstance(data_dictionary, dict) and "content" in data_dictionary:
                dict_content = data_dictionary["content"]
                # If content is a string, use it directly; otherwise JSON dump it
                if isinstance(dict_content, str):
                    context_parts.append(dict_content)
                else:
                    context_parts.append(json.dumps(dict_content, indent=2))
            else:
                context_parts.append(json.dumps(data_dictionary, indent=2))
        
        data_context = "\n".join(context_parts) if context_parts else "No schema information provided."
        
        # Escape curly braces
        safe_context = data_context.replace("{", "{{").replace("}", "}}")
        
        # Get chart generation rules from external template
        # Note: We don't escape braces here since chart_rules goes into the LLM prompt as literal text
        chart_rules = get_chart_generator_prompt()
        
        # Get LLM configuration from ai_models table using llm_model_id
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
            model_id = ai_model.model_id  # e.g., "openai/gpt-4o"
            provider_name = ai_model.provider_name.lower()  # e.g., "openai"
            api_base_url = ai_model.api_base_url
            
            # Get API key - try env var first, then encrypted key
            api_key = None
            if ai_model.api_key_env_var:
                api_key = os.environ.get(ai_model.api_key_env_var)
            if not api_key and ai_model.api_key_encrypted:
                api_key = decrypt_value(ai_model.api_key_encrypted)
            if not api_key:
                api_key = settings.openai_api_key
        else:
            # Fallback to config or default
            model_id = llm_config.get("model", "openai/gpt-4o-mini")
            provider_name = "openai"
            api_key = settings.openai_api_key
            api_base_url = None
        
        # Get temperature from llm_config
        temperature = llm_config.get("temperature", 0.0)
        
        # Validate API key is available
        if not api_key:
            raise AppException(
                message="No API key configured. Please either set OPENAI_API_KEY environment variable or configure an LLM model with API key in AI Registry.",
                status_code=400,
                error_code=ErrorCode.BAD_REQUEST
            )
        
        # Extract model name from model_id format "provider/model"
        if "/" in model_id:
            model_name = model_id.split("/", 1)[1]
        else:
            model_name = model_id
        
        # Create LLM provider using core/llm abstraction
        provider_config = {
            "model": model_name,
            "temperature": temperature,
            "api_key": api_key,
        }
        if api_base_url:
            provider_config["base_url"] = api_base_url
        
        provider = create_llm_provider(provider_name, provider_config)
        llm = provider.get_langchain_llm()
        
        # Determine which template to use based on data source type
        if data_source_type == "file":
            generator_template = get_file_generator_prompt()
        else:
            generator_template = get_database_generator_prompt()
        
        # Build the data context for the template
        data_dict_text = safe_context
        
        # Build prompt using the template
        system_role = "You are a Data Architect and AI System Prompt Engineer specializing in creating precise, production-ready system prompts."
        
        # Inject data dictionary into the template
        template_with_data = generator_template.replace("{data_dictionary}", data_dict_text)
        
        instruction = f"""{template_with_data}

CHART VISUALIZATION RULES (MUST BE APPENDED TO THE GENERATED PROMPT):
{chart_rules}

**CRITICAL**: The generated system prompt MUST include the CHART VISUALIZATION section with the chart generation rules above. This is a KEY FEATURE.

---

## MANDATORY OUTPUT FORMAT

Your response MUST contain TWO parts separated by the exact string '---REASONING---':

### PART 1: System Prompt
The complete system prompt text (everything before the separator).

### PART 2: JSON Metadata (REQUIRED)
After the '---REASONING---' separator, you MUST include a valid JSON object with:

```json
{{
  "selection_reasoning": {{
    "column_name_1": "Why this column is important for queries",
    "column_name_2": "Why this column is important for queries"
  }},
  "example_questions": [
    "What is the average BMI across all patients?",
    "How many patients have high CVD risk level?",
    "Show the distribution of patients by county",
    "What is the trend of blood pressure readings over time?",
    "Which facilities have the most assessments?"
  ]
}}
```

**IMPORTANT**: 
- The example_questions MUST be 5 specific, realistic questions that users could ask about THIS dataset
- Questions should cover different types: aggregations, distributions, trends, comparisons
- The selection_reasoning should explain 3-5 key columns and why they matter for analysis

DO NOT skip the ---REASONING--- section. It is mandatory."""

        # First LLM call: Generate the system prompt
        prompt_instruction = f"""{template_with_data}

CHART VISUALIZATION RULES (MUST BE APPENDED TO THE GENERATED PROMPT):
{chart_rules}

**CRITICAL**: The generated system prompt MUST include the CHART VISUALIZATION section with the chart generation rules above. This is a KEY FEATURE.

Return ONLY the system prompt text. Do not include any other text or explanations."""

        messages = [
            SystemMessage(content=system_role),
            HumanMessage(content=prompt_instruction)
        ]
        
        # Invoke LLM for system prompt
        response = llm.invoke(messages)
        prompt_content = response.content.strip()
        
        # Clean up the prompt content - remove any unwanted prefixes
        import re
        # Remove "### PART 1: System Prompt" or similar headers
        pattern1 = r'^###?\s*PART\s*1[:\s]*System\s*Prompt\s*\n*'
        prompt_content = re.sub(pattern1, '', prompt_content, flags=re.IGNORECASE).strip()
        # Remove "### System Prompt" headers  
        pattern2 = r'^###?\s*System\s*Prompt\s*\n*'
        prompt_content = re.sub(pattern2, '', prompt_content, flags=re.IGNORECASE).strip()
        # Ensure it starts with a proper header
        if not prompt_content.startswith("#"):
            prompt_content = "# SYSTEM PROMPT\n\n" + prompt_content
        
        # Second LLM call: Generate reasoning and example questions using template
        reasoning_template = get_reasoning_generator_prompt()
        reasoning_instruction = reasoning_template.replace("{data_dictionary}", data_dict_text)

        reasoning_messages = [
            SystemMessage(content="You are a data analyst. Return only valid JSON, no markdown formatting or extra text."),
            HumanMessage(content=reasoning_instruction)
        ]
        
        # Invoke LLM for reasoning/questions
        reasoning = {}
        questions = []
        try:
            logger.info("Invoking LLM for reasoning and example questions...")
            reasoning_response = llm.invoke(reasoning_messages)
            reasoning_text = reasoning_response.content.strip()
            logger.debug(f"Raw reasoning response: {reasoning_text[:500]}...")
            
            # Clean up JSON - remove markdown code blocks if present
            reasoning_text = reasoning_text.replace("```json", "").replace("```", "").strip()
            
            # Try to find JSON object in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', reasoning_text)
            if json_match:
                reasoning_text = json_match.group()
            
            parsed = json.loads(reasoning_text)
            reasoning = parsed.get("selection_reasoning", {})
            questions = parsed.get("example_questions", [])
            logger.info(f"Successfully parsed reasoning with {len(reasoning)} items and {len(questions)} questions")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse reasoning JSON: {e}. Response was: {reasoning_text[:200] if 'reasoning_text' in dir() else 'N/A'}")
        except Exception as e:
            logger.error(f"Error during reasoning generation: {type(e).__name__}: {e}")
        
        return {
            "draft_prompt": prompt_content,
            "reasoning": reasoning,
            "example_questions": questions,
        }
