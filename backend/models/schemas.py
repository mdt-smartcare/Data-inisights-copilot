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
    role: Optional[str] = Field(default="user", description="User role (admin or user)")


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
    role: str = Field(default="viewer", description="User role: admin, editor, or viewer")


# ============================================
# Chat Schemas
# ============================================

class ChatRequest(BaseModel):
    """Chat request payload."""
    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    user_id: Optional[str] = Field(default=None, description="User identifier (from JWT)")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query": "How many patients have hypertension?",
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
            "title": "Hypertension Distribution",
            "type": "pie",
            "data": {
                "labels": ["Stage 1", "Stage 2"],
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
            "answer": "There are 245 patients with diagnosed hypertension in the database.",
            "chart_data": {
                "title": "HTN Distribution",
                "type": "pie",
                "data": {"labels": ["Stage 1", "Stage 2"], "values": [120, 125]}
            },
            "suggested_questions": [
                "What is the average age of hypertensive patients?",
                "Show glucose levels for diabetic patients"
            ],
            "reasoning_steps": [
                {"tool": "sql_query_tool", "input": "SELECT COUNT(*) FROM patients WHERE diagnosis='HTN'", "output": "245"}
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
            "query": "How many patients have hypertension?",
            "selected_suggestion": "What is the average age of hypertensive patients?",
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
