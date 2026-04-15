"""
Pydantic schemas for AI Models - Simplified Design.
"""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


# Type aliases
ModelType = Literal['llm', 'embedding', 'reranker']
DeploymentType = Literal['cloud', 'local']
DownloadStatus = Literal['not_downloaded', 'pending', 'downloading', 'ready', 'error']


# ============================================
# Model Schemas
# ============================================

class AIModelBase(BaseModel):
    """Base fields for AI model."""
    display_name: str = Field(..., min_length=1, max_length=200)
    model_type: ModelType
    provider_name: str = Field(..., min_length=1, max_length=100)
    deployment_type: DeploymentType
    
    # Cloud config
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None  # Plain text - will be encrypted
    api_key_env_var: Optional[str] = None
    
    # Local config
    local_path: Optional[str] = None
    hf_model_id: Optional[str] = None
    hf_revision: Optional[str] = None
    
    # Model specs
    context_length: Optional[int] = None
    max_input_tokens: Optional[int] = None
    dimensions: Optional[int] = None
    
    # RAG hints
    recommended_chunk_size: Optional[int] = None
    compatibility_notes: Optional[str] = None
    
    description: Optional[str] = None


class AIModelCreate(AIModelBase):
    """Create a new AI model."""
    model_id: str = Field(..., min_length=1, max_length=500, description="Unique ID: provider/model-name")
    is_default: bool = False
    
    @field_validator('model_id')
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        if '/' not in v:
            raise ValueError("model_id must be in format 'provider/model-name'")
        return v


class AIModelUpdate(BaseModel):
    """Update an existing AI model."""
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    
    # Cloud config
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None  # Set to update, None to keep existing
    api_key_env_var: Optional[str] = None
    
    # Local config
    local_path: Optional[str] = None
    
    # Model specs
    context_length: Optional[int] = None
    max_input_tokens: Optional[int] = None
    dimensions: Optional[int] = None
    
    # RAG hints
    recommended_chunk_size: Optional[int] = None
    compatibility_notes: Optional[str] = None
    
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class AIModelResponse(BaseModel):
    """AI model response."""
    id: int
    model_id: str
    display_name: str
    model_type: ModelType
    provider_name: str
    deployment_type: DeploymentType
    
    # Cloud info (API key hidden)
    api_base_url: Optional[str] = None
    has_api_key: bool = False
    api_key_env_var: Optional[str] = None
    
    # Local info
    local_path: Optional[str] = None
    download_status: DownloadStatus = 'not_downloaded'
    download_progress: int = 0
    download_error: Optional[str] = None
    hf_model_id: Optional[str] = None
    hf_revision: Optional[str] = None
    
    # Model specs
    context_length: Optional[int] = None
    max_input_tokens: Optional[int] = None
    dimensions: Optional[int] = None
    
    # RAG hints
    recommended_chunk_size: Optional[int] = None
    compatibility_notes: Optional[str] = None
    
    # Status
    is_active: bool
    is_default: bool
    is_ready: bool  # Computed: cloud=True, local=download_status=='ready'
    
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class AIModelListResponse(BaseModel):
    """List of AI models."""
    models: List[AIModelResponse]
    total: int


# ============================================
# HuggingFace Search Schemas
# ============================================

class HFSearchRequest(BaseModel):
    """Search HuggingFace Hub."""
    query: str = Field(..., min_length=1)
    model_type: Optional[ModelType] = None
    limit: int = Field(default=20, ge=1, le=100)


class HFModelInfo(BaseModel):
    """HuggingFace model info."""
    model_id: str
    author: str
    model_name: str
    pipeline_tag: Optional[str] = None
    downloads: int = 0
    likes: int = 0
    last_modified: Optional[str] = None
    description: Optional[str] = None
    
    # Inferred
    suggested_type: Optional[ModelType] = None
    is_registered: bool = False  # Already in our database


class HFSearchResponse(BaseModel):
    """HuggingFace search results."""
    models: List[HFModelInfo]
    total: int


class HFQuickAddRequest(BaseModel):
    """Quick-add model from HuggingFace."""
    hf_model_id: str = Field(..., min_length=1)
    model_type: ModelType
    display_name: Optional[str] = None
    auto_download: bool = False


# ============================================
# Download Schemas
# ============================================

class DownloadStartRequest(BaseModel):
    """Start model download."""
    pass  # No extra params needed


class DownloadProgressResponse(BaseModel):
    """Download progress."""
    model_id: int
    status: DownloadStatus
    progress: int  # 0-100
    error: Optional[str] = None
    queue_position: Optional[int] = None  # Position in queue (1-based) if pending


# ============================================
# Default Model Schemas
# ============================================

class SetDefaultRequest(BaseModel):
    """Set default model for a type."""
    model_id: int


class DefaultsResponse(BaseModel):
    """Current default models."""
    llm: Optional[AIModelResponse] = None
    embedding: Optional[AIModelResponse] = None
    reranker: Optional[AIModelResponse] = None


# ============================================
# Available Models (for agent config)
# ============================================

class AvailableModel(BaseModel):
    """Model available for selection in agent config."""
    id: int
    model_id: str
    display_name: str
    model_type: ModelType
    provider_name: str
    deployment_type: DeploymentType
    is_ready: bool
    is_default: bool
    
    # Specs for UI display
    context_length: Optional[int] = None
    dimensions: Optional[int] = None


class AvailableModelsResponse(BaseModel):
    """Available models grouped by type."""
    llm: List[AvailableModel]
    embedding: List[AvailableModel]
    reranker: List[AvailableModel]
