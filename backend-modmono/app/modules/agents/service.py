"""
Business logic for agent management.
"""
import json
from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.defaults import get_system_defaults
from app.core.exceptions import AppException, ErrorCode
from app.modules.agents.repository import AgentRepository
from app.modules.agents.schemas import (
    Agent, AgentCreate, AgentUpdate, AgentWithConfig,
    UserAgentAccess, UserAgentResponse,
    SystemPromptCreate, SystemPromptResponse,
    PromptConfigCreate, PromptConfigResponse,
)


class AgentService:
    """
    Service for agent management operations.
    
    Handles:
    - Agent CRUD with default configuration initialization
    - Agent configuration management (8 config types)
    - User-agent access control (RBAC)
    - System prompt versioning
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AgentRepository(db)
    
    # ==========================================
    # Agent CRUD Operations
    # ==========================================
    
    async def create_agent(
        self,
        agent_data: AgentCreate,
        created_by: UUID,
        initialize_defaults: bool = True,
    ) -> Agent:
        """
        Create a new agent with optional default configuration.
        
        Args:
            agent_data: Agent creation data
            created_by: User ID creating the agent
            initialize_defaults: If True, creates system prompt with default configs
        
        Returns:
            Created agent
        
        Raises:
            AppException: If agent name already exists
        """
        # Check if agent name already exists
        existing = await self.repo.get_by_name(agent_data.name)
        if existing:
            raise AppException(
                error_code=ErrorCode.RESOURCE_ALREADY_EXISTS,
                message=f"Agent with name '{agent_data.name}' already exists",
                status_code=409,
            )
        
        # Create agent
        agent_dict = agent_data.model_dump()
        agent_dict["created_by"] = created_by
        agent = await self.repo.create(agent_data)
        
        # Initialize with default configuration if requested
        if initialize_defaults:
            defaults = get_system_defaults()
            default_config = defaults.get_agent_creation_defaults()
            
            # Create initial system prompt
            prompt_text = default_config["system_prompts"]["base_system_prompt"]
            prompt_id = await self.repo.create_system_prompt(
                agent_id=agent.id,
                prompt_text=prompt_text,
                version=1,
                is_active=True,
                created_by=str(created_by),
            )
            
            # Create prompt config with defaults
            config_data = {
                "data_source_type": agent_data.type,
                "chunking_config": default_config["chunking"],
                "embedding_config": default_config["embedding"],
                "retriever_config": default_config["rag"],
                "llm_config": default_config["llm"],
            }
            await self.repo.create_prompt_config(prompt_id, config_data)
        
        # Grant creator admin access
        await self.repo.grant_user_access(
            user_id=created_by,
            agent_id=agent.id,
            role="admin",
            granted_by=created_by,
        )
        
        return agent
    
    async def get_agent(self, agent_id: UUID) -> Optional[Agent]:
        """Get agent by ID."""
        return await self.repo.get_by_id(agent_id)
    
    async def get_agent_with_config(self, agent_id: UUID) -> Optional[AgentWithConfig]:
        """Get agent with full active configuration."""
        agent_dict = await self.repo.get_with_config(agent_id)
        if agent_dict:
            return AgentWithConfig(**agent_dict)
        return None
    
    async def update_agent(
        self,
        agent_id: UUID,
        agent_data: AgentUpdate,
    ) -> Optional[Agent]:
        """
        Update agent fields.
        
        Args:
            agent_id: Agent ID to update
            agent_data: Updated fields
        
        Returns:
            Updated agent or None if not found
        
        Raises:
            AppException: If new name already exists
        """
        # Check if agent exists
        existing = await self.repo.get_by_id(agent_id)
        if not existing:
            return None
        
        # If updating name, check for duplicates
        if agent_data.name and agent_data.name != existing.name:
            name_exists = await self.repo.get_by_name(agent_data.name)
            if name_exists:
                raise AppException(
                    error_code=ErrorCode.RESOURCE_ALREADY_EXISTS,
                    message=f"Agent with name '{agent_data.name}' already exists",
                    status_code=409,
                )
        
        # Update
        return await self.repo.update(agent_id, agent_data)
    
    async def delete_agent(self, agent_id: UUID) -> bool:
        """
        Delete an agent (cascades to prompts, configs, user access).
        
        Returns:
            True if deleted, False if not found
        """
        return await self.repo.delete(agent_id)
    
    async def search_agents(
        self,
        query: Optional[str] = None,
        agent_type: Optional[str] = None,
        created_by: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Agent], int]:
        """Search agents with filters and pagination."""
        return await self.repo.search_agents(
            query=query,
            agent_type=agent_type,
            created_by=created_by,
            skip=skip,
            limit=limit,
        )
    
    async def get_accessible_agents(
        self,
        user_id: UUID,
        role_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Agent], int]:
        """
        Get agents accessible to a user.
        
        Args:
            user_id: User ID to check access for
            role_filter: Optional filter by user's role (user, editor, admin)
            skip: Pagination offset
            limit: Max results
        
        Returns:
            Tuple of (agents, total_count)
        """
        return await self.repo.get_accessible_agents(
            user_id=user_id,
            role_filter=role_filter,
            skip=skip,
            limit=limit,
        )
    
    # ==========================================
    # User Access Management
    # ==========================================
    
    async def grant_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        role: str = "user",
        granted_by: Optional[UUID] = None,
    ) -> None:
        """
        Grant a user access to an agent.
        
        Args:
            user_id: User to grant access to
            agent_id: Agent to grant access for
            role: Role to grant (user, editor, admin)
            granted_by: User granting the access
        
        Raises:
            AppException: If agent not found
        """
        # Verify agent exists
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent with ID {agent_id} not found",
                status_code=404,
            )
        
        await self.repo.grant_user_access(
            user_id=user_id,
            agent_id=agent_id,
            role=role,
            granted_by=granted_by,
        )
    
    async def revoke_access(self, user_id: UUID, agent_id: UUID) -> bool:
        """
        Revoke a user's access to an agent.
        
        Returns:
            True if access was revoked, False if no access existed
        """
        return await self.repo.revoke_user_access(user_id, agent_id)
    
    async def update_access_role(
        self,
        user_id: UUID,
        agent_id: UUID,
        new_role: str,
    ) -> bool:
        """
        Update a user's role on an agent.
        
        Returns:
            True if updated, False if user had no access
        """
        return await self.repo.update_user_role(user_id, agent_id, new_role)
    
    async def get_agent_users(self, agent_id: UUID) -> List[UserAgentResponse]:
        """
        Get all users with access to an agent.
        
        Returns:
            List of user-agent relationships
        """
        users_data = await self.repo.get_agent_users(agent_id)
        return [UserAgentResponse(**data) for data in users_data]
    
    async def user_has_access(
        self,
        user_id: UUID,
        agent_id: UUID,
        min_role: str = "user",
    ) -> bool:
        """
        Check if user has access to agent with minimum role.
        
        Args:
            user_id: User to check
            agent_id: Agent to check access for
            min_role: Minimum required role
        
        Returns:
            True if user has sufficient access
        """
        return await self.repo.user_has_access(user_id, agent_id, min_role)
    
    # ==========================================
    # System Prompt Management
    # ==========================================
    
    async def create_system_prompt(
        self,
        agent_id: UUID,
        prompt_data: SystemPromptCreate,
        created_by: str,
    ) -> int:
        """
        Create a new system prompt version for an agent.
        
        Args:
            agent_id: Agent to create prompt for
            prompt_data: Prompt creation data
            created_by: Username of creator
        
        Returns:
            Created prompt ID
        
        Raises:
            AppException: If agent not found
        """
        # Verify agent exists
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent with ID {agent_id} not found",
                status_code=404,
            )
        
        return await self.repo.create_system_prompt(
            agent_id=agent_id,
            prompt_text=prompt_data.prompt_text,
            version=prompt_data.version,
            is_active=prompt_data.is_active,
            created_by=created_by,
        )
    
    async def activate_system_prompt(
        self,
        agent_id: UUID,
        prompt_id: int,
    ) -> None:
        """
        Activate a system prompt (deactivates all others for the agent).
        
        Args:
            agent_id: Agent the prompt belongs to
            prompt_id: Prompt to activate
        """
        await self.repo.activate_system_prompt(prompt_id, agent_id)
    
    async def get_active_prompt(self, agent_id: UUID) -> Optional[SystemPromptResponse]:
        """Get the active system prompt for an agent."""
        prompt_data = await self.repo.get_active_system_prompt(agent_id)
        if prompt_data:
            return SystemPromptResponse(**prompt_data)
        return None
    
    # ==========================================
    # Configuration Management
    # ==========================================
    
    async def update_agent_config(
        self,
        agent_id: UUID,
        config_data: PromptConfigCreate,
        create_new_version: bool = False,
        version: Optional[int] = None,
        created_by: Optional[str] = None,
    ) -> PromptConfigResponse:
        """
        Update agent configuration.
        
        Args:
            agent_id: Agent to update config for
            config_data: New configuration data
            create_new_version: If True, creates a new system prompt version
            version: New version number (required if create_new_version=True)
            created_by: Creator username (required if create_new_version=True)
        
        Returns:
            Updated configuration
        
        Raises:
            AppException: If agent not found or validation fails
        """
        # Verify agent exists
        agent = await self.repo.get_by_id(agent_id)
        if not agent:
            raise AppException(
                error_code=ErrorCode.RESOURCE_NOT_FOUND,
                message=f"Agent with ID {agent_id} not found",
                status_code=404,
            )
        
        # Get or create system prompt
        if create_new_version:
            if version is None or created_by is None:
                raise AppException(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="version and created_by required when creating new version",
                    status_code=400,
                )
            
            # Get active prompt for template
            active_prompt = await self.repo.get_active_system_prompt(agent_id)
            prompt_text = active_prompt["prompt_text"] if active_prompt else agent.system_prompt or "Default prompt"
            
            prompt_id = await self.repo.create_system_prompt(
                agent_id=agent_id,
                prompt_text=prompt_text,
                version=version,
                is_active=True,
                created_by=created_by,
            )
        else:
            # Use active prompt or create initial
            active_prompt = await self.repo.get_active_system_prompt(agent_id)
            if active_prompt:
                prompt_id = active_prompt["id"]
            else:
                # Create initial prompt
                prompt_id = await self.repo.create_system_prompt(
                    agent_id=agent_id,
                    prompt_text=agent.system_prompt or "Default system prompt",
                    version=1,
                    is_active=True,
                    created_by=created_by or "system",
                )
        
        # Prepare config dict with JSON serialization
        config_dict = {
            "connection_id": config_data.connection_id,
            "schema_selection": config_data.schema_selection,
            "data_dictionary": config_data.data_dictionary,
            "reasoning": config_data.reasoning,
            "example_questions": config_data.example_questions,
            "data_source_type": config_data.data_source_type,
            "chunking_config": config_data.chunking_config.model_dump() if config_data.chunking_config else None,
            "embedding_config": config_data.embedding_config.model_dump() if config_data.embedding_config else None,
            "retriever_config": config_data.retriever_config.model_dump() if config_data.retriever_config else None,
            "llm_config": config_data.llm_config.model_dump() if config_data.llm_config else None,
        }
        
        # Create or update config
        await self.repo.create_prompt_config(prompt_id, config_dict)
        
        # Retrieve and return
        config_response = await self.repo.get_prompt_config(prompt_id)
        return PromptConfigResponse(**config_response)
    
    async def get_agent_config(self, agent_id: UUID) -> Optional[PromptConfigResponse]:
        """
        Get active configuration for an agent.
        
        Returns:
            Active configuration or None if no config exists
        """
        active_prompt = await self.repo.get_active_system_prompt(agent_id)
        if not active_prompt:
            return None
        
        config_data = await self.repo.get_prompt_config(active_prompt["id"])
        if config_data:
            return PromptConfigResponse(**config_data)
        return None
    
    async def get_config_by_type(
        self,
        agent_id: UUID,
        config_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific configuration type for an agent.
        
        Args:
            agent_id: Agent ID
            config_type: One of: chunking, embedding, retriever, llm
        
        Returns:
            Configuration dict or None
        """
        config = await self.get_agent_config(agent_id)
        if not config:
            return None
        
        config_field = f"{config_type}_config"
        return getattr(config, config_field, None)
    
    async def update_config_by_type(
        self,
        agent_id: UUID,
        config_type: str,
        config_data: Dict[str, Any],
    ) -> PromptConfigResponse:
        """
        Update specific configuration type for an agent.
        
        Args:
            agent_id: Agent ID
            config_type: One of: chunking, embedding, retriever, llm
            config_data: New configuration data
        
        Returns:
            Updated full configuration
        """
        # Get current config
        current_config = await self.get_agent_config(agent_id)
        
        # Build update dict
        update_data = {}
        if current_config:
            update_data = {
                "connection_id": current_config.connection_id,
                "schema_selection": current_config.schema_selection,
                "data_dictionary": current_config.data_dictionary,
                "reasoning": current_config.reasoning,
                "example_questions": current_config.example_questions,
                "data_source_type": current_config.data_source_type,
                "chunking_config": current_config.chunking_config,
                "embedding_config": current_config.embedding_config,
                "retriever_config": current_config.retriever_config,
                "llm_config": current_config.llm_config,
            }
        
        # Update specific config type
        config_field = f"{config_type}_config"
        update_data[config_field] = config_data
        
        # Create PromptConfigCreate and update
        prompt_config = PromptConfigCreate(**update_data)
        return await self.update_agent_config(agent_id, prompt_config)
