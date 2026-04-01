"""
Pydantic schemas for API request/response validation.
Defines the contract between frontend and backend.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Authentication Schemas (OIDC/Keycloak)
# ============================================

class User(BaseModel):
    """User information."""
    username: str
    id: Optional[str] = None  # UUID serialized as string
    email: Optional[str] = None
    full_name: Optional[str] = None
    created_at: Optional[str] = None
    role: str = Field(default="user", description="User role: admin, user")
    external_id: Optional[str] = Field(None, description="OIDC subject (sub) claim from IdP")
    is_active: Optional[bool] = Field(default=True, description="Whether the user account is active")


# ============================================
# Chat Schemas
# ============================================

class ChatRequest(BaseModel):
    """Chat request payload."""
    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    user_id: Optional[str] = Field(default=None, description="User identifier (from JWT)")
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation tracking. Auto-generated if not provided."
    )
    agent_id: Optional[str] = Field(default=None, description="Target agent ID (UUID)")
    query_mode: str = Field(default="auto", description="Query mode (auto, sql, rag, hybrid)")
    debug: bool = Field(default=False, description="Enable QA debug information in response")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query": "How many active users are there?",
            "user_id": "admin",
            "session_id": "abc123-session-id"
        }
    })


class ChartData(BaseModel):
    """Chart visualization data.
    
    Supports multiple chart types:
    - List-based: pie, bar, line, horizontal_bar, treemap, funnel (data contains lists of labels/values)
    - Single-value: scorecard, gauge (uses value field or data)
    - Comparison: bullet (data contains actual/target pairs)
    """
    title: Optional[str] = Field(default=None, description="Chart title")
    type: str = Field(..., description="Chart type (pie, bar, line, scorecard, gauge, funnel, bullet, horizontal_bar, treemap)")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Chart data - format depends on chart type")
    
    # Gauge-specific fields
    value: Optional[float] = Field(default=None, description="Value for gauge charts")
    min: Optional[float] = Field(default=None, description="Minimum value for gauge")
    max: Optional[float] = Field(default=None, description="Maximum value for gauge")
    target: Optional[float] = Field(default=None, description="Target value for gauge/bullet")
    thresholds: Optional[List[Dict[str, Any]]] = Field(default=None, description="Threshold definitions for gauge")
    
    # Bullet-specific fields
    ranges: Optional[List[float]] = Field(default=None, description="Range boundaries for bullet chart")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "title": "User Distribution",
            "type": "pie",
            "data": {
                "labels": ["Active", "Inactive"],
                "values": [120, 125]
            }
        }
    })


class ReasoningStep(BaseModel):
    tool: str
    thought: Optional[str] = None
    input: str
    output: Optional[str] = None


class EmbeddingInfo(BaseModel):
    """Embedding analysis information."""
    model: str = Field(..., description="Embedding model name")
    dimensions: int = Field(..., description="Vector dimensions")
    search_method: str = Field(..., description="Search method used (hybrid/structured)")
    vector_norm: Optional[float] = Field(default=None, description="Vector L2 norm")
    docs_retrieved: Optional[int] = Field(default=None, description="Number of documents retrieved")


class QADebugInfo(BaseModel):
    """Unified QA debug information."""
    sql_query: Optional[str] = Field(default=None, description="Raw SQL query executed")
    reasoning_steps: List[ReasoningStep] = Field(default_factory=list, description="Agent thought process")
    trace_id: str = Field(..., description="Langfuse trace ID")
    trace_url: Optional[str] = Field(default=None, description="Direct link to Langfuse dashboard")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
    agent_config: Optional[Dict[str, Any]] = Field(default=None, description="Model and RAG parameters used")


class ChatResponse(BaseModel):

    """Chat response payload."""
    answer: str = Field(..., description="Chatbot answer text")
    chart_data: Optional[ChartData] = Field(default=None, description="Optional chart visualization")
    suggested_questions: List[str] = Field(default_factory=list, description="Follow-up questions")
    qa_debug: Optional[QADebugInfo] = Field(default=None, description="Optional QA debug information")
    embedding_info: Optional[EmbeddingInfo] = Field(default=None, description="Embedding analysis")
    trace_id: str = Field(..., description="Langfuse trace ID for debugging/feedback")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation tracking")
    agent_id: Optional[str] = Field(default=None, description="Agent ID (UUID) that generated this response")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "answer": "There are 245 active users in the database.",
            "chart_data": {
                "title": "User Status",
                "type": "pie",
                "data": {"labels": ["Active", "Inactive"], "values": [120, 125]}
            },
            "suggested_questions": [
                "What is the average age of users?",
                "Show active users by region"
            ],
            "qa_debug": {
                "sql_query": "SELECT COUNT(*) FROM users WHERE status='active'",
                "reasoning_steps": [
                    {"tool": "sql_query_tool", "input": "...", "output": "245"}
                ],
                "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                "trace_url": "https://langfuse.com/...",
                "processing_time_ms": 1250.5
            },
            "embedding_info": {
                "model": "bge-m3",
                "dimensions": 1024,
                "search_method": "hybrid"
            },
            "session_id": "abc123-session-id",
            "timestamp": "2025-12-30T10:30:00Z"
        }
    })


# ============================================
# Metric & Configuration Schemas
# ============================================

class MetricDefinition(BaseModel):
    """Configuration for dynamic SQL metrics."""
    id: Optional[int] = None
    name: str = Field(..., description="Unique metric name")
    description: Optional[str] = None
    regex_pattern: str = Field(..., description="Regex pattern to match user questions")
    sql_template: str = Field(..., description="SQL query template")
    priority: int = Field(default=0, description="Match priority (lower is checked first)")
    is_active: bool = Field(default=True)
    created_at: Optional[datetime] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "name": "metric_name",
            "regex_pattern": ".*metric.*",
            "sql_template": "SELECT count(*) FROM ...",
            "priority": 1
        }
    })

class SQLExample(BaseModel):
    """Few-shot SQL example for context injection."""
    id: Optional[int] = None
    question: str = Field(..., description="Natural language question")
    sql_query: str = Field(..., description="Corresponding SQL query")
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "question": "How many users are active?",
            "sql_query": "SELECT count(*) FROM users WHERE status = 'active'",
            "description": "Simple count of users"
        }
    })

class CritiqueResponse(BaseModel):
    """Output from the SQL critique agent."""
    is_valid: bool = Field(..., description="Whether the SQL is valid and safe")
    issues: List[str] = Field(default_factory=list, description="List of identified issues")
    corrected_sql: Optional[str] = Field(default=None, description="Suggested fix if applicable")
    reasoning: str = Field(..., description="Explanation of the critique")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "is_valid": False,
            "issues": ["Column 'p_id' does not exist in table 'patients'"],
            "corrected_sql": "SELECT count(*) FROM patient_tracker",
            "reasoning": "Schema mismatch identified."
        }
    })


# ============================================
# Feedback Schemas
# ============================================

class FeedbackRequest(BaseModel):
    """Feedback submission payload."""
    trace_id: str = Field(..., description="Trace ID from chat response")
    query: str = Field(..., description="Original user query")
    selected_suggestion: Optional[str] = Field(default=None, description="Selected suggestion text")
    rating: int = Field(..., ge=-1, le=1, description="Rating: 1 (good), -1 (bad)")
    comment: Optional[str] = Field(default=None, max_length=500, description="Optional user comment")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "query": "How many users are active?",
            "selected_suggestion": "What is the average age of users?",
            "rating": 1,
            "comment": "Very helpful suggestion"
        }
    })


class FeedbackResponse(BaseModel):
    """Feedback submission response."""
    status: str = Field(..., description="Status message")
    message: str = Field(..., description="Human-readable message")
    feedback_id: Optional[str] = Field(default=None, description="Feedback record ID")


# ============================================
# Health Check Schemas
# ============================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: Dict[str, str] = Field(default_factory=dict, description="Dependent service statuses")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": "2025-12-30T10:30:00Z",
            "services": {
                "database": "connected",
                "vector_store": "loaded",
                "llm": "ready"
            }
        }
    })


# ============================================
# Error Schemas
# ============================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    detail: Optional[Dict[str, Any]] = Field(default=None, description="Additional error details")
    trace_id: Optional[str] = Field(default=None, description="Request trace ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "error": "ValidationError",
            "message": "Invalid query format",
            "detail": {"field": "query", "issue": "Cannot be empty"},
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2025-12-30T10:30:00Z"
        }
    })


# ============================================
# Ingestion Schemas (Phase 3: Payload Injection)
# ============================================

class IngestionOverrideConfig(BaseModel):
    """
    Override configuration for ad-hoc ingestion jobs.
    
    Allows users to run ingestion with custom settings that differ
    from the global system defaults stored in the database.
    """
    # Chunking overrides
    parent_chunk_size: Optional[int] = Field(
        None, ge=100, le=4000,
        description="Override parent chunk size (default from DB: 800)"
    )
    parent_chunk_overlap: Optional[int] = Field(
        None, ge=0, le=500,
        description="Override parent chunk overlap (default from DB: 150)"
    )
    child_chunk_size: Optional[int] = Field(
        None, ge=50, le=1000,
        description="Override child chunk size (default from DB: 200)"
    )
    child_chunk_overlap: Optional[int] = Field(
        None, ge=0, le=200,
        description="Override child chunk overlap (default from DB: 50)"
    )
    min_chunk_length: Optional[int] = Field(
        None, ge=10, le=500,
        description="Override minimum chunk length (default from DB: 50)"
    )
    
    # PII overrides
    exclude_columns: Optional[List[str]] = Field(
        None,
        description="Override columns to exclude from embedding (PII protection)"
    )
    exclude_tables: Optional[List[str]] = Field(
        None,
        description="Override tables to exclude entirely from embedding"
    )
    
    # Embedding overrides
    batch_size: Optional[int] = Field(
        None, ge=1, le=1024,
        description="Override embedding batch size"
    )
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "parent_chunk_size": 1000,
            "parent_chunk_overlap": 200,
            "exclude_columns": ["ssn", "credit_card"],
            "batch_size": 64
        }
    })


class IngestionRequest(BaseModel):
    """
    Request payload for triggering an ingestion/embedding job.
    
    Supports ad-hoc configuration overrides that take precedence
    over the global database defaults for this specific job.
    """
    source_id: str = Field(
        ...,
        description="Identifier for the data source (connection ID, file name, or agent ID)"
    )
    source_type: str = Field(
        default="database",
        description="Type of data source: 'database', 'file', or 'agent'"
    )
    agent_id: Optional[str] = Field(
        None,
        description="Target agent ID (UUID) for the embedding job"
    )
    vector_db_name: Optional[str] = Field(
        None,
        description="Target vector database/collection name"
    )
    override_config: Optional[IngestionOverrideConfig] = Field(
        None,
        description="Optional overrides for chunking, PII rules, and embedding settings. "
                    "If provided, these values take precedence over database defaults."
    )
    force_reindex: bool = Field(
        default=False,
        description="Force re-indexing even if documents already exist"
    )
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "source_id": "conn-123",
            "source_type": "database",
            "agent_id": 1,
            "vector_db_name": "clinical_data_v2",
            "override_config": {
                "parent_chunk_size": 1000,
                "batch_size": 64
            },
            "force_reindex": False
        }
    })


class IngestionJobResponse(BaseModel):
    """Response after triggering an ingestion job."""
    job_id: str = Field(..., description="Unique job identifier for tracking")
    status: str = Field(..., description="Initial job status")
    message: str = Field(..., description="Human-readable status message")
    source_id: str = Field(..., description="Data source being processed")
    config_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="Final configuration applied (merged defaults + overrides)"
    )
    estimated_documents: Optional[int] = Field(
        None,
        description="Estimated number of documents to process"
    )
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "job_id": "emb-job-abc123def456",
            "status": "queued",
            "message": "Ingestion job queued successfully",
            "source_id": "conn-123",
            "config_applied": {
                "parent_chunk_size": 1000,
                "parent_chunk_overlap": 150,
                "batch_size": 64
            },
            "estimated_documents": 5000
        }
    })
