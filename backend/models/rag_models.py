"""
Pydantic models for RAG configuration, embedding jobs, and notifications.
Provides type-safe API request/response validation.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Enums for Status Fields
# ============================================

class RAGConfigStatus(str, Enum):
    """Status states for RAG configurations."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    ROLLBACK = "rollback"


class EmbeddingVersionStatus(str, Enum):
    """Status states for embedding versions."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class EmbeddingJobStatus(str, Enum):
    """Status states for embedding jobs (state machine)."""
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    EMBEDDING = "EMBEDDING"
    VALIDATING = "VALIDATING"
    STORING = "STORING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NotificationPriority(str, Enum):
    """Priority levels for notifications."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationStatus(str, Enum):
    """Status states for notifications."""
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"


class NotificationType(str, Enum):
    """Types of notifications."""
    EMBEDDING_STARTED = "embedding_started"
    EMBEDDING_PROGRESS = "embedding_progress"
    EMBEDDING_COMPLETE = "embedding_complete"
    EMBEDDING_FAILED = "embedding_failed"
    EMBEDDING_CANCELLED = "embedding_cancelled"
    CONFIG_PUBLISHED = "config_published"
    CONFIG_ROLLED_BACK = "config_rolled_back"
    SCHEMA_CHANGE_DETECTED = "schema_change_detected"


class WebhookFormat(str, Enum):
    """Supported webhook payload formats."""
    SLACK = "slack"
    TEAMS = "teams"
    GENERIC = "generic"


# ============================================
# RAG Configuration Models
# ============================================

class RAGConfigurationBase(BaseModel):
    """Base fields for RAG configuration."""
    schema_snapshot: Dict[str, Any] = Field(..., description="Complete database schema snapshot")
    data_dictionary: Optional[str] = Field(None, description="Data dictionary content")
    prompt_template: str = Field(..., description="Generated system prompt")
    change_summary: Optional[str] = Field(None, description="Description of changes")


class RAGConfigurationCreate(RAGConfigurationBase):
    """Request model for creating a new RAG configuration."""
    pass


class RAGConfiguration(RAGConfigurationBase):
    """Complete RAG configuration response model."""
    id: int
    version: str
    version_number: int
    status: RAGConfigStatus
    config_hash: str
    created_by: int
    created_at: datetime
    published_at: Optional[datetime] = None
    published_by: Optional[int] = None
    parent_version_id: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


# ============================================
# Embedding Version Models
# ============================================

class EmbeddingVersionBase(BaseModel):
    """Base fields for embedding version."""
    embedding_model: str = Field(default="BAAI/bge-m3", description="Embedding model name")
    embedding_dimension: int = Field(default=1024, description="Vector dimension")


class EmbeddingVersionCreate(EmbeddingVersionBase):
    """Request model for creating a new embedding version."""
    config_id: int


class EmbeddingVersion(EmbeddingVersionBase):
    """Complete embedding version response model."""
    id: int
    config_id: int
    version_hash: str
    total_documents: int
    table_documents: int
    column_documents: int
    relationship_documents: int
    status: EmbeddingVersionStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    generation_time_seconds: Optional[float] = None
    validation_passed: bool = False
    validation_details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    created_by: int
    
    model_config = ConfigDict(from_attributes=True)


# ============================================
# Embedding Job Models
# ============================================

class ChunkingConfig(BaseModel):
    """Configuration for parent-child chunking strategy."""
    parent_chunk_size: int = Field(default=800, ge=200, le=2000, description="Parent chunk size in tokens")
    parent_chunk_overlap: int = Field(default=150, ge=0, le=500, description="Parent chunk overlap in tokens")
    child_chunk_size: int = Field(default=200, ge=50, le=500, description="Child chunk size in tokens")
    child_chunk_overlap: int = Field(default=50, ge=0, le=100, description="Child chunk overlap in tokens")


class ParallelizationConfig(BaseModel):
    """Configuration for parallel processing."""
    num_workers: Optional[int] = Field(default=None, ge=1, le=16, description="Number of worker processes. None = auto")
    chunking_batch_size: Optional[int] = Field(default=None, ge=100, le=50000, description="Documents per chunking batch. None = auto")
    delta_check_batch_size: int = Field(default=50000, ge=1000, le=100000, description="Documents per delta check batch")


class MedicalContextConfig(BaseModel):
    """
    Configuration for medical terminology enrichment.
    
    Improves embedding quality by expanding clinical abbreviations
    and recognizing boolean flag patterns in column names.
    """
    # Medical abbreviation mappings (column_name -> human_readable_name)
    # Example: {"bp": "Blood Pressure", "hr": "Heart Rate", "hba1c": "Glycated Hemoglobin"}
    medical_context: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of column names to human-readable medical terms"
    )
    
    # Clinical boolean flag prefixes to recognize
    # Example: ["is_", "has_", "was_", "history_of_", "confirmed_"]
    clinical_flag_prefixes: List[str] = Field(
        default_factory=lambda: ["is_", "has_", "was_", "history_of_", "flag_", "confirmed_", "requires_", "on_"],
        description="Column prefixes indicating clinical boolean flags"
    )
    
    # Whether to use defaults from YAML config as base (merge with user config)
    use_yaml_defaults: bool = Field(
        default=True,
        description="Merge with default mappings from embedding_config.yaml"
    )


class EmbeddingJobCreate(BaseModel):
    """Request model for starting a new embedding job."""
    config_id: int = Field(..., description="RAG configuration to generate embeddings for")
    
    # Batch Processing Config
    batch_size: int = Field(default=50, ge=10, le=500, description="Documents per embedding batch")
    max_concurrent: int = Field(default=5, ge=1, le=20, description="Max concurrent embedding batches")
    incremental: bool = Field(default=True, description="Whether to run incrementally")
    
    # Chunking Config (optional - uses defaults if not provided)
    chunking: Optional[ChunkingConfig] = Field(default=None, description="Chunking configuration")
    
    # Parallelization Config (optional - uses adaptive defaults if not provided)
    parallelization: Optional[ParallelizationConfig] = Field(default=None, description="Parallelization configuration")
    
    # Medical Context Config (optional - improves semantic search for clinical data)
    medical_context_config: Optional[MedicalContextConfig] = Field(
        default=None, 
        description="Medical terminology enrichment configuration"
    )
    
    # Circuit Breaker Config
    max_consecutive_failures: int = Field(default=5, ge=1, le=20, description="Max consecutive ChromaDB failures before abort")
    retry_attempts: int = Field(default=3, ge=1, le=10, description="Retry attempts per batch")


class EmbeddingJobProgress(BaseModel):
    """Real-time progress information for an embedding job."""
    job_id: str = Field(..., description="Unique job identifier")
    status: EmbeddingJobStatus = Field(..., description="Current job status")
    phase: Optional[str] = Field(None, description="Current phase description")
    
    # Document Progress
    total_documents: int = Field(..., description="Total documents to process")
    processed_documents: int = Field(default=0, description="Documents processed so far")
    failed_documents: int = Field(default=0, description="Documents that failed processing")
    progress_percentage: float = Field(default=0.0, ge=0, le=100, description="Progress percentage")
    
    # Batch Progress
    current_batch: int = Field(default=0, description="Current batch being processed")
    total_batches: int = Field(..., description="Total number of batches")
    
    # Performance Metrics
    documents_per_second: Optional[float] = Field(None, description="Processing speed")
    estimated_time_remaining_seconds: Optional[int] = Field(None, description="ETA in seconds")
    elapsed_seconds: Optional[int] = Field(None, description="Time elapsed since start")
    
    # Errors
    errors_count: int = Field(default=0, description="Number of errors encountered")
    recent_errors: List[str] = Field(default_factory=list, description="Recent error messages")
    
    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "job_id": "emb-job-abc123",
                "status": "EMBEDDING",
                "phase": "Processing batch 19/25",
                "total_documents": 1247,
                "processed_documents": 935,
                "progress_percentage": 75.0,
                "current_batch": 19,
                "total_batches": 25,
                "documents_per_second": 7.8,
                "estimated_time_remaining_seconds": 120,
                "errors_count": 0
            }
        }
    )


class EmbeddingJobSummary(BaseModel):
    """Summary of a completed embedding job."""
    job_id: str
    status: EmbeddingJobStatus
    total_documents: int
    processed_documents: int
    failed_documents: int
    duration_seconds: Optional[float] = None
    average_speed: Optional[float] = None
    validation_passed: bool = False
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ============================================
# Notification Models
# ============================================

class NotificationBase(BaseModel):
    """Base fields for notifications."""
    type: NotificationType = Field(..., description="Notification type")
    priority: NotificationPriority = Field(default=NotificationPriority.MEDIUM)
    title: str = Field(..., max_length=255, description="Notification title")
    message: Optional[str] = Field(None, description="Notification message body")
    action_url: Optional[str] = Field(None, description="URL for action button")
    action_label: Optional[str] = Field(None, description="Action button label")


class NotificationCreate(NotificationBase):
    """Request model for creating a notification."""
    user_id: int = Field(..., description="Target user ID")
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    channels: List[str] = Field(default=["in_app"], description="Delivery channels")


class Notification(NotificationBase):
    """Complete notification response model."""
    id: int
    user_id: int
    status: NotificationStatus
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    channels: List[str]
    read_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class NotificationPreferences(BaseModel):
    """User notification preferences."""
    in_app_enabled: bool = Field(default=True, description="Enable in-app notifications")
    email_enabled: bool = Field(default=True, description="Enable email notifications")
    webhook_enabled: bool = Field(default=False, description="Enable webhook notifications")
    webhook_url: Optional[str] = Field(None, description="Custom webhook URL")
    webhook_format: WebhookFormat = Field(default=WebhookFormat.SLACK)
    notification_types: Dict[str, bool] = Field(
        default_factory=dict,
        description="Per-type enable/disable settings"
    )
    quiet_hours_enabled: bool = Field(default=False)
    quiet_hours_start: Optional[str] = Field(None, description="Start time (HH:MM)")
    quiet_hours_end: Optional[str] = Field(None, description="End time (HH:MM)")
    quiet_hours_timezone: str = Field(default="UTC")
    
    model_config = ConfigDict(from_attributes=True)


class NotificationPreferencesUpdate(BaseModel):
    """Request model for updating notification preferences."""
    in_app_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    webhook_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    webhook_format: Optional[WebhookFormat] = None
    notification_types: Optional[Dict[str, bool]] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    quiet_hours_timezone: Optional[str] = None


# ============================================
# WebSocket Message Models
# ============================================

class WebSocketMessage(BaseModel):
    """Base model for WebSocket messages."""
    event: str = Field(..., description="Event type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EmbeddingProgressMessage(WebSocketMessage):
    """WebSocket message for embedding progress updates."""
    event: str = "embedding_progress"
    job_id: str
    status: EmbeddingJobStatus
    phase: Optional[str] = None
    progress: Dict[str, Any] = Field(
        default_factory=lambda: {
            "total_documents": 0,
            "processed_documents": 0,
            "percentage": 0,
            "current_batch": 0,
            "total_batches": 0
        }
    )
    performance: Dict[str, Any] = Field(
        default_factory=lambda: {
            "documents_per_second": None,
            "estimated_time_remaining_seconds": None,
            "elapsed_seconds": None
        }
    )
    errors: Dict[str, Any] = Field(
        default_factory=lambda: {
            "count": 0,
            "recent": []
        }
    )


class NotificationMessage(WebSocketMessage):
    """WebSocket message for new notifications."""
    event: str = "notification"
    notification: Notification


# ============================================
# RAG Audit Log Models
# ============================================

class RAGAuditAction(str, Enum):
    """Types of RAG-related auditable actions."""
    WIZARD_ACCESSED = "wizard_accessed"
    SCHEMA_SELECTED = "schema_selected"
    DICTIONARY_UPLOADED = "dictionary_uploaded"
    EMBEDDING_STARTED = "embedding_started"
    EMBEDDING_COMPLETED = "embedding_completed"
    EMBEDDING_FAILED = "embedding_failed"
    EMBEDDING_CANCELLED = "embedding_cancelled"
    CONFIG_PUBLISHED = "config_published"
    CONFIG_ROLLED_BACK = "config_rolled_back"
    UNAUTHORIZED_ACCESS = "unauthorized_access"


class RAGAuditLogEntry(BaseModel):
    """RAG audit log entry."""
    id: int
    config_id: Optional[int] = None
    action: RAGAuditAction
    performed_by: int
    performed_by_email: str
    performed_by_role: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    performed_at: datetime
    changes: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
