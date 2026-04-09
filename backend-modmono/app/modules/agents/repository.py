"""
Repository for agents, data sources, and configurations.

Provides data access operations for the simplified schema:
- AgentRepository: Agent CRUD
- DataSourceRepository: Database + file source CRUD
- AgentConfigRepository: Configuration versioning and management
"""
import json
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import and_, or_, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database.base_repository import BaseRepository
from app.core.utils.logging import get_logger
from app.modules.agents.models import (
    AgentModel, AgentConfigModel, UserAgentModel
)
from app.modules.users.models import UserModel
from app.modules.data_sources.models import DataSourceModel
from app.modules.agents.schemas import (
    AgentCreate, AgentUpdate, AgentResponse,
    DataSourceResponse, AgentConfigResponse, UserAgentResponse
)

logger = get_logger(__name__)


class AgentRepository(BaseRepository[AgentModel, AgentCreate, AgentUpdate, AgentResponse]):
    """
    Repository for agent CRUD operations.
    """
    
    def __init__(self, session: AsyncSession):
        super().__init__(session=session, model=AgentModel, response_schema=AgentResponse)
        self.db = self.session  # Alias for compatibility
    
    async def get_by_title(self, title: str) -> Optional[AgentResponse]:
        """Get agent by unique title."""
        query = select(AgentModel).where(AgentModel.title == title)
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        return self._to_pydantic(agent) if agent else None
    
    async def get_with_active_config(self, agent_id: UUID) -> Optional[Dict[str, Any]]:
        """Get agent with its active configuration and data source."""
        query = (
            select(AgentModel)
            .options(
                selectinload(AgentModel.configs).selectinload(AgentConfigModel.data_source)
            )
            .where(AgentModel.id == agent_id)
        )
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return None
        
        # Find active config
        active_config = next(
            (c for c in agent.configs if c.is_active == 1),
            None
        )
        
        agent_dict = self._to_pydantic(agent).model_dump()
        
        if active_config:
            agent_dict["active_config"] = _config_to_dict(active_config)
        
        return agent_dict
    
    async def search_agents(
        self,
        query: Optional[str] = None,
        created_by: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AgentResponse], int]:
        """Search agents with filters."""
        filters = []
        
        if query:
            filters.append(
                or_(
                    AgentModel.title.ilike(f"%{query}%"),
                    AgentModel.description.ilike(f"%{query}%"),
                )
            )
        
        if created_by:
            filters.append(AgentModel.created_by == created_by)
        
        base_query = select(AgentModel)
        if filters:
            base_query = base_query.where(and_(*filters))
        
        # Count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await self.db.execute(count_query)).scalar_one()
        
        # Results
        stmt = base_query.offset(skip).limit(limit).order_by(AgentModel.created_at.desc())
        result = await self.db.execute(stmt)
        
        return [self._to_pydantic(a) for a in result.scalars().all()], total
    
    async def get_accessible_agents(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get agents accessible to a user with their roles."""
        base_query = (
            select(AgentModel, UserAgentModel.role)
            .join(UserAgentModel, AgentModel.id == UserAgentModel.agent_id)
            .where(UserAgentModel.user_id == user_id)
        )
        
        # Count
        count_query = select(func.count()).select_from(
            select(AgentModel.id)
            .join(UserAgentModel)
            .where(UserAgentModel.user_id == user_id)
            .subquery()
        )
        total = (await self.db.execute(count_query)).scalar_one()
        
        # Results with role
        stmt = base_query.offset(skip).limit(limit).order_by(AgentModel.created_at.desc())
        result = await self.db.execute(stmt)
        
        agents = []
        for agent, role in result.all():
            agent_dict = self._to_pydantic(agent).model_dump()
            agent_dict["user_role"] = role
            agents.append(agent_dict)
        
        return agents, total


class AgentConfigRepository:
    """Repository for agent configuration management."""
    
    def __init__(self, session: AsyncSession):
        self.db = session
    
    async def create(
        self,
        agent_id: UUID,
        data_source_id: UUID,
        config_data: Dict[str, Any],
        is_active: bool = True,
    ) -> AgentConfigModel:
        """
        Create a new agent configuration.
        
        If is_active=True, deactivates all other configs for this agent.
        Auto-increments version based on existing configs.
        """
        # Get next version number
        version = await self._get_next_version(agent_id)
        
        # Deactivate existing configs if this is active
        if is_active:
            await self._deactivate_configs(agent_id)
        
        # Serialize JSON fields
        config = AgentConfigModel(
            agent_id=agent_id,
            data_source_id=data_source_id,
            version=version,
            is_active=1 if is_active else 0,
            selected_columns=json.dumps(config_data.get("selected_columns")) if config_data.get("selected_columns") else None,
            data_dictionary=json.dumps(config_data.get("data_dictionary")) if config_data.get("data_dictionary") else None,
            llm_config=json.dumps(config_data.get("llm_config")) if config_data.get("llm_config") else None,
            embedding_config=json.dumps(config_data.get("embedding_config")) if config_data.get("embedding_config") else None,
            chunking_config=json.dumps(config_data.get("chunking_config")) if config_data.get("chunking_config") else None,
            rag_config=json.dumps(config_data.get("rag_config")) if config_data.get("rag_config") else None,
            system_prompt=config_data.get("system_prompt"),
            example_questions=json.dumps(config_data.get("example_questions")) if config_data.get("example_questions") else None,
            embedding_path=config_data.get("embedding_path"),
            vector_collection_name=config_data.get("vector_collection_name"),
            embedding_status=config_data.get("embedding_status", "not_started"),
        )
        
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return config
    
    async def get_by_id(self, config_id: int) -> Optional[AgentConfigModel]:
        """Get config by ID."""
        query = (
            select(AgentConfigModel)
            .options(selectinload(AgentConfigModel.data_source))
            .where(AgentConfigModel.id == config_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_active_config(self, agent_id: UUID) -> Optional[AgentConfigModel]:
        """Get the active configuration for an agent."""
        query = (
            select(AgentConfigModel)
            .options(selectinload(AgentConfigModel.data_source))
            .where(
                and_(
                    AgentConfigModel.agent_id == agent_id,
                    AgentConfigModel.is_active == 1,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_config_history(self, agent_id: UUID) -> List[AgentConfigModel]:
        """Get all configurations for an agent (version history)."""
        query = (
            select(AgentConfigModel)
            .options(selectinload(AgentConfigModel.data_source))
            .where(AgentConfigModel.agent_id == agent_id)
            .order_by(AgentConfigModel.version.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_config_history_paginated(
        self,
        agent_id: UUID,
        page: int = 1,
        page_size: int = 10,
    ) -> Tuple[List[AgentConfigModel], int]:
        """Get paginated configurations for an agent (version history).
        
        Returns:
            Tuple of (configs, total_count)
        """
        # Get total count
        count_query = (
            select(func.count())
            .select_from(AgentConfigModel)
            .where(AgentConfigModel.agent_id == agent_id)
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Get paginated configs
        offset = (page - 1) * page_size
        query = (
            select(AgentConfigModel)
            .options(selectinload(AgentConfigModel.data_source))
            .where(AgentConfigModel.agent_id == agent_id)
            .order_by(AgentConfigModel.version.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        configs = list(result.scalars().all())
        
        return configs, total
    
    async def update(self, config_id: int, config_data: Dict[str, Any]) -> Optional[AgentConfigModel]:
        """Update a configuration."""
        config = await self.get_by_id(config_id)
        if not config:
            return None
        
        # Update JSON fields
        if "selected_columns" in config_data:
            config.selected_columns = json.dumps(config_data["selected_columns"]) if config_data["selected_columns"] else None
        if "data_dictionary" in config_data:
            config.data_dictionary = json.dumps(config_data["data_dictionary"]) if config_data["data_dictionary"] else None
        if "llm_config" in config_data:
            config.llm_config = json.dumps(config_data["llm_config"]) if config_data["llm_config"] else None
        if "embedding_config" in config_data:
            config.embedding_config = json.dumps(config_data["embedding_config"]) if config_data["embedding_config"] else None
        if "chunking_config" in config_data:
            config.chunking_config = json.dumps(config_data["chunking_config"]) if config_data["chunking_config"] else None
        if "rag_config" in config_data:
            config.rag_config = json.dumps(config_data["rag_config"]) if config_data["rag_config"] else None
        
        # Update simple fields
        if "system_prompt" in config_data:
            config.system_prompt = config_data["system_prompt"]
        if "example_questions" in config_data:
            config.example_questions = json.dumps(config_data["example_questions"]) if config_data["example_questions"] else None
        if "data_source_id" in config_data:
            config.data_source_id = config_data["data_source_id"]
        if "completed_step" in config_data:
            config.completed_step = config_data["completed_step"]
        if "status" in config_data:
            config.status = config_data["status"]
        
        # Update AI Registry model IDs (foreign keys to ai_models.id)
        if "llm_model_id" in config_data:
            config.llm_model_id = config_data["llm_model_id"]
        if "embedding_model_id" in config_data:
            config.embedding_model_id = config_data["embedding_model_id"]
        if "reranker_model_id" in config_data:
            config.reranker_model_id = config_data["reranker_model_id"]
        
        await self.db.flush()
        await self.db.refresh(config)
        # Re-fetch with relationships loaded
        return await self.get_by_id(config.id)
    
    async def activate_config(self, config_id: int) -> bool:
        """Activate a config and deactivate all others for the agent."""
        config = await self.get_by_id(config_id)
        if not config:
            return False
        
        await self._deactivate_configs(config.agent_id)
        config.is_active = 1
        await self.db.flush()
        return True
    
    async def update_embedding_status(
        self,
        config_id: int,
        status: str,
        embedding_path: Optional[str] = None,
        vector_collection_name: Optional[str] = None,
    ) -> bool:
        """Update embedding status for a config."""
        config = await self.get_by_id(config_id)
        if not config:
            return False
        
        config.embedding_status = status
        if embedding_path is not None:
            config.embedding_path = embedding_path
        if vector_collection_name is not None:
            config.vector_collection_name = vector_collection_name
        
        await self.db.flush()
        return True
    
    async def _get_next_version(self, agent_id: UUID) -> int:
        """Get the next version number for an agent's config."""
        query = (
            select(func.max(AgentConfigModel.version))
            .where(AgentConfigModel.agent_id == agent_id)
        )
        result = await self.db.execute(query)
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1
    
    async def _deactivate_configs(self, agent_id: UUID) -> None:
        """Deactivate all configs for an agent."""
        stmt = (
            update(AgentConfigModel)
            .where(AgentConfigModel.agent_id == agent_id)
            .values(is_active=0)
        )
        await self.db.execute(stmt)
    
    async def get_draft_config(self, agent_id: UUID) -> Optional[AgentConfigModel]:
        """Get the draft configuration for an agent (if exists)."""
        query = (
            select(AgentConfigModel)
            .options(selectinload(AgentConfigModel.data_source))
            .where(
                and_(
                    AgentConfigModel.agent_id == agent_id,
                    AgentConfigModel.status == "draft",
                )
            )
            .order_by(AgentConfigModel.version.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def create_draft(
        self,
        agent_id: UUID,
        data_source_id: UUID,
        config_data: Optional[Dict[str, Any]] = None,
    ) -> AgentConfigModel:
        """Create a new draft configuration for an agent."""
        config_data = config_data or {}
        version = await self._get_next_version(agent_id)
        
        config = AgentConfigModel(
            agent_id=agent_id,
            data_source_id=data_source_id,
            version=version,
            is_active=0,  # Drafts are not active
            status="draft",
            completed_step=0,  # No steps completed yet
            selected_columns=json.dumps(config_data.get("selected_columns")) if config_data.get("selected_columns") else None,
            data_dictionary=json.dumps(config_data.get("data_dictionary")) if config_data.get("data_dictionary") else None,
            llm_config=json.dumps(config_data.get("llm_config")) if config_data.get("llm_config") else None,
            embedding_config=json.dumps(config_data.get("embedding_config")) if config_data.get("embedding_config") else None,
            chunking_config=json.dumps(config_data.get("chunking_config")) if config_data.get("chunking_config") else None,
            rag_config=json.dumps(config_data.get("rag_config")) if config_data.get("rag_config") else None,
            # AI Registry model IDs (foreign keys to ai_models.id)
            llm_model_id=config_data.get("llm_model_id"),
            embedding_model_id=config_data.get("embedding_model_id"),
            reranker_model_id=config_data.get("reranker_model_id"),
            system_prompt=config_data.get("system_prompt"),
            example_questions=json.dumps(config_data.get("example_questions")) if config_data.get("example_questions") else None,
            embedding_path=config_data.get("embedding_path"),
            vector_collection_name=config_data.get("vector_collection_name"),
            embedding_status="not_started",
        )
        
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        # Re-fetch with relationships loaded
        return await self.get_by_id(config.id)
    
    async def update_step_data(
        self,
        config_id: int,
        step: int,
        data: Dict[str, Any],
    ) -> Optional[AgentConfigModel]:
        """Update step-specific data and completed_step for a config."""
        config = await self.get_by_id(config_id)
        if not config:
            return None
        
        # Map step number to fields
        step_field_mapping = {
            1: {"data_source_id"},  # Data source selection
            2: {"selected_columns", "data_dictionary"},  # Schema selection
            3: {"llm_config", "embedding_config", "chunking_config"},  # Model config
            4: {"rag_config"},  # RAG config
            5: {"system_prompt", "example_questions"},  # Prompts
            6: {"embedding_path", "vector_collection_name"},  # Vector store
        }
        
        allowed_fields = step_field_mapping.get(step, set())
        
        for field, value in data.items():
            if field not in allowed_fields:
                continue
            
            if field == "data_source_id":
                config.data_source_id = value
            elif field == "selected_columns":
                config.selected_columns = json.dumps(value) if value else None
            elif field == "data_dictionary":
                config.data_dictionary = json.dumps(value) if value else None
            elif field == "llm_config":
                config.llm_config = json.dumps(value) if value else None
            elif field == "embedding_config":
                config.embedding_config = json.dumps(value) if value else None
            elif field == "chunking_config":
                config.chunking_config = json.dumps(value) if value else None
            elif field == "rag_config":
                config.rag_config = json.dumps(value) if value else None
            elif field == "system_prompt":
                config.system_prompt = value
            elif field == "example_questions":
                config.example_questions = json.dumps(value) if value else None
            elif field == "embedding_path":
                config.embedding_path = value
            elif field == "vector_collection_name":
                config.vector_collection_name = value
        
        # Update completed_step if progressing forward
        if step > config.completed_step:
            config.completed_step = step
        
        await self.db.flush()
        await self.db.refresh(config)
        return config
    
    async def publish_draft(self, config_id: int) -> Optional[AgentConfigModel]:
        """Publish a draft config (activates it but keeps status as draft until embedding completes)."""
        config = await self.get_by_id(config_id)
        if not config or config.status != "draft":
            return None
        
        # Deactivate other configs
        await self._deactivate_configs(config.agent_id)
        
        # Activate but keep status as draft - will be set to published when embedding completes
        config.is_active = 1
        
        await self.db.flush()
        await self.db.refresh(config)
        return config
    
    async def clone_config_as_draft(
        self,
        source_config_id: int,
    ) -> Optional[AgentConfigModel]:
        """Create a new draft config by cloning an existing config."""
        source = await self.get_by_id(source_config_id)
        if not source:
            return None
        
        version = await self._get_next_version(source.agent_id)
        
        config = AgentConfigModel(
            agent_id=source.agent_id,
            data_source_id=source.data_source_id,
            version=version,
            is_active=0,
            status="draft",
            completed_step=5,  # Cloned config has all steps completed
            selected_columns=source.selected_columns,
            data_dictionary=source.data_dictionary,
            llm_config=source.llm_config,
            embedding_config=source.embedding_config,
            chunking_config=source.chunking_config,
            rag_config=source.rag_config,
            system_prompt=source.system_prompt,
            example_questions=source.example_questions,
            embedding_path=source.embedding_path,
            vector_collection_name=source.vector_collection_name,
            embedding_status="not_started",  # Reset embedding status
        )
        
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)
        return config


class UserAgentRepository:
    """Repository for user-agent access control."""
    
    def __init__(self, session: AsyncSession):
        self.db = session
    
    async def grant_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        role: str = "user",
        granted_by: Optional[UUID] = None,
    ) -> UserAgentModel:
        """Grant user access to an agent."""
        # Check if already has access
        existing = await self.get_access(user_id, agent_id)
        if existing:
            # Update role
            existing.role = role
            await self.db.flush()
            return existing
        
        user_agent = UserAgentModel(
            user_id=user_id,
            agent_id=agent_id,
            role=role,
            granted_by=granted_by,
        )
        self.db.add(user_agent)
        await self.db.flush()
        await self.db.refresh(user_agent)
        return user_agent
    
    async def revoke_access(self, user_id: UUID, agent_id: UUID) -> bool:
        """Revoke user's access to an agent."""
        existing = await self.get_access(user_id, agent_id)
        if not existing:
            return False
        
        await self.db.delete(existing)
        await self.db.flush()
        return True
    
    async def get_access(self, user_id: UUID, agent_id: UUID) -> Optional[UserAgentModel]:
        """Get user's access record for an agent."""
        query = select(UserAgentModel).where(
            and_(
                UserAgentModel.user_id == user_id,
                UserAgentModel.agent_id == agent_id,
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def has_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        min_role: str = "user",
    ) -> bool:
        """Check if user has access with minimum role."""
        role_levels = {"user": 0, "editor": 1, "admin": 2}
        
        access = await self.get_access(user_id, agent_id)
        if not access:
            return False
        
        return role_levels.get(access.role, 0) >= role_levels.get(min_role, 0)
    
    async def get_agent_users(self, agent_id: UUID) -> List[UserAgentResponse]:
        """Get all users with access to an agent using explicit JOIN with specific columns."""
        query = (
            select(
                # User agent columns
                UserAgentModel.user_id,
                UserAgentModel.user_id.label("id"),
                UserAgentModel.agent_id,
                UserAgentModel.role,
                UserAgentModel.granted_at,
                UserAgentModel.granted_by,
                # User columns
                UserModel.username,
                UserModel.email,
                UserModel.full_name,
                UserModel.is_active,
            )
            .join(UserModel, UserAgentModel.user_id == UserModel.id)
            .where(UserAgentModel.agent_id == agent_id)
        )
        result = await self.db.execute(query)
        rows = result.all()
        
        return [UserAgentResponse(**row._asdict()) for row in rows]
    
    async def get_user_agents(self, user_id: UUID) -> List[UserAgentModel]:
        """Get all agents a user has access to."""
        query = select(UserAgentModel).where(UserAgentModel.user_id == user_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())


# ==========================================
# Helper Functions
# ==========================================

def _config_to_dict(config: AgentConfigModel) -> Dict[str, Any]:
    """Convert AgentConfigModel to dictionary with parsed JSON fields."""
    # Build data_source dict with all required fields
    data_source_dict = None
    if config.data_source:
        ds = config.data_source
        data_source_dict = {
            "id": str(ds.id),
            "title": ds.title,
            "description": ds.description,
            "source_type": ds.source_type,
            "db_url": ds.db_url,
            "db_engine_type": ds.db_engine_type,
            "original_file_path": ds.original_file_path,
            "file_type": ds.file_type,
            "duckdb_file_path": ds.duckdb_file_path,
            "duckdb_table_name": ds.duckdb_table_name,
            "columns_json": ds.columns_json,
            "row_count": ds.row_count,
            "created_by": str(ds.created_by) if ds.created_by else None,
            "created_at": ds.created_at,
            "updated_at": ds.updated_at,
        }
    
    # Parse JSON configs
    llm_config = json.loads(config.llm_config) if config.llm_config else None
    embedding_config = json.loads(config.embedding_config) if config.embedding_config else None
    rag_config = json.loads(config.rag_config) if config.rag_config else None
    
    # Strip redundant model fields when model IDs are set
    if llm_config and config.llm_model_id:
        llm_config.pop("model", None)
    if embedding_config and config.embedding_model_id:
        embedding_config.pop("model", None)
    if rag_config and config.reranker_model_id:
        rag_config.pop("reranker_model", None)
    
    return {
        "id": config.id,
        "agent_id": str(config.agent_id),
        "data_source_id": str(config.data_source_id),
        "selected_columns": json.loads(config.selected_columns) if config.selected_columns else None,
        "data_dictionary": json.loads(config.data_dictionary) if config.data_dictionary else None,
        "llm_config": llm_config,
        "embedding_config": embedding_config,
        "chunking_config": json.loads(config.chunking_config) if config.chunking_config else None,
        "rag_config": rag_config,
        # AI Registry model IDs (foreign keys to ai_models.id)
        "llm_model_id": config.llm_model_id,
        "embedding_model_id": config.embedding_model_id,
        "reranker_model_id": config.reranker_model_id,
        "system_prompt": config.system_prompt,
        "example_questions": json.loads(config.example_questions) if config.example_questions else None,
        "embedding_path": config.embedding_path,
        "vector_collection_name": config.vector_collection_name,
        "embedding_status": config.embedding_status,
        "version": config.version,
        "is_active": bool(config.is_active),
        "status": config.status,
        "completed_step": config.completed_step,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
        "data_source": data_source_dict,
    }
