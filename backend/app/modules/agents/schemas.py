"""
Pydantic schemas for agents and configurations.

Schema structure:
- agents: Core agent entity
- agent_configs: Links agent ↔ data source with all configs

Note: Data source schemas are in app.modules.data_sources.schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# Import DataSourceResponse for use in AgentConfigResponse
from app.modules.data_sources.schemas import DataSourceResponse


# ==========================================
# Config Sub-Schemas (reusable)
# ==========================================

class LLMConfig(BaseModel):
    """LLM configuration options."""
    model: Optional[str] = Field(None, description="AI Registry model_id (provider/model) - optional when llmModelId is provided")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, alias="maxTokens")
    
    model_config = {"populate_by_name": True}


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""
    model: Optional[str] = Field(None, description="AI Registry model_id - optional when embeddingModelId is provided")
    vector_db_name: Optional[str] = Field(None, alias="vectorDbName", description="Vector DB collection name")
    dimensions: int = Field(default=1536, ge=1)
    batch_size: int = Field(default=100, ge=1, alias="batchSize")
    
    model_config = {"populate_by_name": True}


class ChunkingConfig(BaseModel):
    """Text chunking configuration."""
    parent_chunk_size: int = Field(default=512, ge=100, alias="parentChunkSize")
    parent_chunk_overlap: int = Field(default=100, ge=0, alias="parentChunkOverlap")
    child_chunk_size: int = Field(default=128, ge=50, alias="childChunkSize")
    child_chunk_overlap: int = Field(default=25, ge=0, alias="childChunkOverlap")
    
    model_config = {"populate_by_name": True}


class RAGConfig(BaseModel):
    """RAG retrieval configuration."""
    top_k_initial: int = Field(default=50, ge=1, le=200, alias="topKInitial")
    top_k_final: int = Field(default=10, ge=1, le=50, alias="topKFinal")
    hybrid_weights: List[float] = Field(default=[0.75, 0.25], alias="hybridWeights")
    reranking_enabled: bool = Field(default=False, alias="rerankEnabled")
    reranker_model: Optional[str] = Field(None, alias="rerankerModel", description="AI Registry model_id for reranker")
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0, alias="similarityThreshold")
    
    model_config = {"populate_by_name": True}
    
    @field_validator("hybrid_weights")
    @classmethod
    def validate_hybrid_weights(cls, v: List[float]) -> List[float]:
        if len(v) != 2:
            raise ValueError("hybrid_weights must have exactly 2 values")
        if abs(sum(v) - 1.0) > 0.01:
            raise ValueError("hybrid_weights must sum to 1.0")
        return v


# ==========================================
# Agent Schemas
# ==========================================

class AgentBase(BaseModel):
    """Base agent schema."""
    title: str = Field(..., min_length=1, max_length=255, description="Unique agent title")
    description: Optional[str] = Field(None, description="Agent description")


class AgentCreate(AgentBase):
    """Schema for creating a new agent."""
    pass


class AgentUpdate(BaseModel):
    """Schema for updating an agent (all fields optional)."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class AgentResponse(AgentBase):
    """Agent response schema."""
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class AgentWithRole(AgentResponse):
    """Agent response with user's role included."""
    user_role: str = Field(default="user", description="User's role for this agent")


class AgentDetailResponse(AgentResponse):
    """Detailed agent response with active config."""
    active_config: Optional["AgentConfigResponse"] = None


class AgentListResponse(BaseModel):
    """Paginated list of agents."""
    agents: List[AgentWithRole]
    total: int
    skip: int
    limit: int


# ==========================================
# Agent Config Schemas
# ==========================================

class AgentConfigBase(BaseModel):
    """Base agent configuration schema."""
    # Data selection
    selected_columns: Optional[List[str]] = Field(None, description="Columns to embed/query")
    data_dictionary: Optional[Dict[str, Any]] = Field(None, description="Column descriptions")
    
    # Model configs
    llm_config: Optional[LLMConfig] = None
    embedding_config: Optional[EmbeddingConfig] = None
    chunking_config: Optional[ChunkingConfig] = None
    rag_config: Optional[RAGConfig] = None
    
    # Prompt
    system_prompt: Optional[str] = None
    example_questions: Optional[List[str]] = None


class AgentConfigCreate(AgentConfigBase):
    """Create a new agent configuration."""
    agent_id: UUID
    data_source_id: UUID
    is_active: bool = Field(default=False, description="Whether this is the active config")
    status: str = Field(default="draft", description="draft or published")
    completed_step: int = Field(default=0, ge=0, le=6, description="Highest completed wizard step (0 = none)")


class AgentConfigUpdate(AgentConfigBase):
    """Update an agent configuration."""
    data_source_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    completed_step: Optional[int] = Field(None, ge=0, le=6)


# ==========================================
# Per-Step Request Schemas (named steps)
# ==========================================

class DataSourceStepRequest(BaseModel):
    """Step: data-source. Creates new version if version_id not provided."""
    data_source_id: UUID = Field(..., description="Data source to use")
    version_id: Optional[int] = Field(None, description="Existing version ID to update (optional, creates new if not provided)")


class SchemaSelectionStepRequest(BaseModel):
    """Step: schema-selection. Select tables and columns from data source."""
    # Unified format for both file and database: table -> columns mapping
    selected_schema: Dict[str, List[str]] = Field(..., description="Table to columns mapping")


class DataDictionaryStepRequest(BaseModel):
    """Step: data-dictionary. Add context/descriptions."""
    data_dictionary: Dict[str, Any] = Field(default_factory=dict, description="Column descriptions and context")


class SettingsStepRequest(BaseModel):
    """Step: settings. Configure embedding, chunking, RAG, LLM."""
    embedding_config: Optional[EmbeddingConfig] = Field(None, alias="embeddingConfig")
    chunking_config: Optional[ChunkingConfig] = Field(None, alias="chunkingConfig")
    rag_config: Optional[RAGConfig] = Field(None, alias="ragConfig")
    llm_config: Optional[LLMConfig] = Field(None, alias="llmConfig")
    
    # AI Registry model IDs (foreign keys to ai_models.id)
    llm_model_id: Optional[int] = Field(None, alias="llmModelId", description="LLM model ID from ai_models table")
    embedding_model_id: Optional[int] = Field(None, alias="embeddingModelId", description="Embedding model ID from ai_models table")
    reranker_model_id: Optional[int] = Field(None, alias="rerankerModelId", description="Reranker model ID from ai_models table")
    
    model_config = {"populate_by_name": True}


class PromptStepRequest(BaseModel):
    """Step: prompt. Configure system prompt and example questions."""
    system_prompt: str = Field(..., min_length=1, description="System prompt for the agent")
    example_questions: Optional[List[str]] = Field(default_factory=list, description="Example questions for users")


class PublishStepRequest(BaseModel):
    """Step: publish. Save final prompt and publish the configuration."""
    system_prompt: str = Field(..., min_length=1, description="Final system prompt for the agent")
    example_questions: Optional[List[str]] = Field(default_factory=list, description="Example questions for users")


class GeneratePromptResponse(BaseModel):
    """Response from generate-prompt endpoint."""
    draft_prompt: str = Field(..., description="Generated system prompt")
    reasoning: Dict[str, str] = Field(default_factory=dict, description="Reasoning for key schema elements")
    example_questions: List[str] = Field(default_factory=list, description="Example questions the agent can answer")


class ModelInfo(BaseModel):
    """Resolved model information from ai_models table."""
    id: int
    provider_name: str
    display_name: str  # display name
    model_id: str      # actual model ID (e.g., "openai/gpt-4o")
    model_type: str    # "llm", "embedding", "reranker"


class AgentConfigResponse(BaseModel):
    """Agent configuration response."""
    id: int
    agent_id: UUID
    data_source_id: UUID
    
    # Data source type (derived from data_source)
    data_source_type: Optional[str] = None  # 'database' or 'file'
    
    # Data selection (parsed from JSON)
    # For files: List[str] of column names
    # For databases: Dict[table_name, List[column_names]]
    selected_columns: Optional[Union[List[str], Dict[str, List[str]]]] = None
    data_dictionary: Optional[Dict[str, Any]] = None
    
    # Model configs (parsed from JSON)
    llm_config: Optional[Dict[str, Any]] = None
    embedding_config: Optional[Dict[str, Any]] = None
    chunking_config: Optional[Dict[str, Any]] = None
    rag_config: Optional[Dict[str, Any]] = None
    
    # AI Registry model IDs (foreign keys to ai_models.id)
    llm_model_id: Optional[int] = None
    embedding_model_id: Optional[int] = None
    reranker_model_id: Optional[int] = None
    
    # Resolved model info (populated when model IDs are set)
    llm_model: Optional[ModelInfo] = None
    embedding_model: Optional[ModelInfo] = None
    reranker_model: Optional[ModelInfo] = None
    
    # Prompt
    system_prompt: Optional[str] = None
    example_questions: Optional[List[str]] = None
    
    # Vector store
    embedding_path: Optional[str] = None
    vector_collection_name: Optional[str] = None
    embedding_status: str = "not_started"
    
    # Version & Status
    version: int
    is_active: bool
    status: str = "draft"
    completed_step: int = 0
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    
    # Related data source
    data_source: Optional[DataSourceResponse] = None
    
    model_config = {"from_attributes": True}


class AgentConfigSummary(BaseModel):
    """Summary of agent configuration for table view (limited fields)."""
    id: int
    agent_id: UUID
    version: int
    is_active: bool
    status: str
    embedding_status: str
    data_source_name: Optional[str] = None
    llm_model_name: Optional[str] = None
    embedding_model_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class AgentConfigHistoryResponse(BaseModel):
    """Paginated list of agent config summaries for history table."""
    configs: List[AgentConfigSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class AgentConfigListResponse(BaseModel):
    """List of agent configurations (history)."""
    configs: List[AgentConfigResponse]
    total: int


# ==========================================
# User-Agent RBAC Schemas
# ==========================================

class UserAgentGrantRequest(BaseModel):
    """Request to grant user access to an agent."""
    user_id: UUID
    role: str = Field(default="user", description="Role: user, editor, or admin")
    
    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"user", "editor", "admin"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(allowed)}")
        return v


class BulkAssignAgentsRequest(BaseModel):
    """Request to bulk assign agents to a user."""
    user_id: UUID
    agent_ids: List[UUID]
    role: str = Field(default="user", description="Role: user, editor, or admin")
    
    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"user", "editor", "admin"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {', '.join(allowed)}")
        return v


class BulkAssignAgentsResponse(BaseModel):
    """Response for bulk agent assignment."""
    status: str = "success"
    assigned: List[str] = Field(default_factory=list, description="Successfully assigned agent IDs")
    failed: List[str] = Field(default_factory=list, description="Failed agent IDs")
    message: str = ""


class UserAgentResponse(BaseModel):
    """User-agent relationship response with user details."""
    # User identification
    id: UUID  # user_id for frontend compatibility
    user_id: UUID
    agent_id: UUID
    
    # User details
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    
    # Agent access details
    role: Optional[str]=None  # Role on this specific agent (user, admin)
    granted_at: datetime
    granted_by: Optional[UUID] = None
    
    model_config = {"from_attributes": True}


class UserAgentListResponse(BaseModel):
    """List of users with access to an agent."""
    users: List[UserAgentResponse]
    total: int
    agent_id: Optional[UUID] = None


class AgentForUserResponse(BaseModel):
    """Agent info with user's access role - used when listing agents for a user."""
    # Agent details
    id: UUID
    title: str
    description: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    # User's access to this agent
    role: str = Field(description="User's role on this agent (user, editor, admin)")
    granted_at: datetime
    granted_by: Optional[UUID] = None
    
    model_config = {"from_attributes": True}


class AgentsForUserListResponse(BaseModel):
    """List of agents a user has access to."""
    agents: List[AgentForUserResponse]
    total: int
    user_id: UUID


# ==========================================
# Search Schema
# ==========================================

class AgentSearchParams(BaseModel):
    """Search parameters for agents."""
    query: Optional[str] = Field(None, description="Search in title/description")
    created_by: Optional[UUID] = Field(None, description="Filter by creator")
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


# ==========================================
# Embedding Status Schema
# ==========================================

class EmbeddingStatusUpdate(BaseModel):
    """Update embedding status for a config."""
    status: Literal["not_started", "in_progress", "completed", "failed"]
    embedding_path: Optional[str] = None
    vector_collection_name: Optional[str] = None


# Forward reference resolution
AgentDetailResponse.model_rebuild()
