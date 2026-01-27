"""
Pydantic schemas for API request/response validation.
Defines the contract between frontend and backend.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Authentication Schemas
# ============================================

class LoginRequest(BaseModel):
    """Login request payload."""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=3, description="Password")


class RegisterRequest(BaseModel):
    """User registration request payload."""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=6, description="Password (minimum 6 characters)")
    email: Optional[str] = Field(None, description="Email address")
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    role: Optional[str] = Field(default="user", description="User role (super_admin, editor, user, viewer)")


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: "User" = Field(..., description="Authenticated user information")
    expires_in: int = Field(..., description="Token expiration in seconds")


class User(BaseModel):
    """User information."""
    username: str
    id: Optional[int] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    created_at: Optional[str] = None
    role: str = Field(default="viewer", description="User role: super_admin, editor, user, or viewer")


# ============================================
# Chat Schemas
# ============================================

class ChatRequest(BaseModel):
    """Chat request payload."""
    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    user_id: Optional[str] = Field(default=None, description="User identifier (from JWT)")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query": "How many active users are there?",
            "user_id": "admin"
        }
    })


class ChartData(BaseModel):
    """Chart visualization data."""
    title: str = Field(..., description="Chart title")
    type: str = Field(..., description="Chart type (pie, bar, line)")
    data: Dict[str, List[Any]] = Field(..., description="Chart data with labels and values")
    
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
    """Agent reasoning step."""
    tool: str = Field(..., description="Tool name used")
    input: str = Field(..., description="Tool input/query")
    output: str = Field(..., description="Tool output (truncated)")


class EmbeddingInfo(BaseModel):
    """Embedding analysis information."""
    model: str = Field(..., description="Embedding model name")
    dimensions: int = Field(..., description="Vector dimensions")
    search_method: str = Field(..., description="Search method used (hybrid/structured)")
    vector_norm: Optional[float] = Field(default=None, description="Vector L2 norm")
    docs_retrieved: Optional[int] = Field(default=None, description="Number of documents retrieved")


class ChatResponse(BaseModel):
    """Chat response payload."""
    answer: str = Field(..., description="Chatbot answer text")
    chart_data: Optional[ChartData] = Field(default=None, description="Optional chart visualization")
    suggested_questions: List[str] = Field(default_factory=list, description="Follow-up questions")
    reasoning_steps: List[ReasoningStep] = Field(default_factory=list, description="Agent reasoning process")
    embedding_info: Optional[EmbeddingInfo] = Field(default=None, description="Embedding analysis")
    trace_id: str = Field(..., description="Langfuse trace ID for debugging")
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
            "reasoning_steps": [
                {"tool": "sql_query_tool", "input": "SELECT COUNT(*) FROM users WHERE status='active'", "output": "245"}
            ],
            "embedding_info": {
                "model": "bge-m3",
                "dimensions": 1024,
                "search_method": "hybrid"
            },
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
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
