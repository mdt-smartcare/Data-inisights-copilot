"""
Repository for agent data access operations.
"""
import json
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database.base_repository import BaseRepository
from app.modules.agents.models import (
    AgentModel, UserAgentModel, SystemPromptModel, PromptConfigModel
)
from app.modules.agents.schemas import (
    AgentCreate, AgentUpdate, Agent, 
    SystemPromptCreate, PromptConfigCreate
)


class AgentRepository(BaseRepository[AgentModel, AgentCreate, AgentUpdate, Agent]):
    """
    Repository for agent-related database operations.
    
    Handles CRUD operations for agents and their configurations,
    including system prompts, prompt configs, and user-agent relationships.
    """
    
    def __init__(self, session: AsyncSession):
        super().__init__(AgentModel, AgentCreate, AgentUpdate, Agent, session)
    
    # ==========================================
    # Agent Queries
    # ==========================================
    
    async def get_by_name(self, name: str) -> Optional[Agent]:
        """Get agent by unique name."""
        query = select(AgentModel).where(AgentModel.name == name)
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        return self._to_pydantic(agent) if agent else None
    
    async def get_with_config(self, agent_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get agent with its active configuration.
        
        Returns agent data plus active system prompt and prompt config.
        """
        # Get agent with relationships
        query = (
            select(AgentModel)
            .options(
                selectinload(AgentModel.system_prompts).selectinload(SystemPromptModel.prompt_config)
            )
            .where(AgentModel.id == agent_id)
        )
        result = await self.db.execute(query)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return None
        
        # Find active system prompt
        active_prompt = next(
            (sp for sp in agent.system_prompts if sp.is_active == 1), 
            None
        )
        
        agent_dict = self._to_pydantic(agent).model_dump()
        
        if active_prompt:
            agent_dict["active_system_prompt"] = {
                "id": active_prompt.id,
                "prompt_text": active_prompt.prompt_text,
                "version": active_prompt.version,
                "created_at": active_prompt.created_at,
            }
            
            # Add prompt config if exists
            if active_prompt.prompt_config:
                pc = active_prompt.prompt_config
                agent_dict["config"] = {
                    "connection_id": pc.connection_id,
                    "schema_selection": pc.schema_selection,
                    "data_dictionary": pc.data_dictionary,
                    "reasoning": pc.reasoning,
                    "example_questions": pc.example_questions,
                    "data_source_type": pc.data_source_type,
                    "embedding_config": json.loads(pc.embedding_config) if pc.embedding_config else None,
                    "retriever_config": json.loads(pc.retriever_config) if pc.retriever_config else None,
                    "chunking_config": json.loads(pc.chunking_config) if pc.chunking_config else None,
                    "llm_config": json.loads(pc.llm_config) if pc.llm_config else None,
                }
        
        return agent_dict
    
    async def search_agents(
        self,
        query: Optional[str] = None,
        agent_type: Optional[str] = None,
        created_by: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Agent], int]:
        """
        Search agents with filters.
        
        Args:
            query: Text search in name/description
            agent_type: Filter by agent type (sql, rag, hybrid)
            created_by: Filter by creator user ID
            skip: Pagination offset
            limit: Max results
        
        Returns:
            Tuple of (agents list, total count)
        """
        filters = []
        
        if query:
            search_filter = or_(
                AgentModel.name.ilike(f"%{query}%"),
                AgentModel.description.ilike(f"%{query}%"),
            )
            filters.append(search_filter)
        
        if agent_type:
            filters.append(AgentModel.type == agent_type)
        
        if created_by:
            filters.append(AgentModel.created_by == created_by)
        
        # Build query
        base_query = select(AgentModel)
        if filters:
            base_query = base_query.where(and_(*filters))
        
        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()
        
        # Get paginated results
        query_stmt = base_query.offset(skip).limit(limit).order_by(AgentModel.created_at.desc())
        result = await self.db.execute(query_stmt)
        agents = result.scalars().all()
        
        return [self._to_pydantic(agent) for agent in agents], total
    
    async def get_accessible_agents(
        self,
        user_id: UUID,
        role_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Agent], int]:
        """
        Get agents accessible to a specific user.
        
        Args:
            user_id: User ID to check access for
            role_filter: Optional filter by user's role on agent (user, editor, admin)
            skip: Pagination offset
            limit: Max results
        
        Returns:
            Tuple of (agents list, total count)
        """
        # Base query joins agents with user_agents table
        base_query = (
            select(AgentModel)
            .join(UserAgentModel, AgentModel.id == UserAgentModel.agent_id)
            .where(UserAgentModel.user_id == user_id)
        )
        
        if role_filter:
            base_query = base_query.where(UserAgentModel.role == role_filter)
        
        # Count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()
        
        # Get results
        query_stmt = base_query.offset(skip).limit(limit).order_by(AgentModel.created_at.desc())
        result = await self.db.execute(query_stmt)
        agents = result.scalars().all()
        
        return [self._to_pydantic(agent) for agent in agents], total
    
    async def user_has_access(self, user_id: UUID, agent_id: UUID, min_role: str = "user") -> bool:
        """
        Check if user has access to agent with minimum role.
        
        Args:
            user_id: User ID to check
            agent_id: Agent ID to check access for
            min_role: Minimum required role (user, editor, admin)
        
        Returns:
            True if user has access with sufficient role
        """
        role_hierarchy = {"user": 0, "editor": 1, "admin": 2}
        min_level = role_hierarchy.get(min_role, 0)
        
        query = (
            select(UserAgentModel.role)
            .where(
                and_(
                    UserAgentModel.user_id == user_id,
                    UserAgentModel.agent_id == agent_id,
                )
            )
        )
        result = await self.db.execute(query)
        user_role = result.scalar_one_or_none()
        
        if not user_role:
            return False
        
        user_level = role_hierarchy.get(user_role, 0)
        return user_level >= min_level
    
    # ==========================================
    # User-Agent Relationship Management
    # ==========================================
    
    async def grant_user_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        role: str = "user",
        granted_by: Optional[UUID] = None,
    ) -> None:
        """Grant a user access to an agent with a specific role."""
        user_agent = UserAgentModel(
            user_id=user_id,
            agent_id=agent_id,
            role=role,
            granted_by=granted_by,
        )
        self.db.add(user_agent)
        await self.db.flush()
    
    async def revoke_user_access(self, user_id: UUID, agent_id: UUID) -> bool:
        """
        Revoke a user's access to an agent.
        
        Returns:
            True if access was revoked, False if no access existed
        """
        query = select(UserAgentModel).where(
            and_(
                UserAgentModel.user_id == user_id,
                UserAgentModel.agent_id == agent_id,
            )
        )
        result = await self.db.execute(query)
        user_agent = result.scalar_one_or_none()
        
        if user_agent:
            await self.db.delete(user_agent)
            await self.db.flush()
            return True
        return False
    
    async def update_user_role(self, user_id: UUID, agent_id: UUID, new_role: str) -> bool:
        """
        Update a user's role on an agent.
        
        Returns:
            True if role was updated, False if no access existed
        """
        query = select(UserAgentModel).where(
            and_(
                UserAgentModel.user_id == user_id,
                UserAgentModel.agent_id == agent_id,
            )
        )
        result = await self.db.execute(query)
        user_agent = result.scalar_one_or_none()
        
        if user_agent:
            user_agent.role = new_role
            await self.db.flush()
            return True
        return False
    
    async def get_agent_users(self, agent_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all users who have access to an agent.
        
        Returns:
            List of dicts with user_id, role, granted_at
        """
        query = select(UserAgentModel).where(UserAgentModel.agent_id == agent_id)
        result = await self.db.execute(query)
        user_agents = result.scalars().all()
        
        return [
            {
                "user_id": ua.user_id,
                "role": ua.role,
                "granted_at": ua.granted_at,
                "granted_by": ua.granted_by,
            }
            for ua in user_agents
        ]
    
    # ==========================================
    # System Prompt Management
    # ==========================================
    
    async def create_system_prompt(
        self,
        agent_id: UUID,
        prompt_text: str,
        version: int,
        is_active: bool = False,
        created_by: Optional[str] = None,
    ) -> int:
        """
        Create a new system prompt for an agent.
        
        Returns:
            The created prompt ID
        """
        # If marking as active, deactivate all other prompts for this agent
        if is_active:
            await self._deactivate_agent_prompts(agent_id)
        
        prompt = SystemPromptModel(
            prompt_text=prompt_text,
            version=version,
            is_active=1 if is_active else 0,
            created_by=created_by,
            agent_id=agent_id,
        )
        self.db.add(prompt)
        await self.db.flush()
        await self.db.refresh(prompt)
        return prompt.id
    
    async def activate_system_prompt(self, prompt_id: int, agent_id: UUID) -> None:
        """Activate a system prompt and deactivate all others for the agent."""
        # Deactivate all prompts for this agent
        await self._deactivate_agent_prompts(agent_id)
        
        # Activate the specified prompt
        query = select(SystemPromptModel).where(SystemPromptModel.id == prompt_id)
        result = await self.db.execute(query)
        prompt = result.scalar_one_or_none()
        
        if prompt:
            prompt.is_active = 1
            await self.db.flush()
    
    async def get_active_system_prompt(self, agent_id: UUID) -> Optional[Dict[str, Any]]:
        """Get the active system prompt for an agent."""
        query = (
            select(SystemPromptModel)
            .where(
                and_(
                    SystemPromptModel.agent_id == agent_id,
                    SystemPromptModel.is_active == 1,
                )
            )
        )
        result = await self.db.execute(query)
        prompt = result.scalar_one_or_none()
        
        if prompt:
            return {
                "id": prompt.id,
                "prompt_text": prompt.prompt_text,
                "version": prompt.version,
                "created_at": prompt.created_at,
                "created_by": prompt.created_by,
            }
        return None
    
    async def _deactivate_agent_prompts(self, agent_id: UUID) -> None:
        """Helper: Deactivate all system prompts for an agent."""
        query = (
            select(SystemPromptModel)
            .where(
                and_(
                    SystemPromptModel.agent_id == agent_id,
                    SystemPromptModel.is_active == 1,
                )
            )
        )
        result = await self.db.execute(query)
        prompts = result.scalars().all()
        
        for prompt in prompts:
            prompt.is_active = 0
        await self.db.flush()
    
    # ==========================================
    # Prompt Config Management
    # ==========================================
    
    async def create_prompt_config(
        self,
        prompt_id: int,
        config_data: Dict[str, Any],
    ) -> None:
        """
        Create or update prompt configuration.
        
        Args:
            prompt_id: System prompt ID to attach config to
            config_data: Dictionary with configuration fields
        """
        # Check if config already exists
        query = select(PromptConfigModel).where(PromptConfigModel.prompt_id == prompt_id)
        result = await self.db.execute(query)
        existing_config = result.scalar_one_or_none()
        
        # Serialize JSON fields
        embedding_config_json = json.dumps(config_data.get("embedding_config")) if config_data.get("embedding_config") else None
        retriever_config_json = json.dumps(config_data.get("retriever_config")) if config_data.get("retriever_config") else None
        chunking_config_json = json.dumps(config_data.get("chunking_config")) if config_data.get("chunking_config") else None
        llm_config_json = json.dumps(config_data.get("llm_config")) if config_data.get("llm_config") else None
        
        if existing_config:
            # Update existing
            existing_config.connection_id = config_data.get("connection_id")
            existing_config.schema_selection = config_data.get("schema_selection")
            existing_config.data_dictionary = config_data.get("data_dictionary")
            existing_config.reasoning = config_data.get("reasoning")
            existing_config.example_questions = config_data.get("example_questions")
            existing_config.data_source_type = config_data.get("data_source_type", "database")
            existing_config.embedding_config = embedding_config_json
            existing_config.retriever_config = retriever_config_json
            existing_config.chunking_config = chunking_config_json
            existing_config.llm_config = llm_config_json
        else:
            # Create new
            config = PromptConfigModel(
                prompt_id=prompt_id,
                connection_id=config_data.get("connection_id"),
                schema_selection=config_data.get("schema_selection"),
                data_dictionary=config_data.get("data_dictionary"),
                reasoning=config_data.get("reasoning"),
                example_questions=config_data.get("example_questions"),
                data_source_type=config_data.get("data_source_type", "database"),
                embedding_config=embedding_config_json,
                retriever_config=retriever_config_json,
                chunking_config=chunking_config_json,
                llm_config=llm_config_json,
            )
            self.db.add(config)
        
        await self.db.flush()
    
    async def get_prompt_config(self, prompt_id: int) -> Optional[Dict[str, Any]]:
        """Get prompt configuration with deserialized JSON fields."""
        query = select(PromptConfigModel).where(PromptConfigModel.prompt_id == prompt_id)
        result = await self.db.execute(query)
        config = result.scalar_one_or_none()
        
        if not config:
            return None
        
        return {
            "prompt_id": config.prompt_id,
            "connection_id": config.connection_id,
            "schema_selection": config.schema_selection,
            "data_dictionary": config.data_dictionary,
            "reasoning": config.reasoning,
            "example_questions": config.example_questions,
            "data_source_type": config.data_source_type,
            "embedding_config": json.loads(config.embedding_config) if config.embedding_config else None,
            "retriever_config": json.loads(config.retriever_config) if config.retriever_config else None,
            "chunking_config": json.loads(config.chunking_config) if config.chunking_config else None,
            "llm_config": json.loads(config.llm_config) if config.llm_config else None,
        }
