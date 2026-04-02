"""
Pydantic schemas for agent requests and responses.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ==========================================
# Agent Schemas
# ==========================================

class AgentBase(BaseModel):
    """Base agent schema with common fields."""
    name: str = Field(..., min_length=1, max_length=255, description="Unique agent name")
    description: Optional[str] = Field(None, description="Agent description")
    type: str = Field(default="sql", description="Agent type: sql, rag, or hybrid")
    db_connection_uri: Optional[str] = Field(None, description="Database connection URI")
    system_prompt: Optional[str] = Field(None, description="Default system prompt")
    embedding_model: Optional[str] = Field(default="bge-m3", description="Embedding model name")
    embedding_dimension: Optional[int] = Field(default=1024, description="Embedding dimensions")
    embedding_provider: Optional[str] = Field(default="sentence-transformers", description="Embedding provider")
    
    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate agent type."""
        allowed_types = {"sql", "rag", "hybrid"}
        if v not in allowed_types:
            raise ValueError(f"Agent type must be one of: {', '.join(allowed_types)}")
        return v


class AgentCreate(AgentBase):
    """Schema for creating a new agent."""
    pass


class AgentUpdate(BaseModel):
    """Schema for updating an agent (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = None
    db_connection_uri: Optional[str] = None
    system_prompt: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    embedding_provider: Optional[str] = None
    
    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate agent type if provided."""
        if v is not None:
            allowed_types = {"sql", "rag", "hybrid"}
            if v not in allowed_types:
                raise ValueError(f"Agent type must be one of: {', '.join(allowed_types)}")
        return v


class Agent(AgentBase):
    """Schema for agent response."""
    id: UUID
    created_by: Optional[UUID] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}


class AgentWithConfig(Agent):
    """Agent response with full configuration."""
    active_system_prompt: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


# ==========================================
# User-Agent Relationship Schemas
# ==========================================

class UserAgentAccess(BaseModel):
    """Schema for granting user access to agent."""
    user_id: UUID
    agent_id: UUID
    role: str = Field(default="user", description="Role: user, editor, or admin")
    
    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate agent-specific role."""
        allowed_roles = {"user", "editor", "admin"}
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of: {', '.join(allowed_roles)}")
        return v


class UserAgentResponse(BaseModel):
    """Response for user-agent relationship."""
    user_id: UUID
    role: str
    granted_at: datetime
    granted_by: Optional[UUID] = None


# ==========================================
# System Prompt Schemas
# ==========================================

class SystemPromptCreate(BaseModel):
    """Schema for creating a system prompt."""
    prompt_text: str = Field(..., min_length=1, description="System prompt text")
    version: int = Field(..., ge=1, description="Prompt version number")
    is_active: bool = Field(default=False, description="Whether prompt is active")


class SystemPromptResponse(BaseModel):
    """Response for system prompt."""
    id: int
    prompt_text: str
    version: int
    created_at: datetime
    created_by: Optional[str] = None


# ==========================================
# Prompt Config Schemas
# ==========================================

class ChunkingConfig(BaseModel):
    """Chunking configuration."""
    parent_chunk_size: int = Field(default=2000, ge=100)
    child_chunk_size: int = Field(default=400, ge=50)
    overlap: int = Field(default=200, ge=0)
    min_chunk_length: int = Field(default=50, ge=1)
    separators: List[str] = Field(default_factory=lambda: ["\n\n", "\n", ". ", " ", ""])


class PIIConfig(BaseModel):
    """PII exclusion configuration."""
    exclude_patient_names: bool = True
    exclude_patient_ids: bool = False
    exclude_ssn: bool = True
    exclude_phone_numbers: bool = True
    exclude_emails: bool = False
    exclude_addresses: bool = True
    exclude_dob: bool = False
    exclude_medical_record_numbers: bool = False
    custom_patterns: List[str] = Field(default_factory=list)


class MedicalContextConfig(BaseModel):
    """Medical terminology configuration."""
    include_icd_codes: bool = True
    include_cpt_codes: bool = True
    include_medications: bool = True
    include_lab_results: bool = True
    include_vital_signs: bool = True
    include_diagnoses: bool = True
    include_procedures: bool = True
    terminology_systems: List[str] = Field(default_factory=lambda: ["ICD-10", "CPT", "SNOMED", "LOINC", "RxNorm"])


class RAGConfig(BaseModel):
    """RAG (Retrieval Augmented Generation) configuration."""
    top_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    reranking_enabled: bool = False
    reranking_top_k: int = Field(default=10, ge=1)
    max_context_length: int = Field(default=4000, ge=100)
    use_parent_chunks: bool = True
    use_child_chunks: bool = True
    hybrid_search: bool = False
    hybrid_alpha: float = Field(default=0.5, ge=0.0, le=1.0)


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""
    provider: str = Field(default="openai")
    model: str = Field(default="text-embedding-3-small")
    dimensions: int = Field(default=1536, ge=1)
    batch_size: int = Field(default=100, ge=1)
    max_input_tokens: int = Field(default=8191, ge=1)
    normalize: bool = True


class LLMConfig(BaseModel):
    """LLM configuration."""
    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    streaming: bool = True


class VectorStoreConfig(BaseModel):
    """Vector store configuration."""
    provider: str = Field(default="chroma")
    collection_prefix: str = Field(default="agent")
    distance_metric: str = Field(default="cosine")
    index_type: str = Field(default="hnsw")
    persist_directory: str = Field(default="./data/indexes")


class SystemPromptConfig(BaseModel):
    """System prompt templates configuration."""
    base_system_prompt: str = Field(
        default="""You are a helpful AI assistant specialized in analyzing healthcare data.

You have access to clinical information and should:
1. Provide accurate, evidence-based responses
2. Cite specific data sources when possible
3. Acknowledge uncertainty when information is incomplete
4. Never fabricate or guess clinical information
5. Respect patient privacy and confidentiality

Always ground your responses in the provided context."""
    )
    query_prefix: str = Field(
        default="""Using the following clinical context, answer the user's question accurately and concisely.

Context:
{context}

Question: {question}

Answer:"""
    )
    sql_system_prompt: str = Field(
        default="""You are an expert SQL query generator for healthcare databases.

Generate safe, read-only SQL queries based on user questions. Follow these rules:
1. Only generate SELECT queries (no INSERT, UPDATE, DELETE, DROP)
2. Use proper JOINs and WHERE clauses
3. Include LIMIT clauses to prevent large result sets
4. Use descriptive column aliases
5. Add comments explaining complex logic

Always validate queries before execution."""
    )


class PromptConfigCreate(BaseModel):
    """Schema for creating/updating prompt configuration."""
    connection_id: Optional[int] = None
    schema_selection: Optional[str] = None
    data_dictionary: Optional[str] = None
    reasoning: Optional[str] = None
    example_questions: Optional[str] = None
    data_source_type: str = Field(default="database")
    
    # Configuration objects
    chunking_config: Optional[ChunkingConfig] = None
    embedding_config: Optional[EmbeddingConfig] = None
    retriever_config: Optional[RAGConfig] = None  # Aliased as retriever_config in DB
    llm_config: Optional[LLMConfig] = None


class PromptConfigResponse(BaseModel):
    """Response for prompt configuration."""
    prompt_id: int
    connection_id: Optional[int] = None
    schema_selection: Optional[str] = None
    data_dictionary: Optional[str] = None
    reasoning: Optional[str] = None
    example_questions: Optional[str] = None
    data_source_type: str
    chunking_config: Optional[Dict[str, Any]] = None
    embedding_config: Optional[Dict[str, Any]] = None
    retriever_config: Optional[Dict[str, Any]] = None
    llm_config: Optional[Dict[str, Any]] = None


# ==========================================
# Agent Search & Query Schemas
# ==========================================

class AgentSearchParams(BaseModel):
    """Search parameters for agents."""
    query: Optional[str] = Field(None, description="Search in name/description")
    type: Optional[str] = Field(None, description="Filter by agent type")
    created_by: Optional[UUID] = Field(None, description="Filter by creator")
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


class AgentListResponse(BaseModel):
    """Response for agent list with pagination."""
    agents: List[Agent]
    total: int
    skip: int
    limit: int
