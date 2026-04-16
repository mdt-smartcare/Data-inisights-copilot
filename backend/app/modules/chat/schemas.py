"""
Chat module Pydantic schemas.

Request/Response DTOs for the chat endpoint.
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ==========================================
# Sub-Schemas (embedded in response)
# ==========================================

class ChartData(BaseModel):
    """Chart visualization data.
    
    Supports multiple chart types:
    - List-based: pie, bar, line, horizontal_bar, treemap, funnel
    - Single-value: scorecard, gauge
    - Comparison: bullet
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
    """Agent reasoning step for transparency."""
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


class SourceChunk(BaseModel):
    """A retrieved source chunk."""
    content: str = Field(..., description="Chunk text content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")
    score: Optional[float] = Field(default=None, description="Similarity score")


# ==========================================
# Request/Response Schemas
# ==========================================

class ChatRequest(BaseModel):
    """Chat request payload."""
    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    agent_id: Optional[UUID] = Field(default=None, description="Target agent ID (UUID)")
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation tracking. Auto-generated if not provided."
    )
    stream: bool = Field(default=False, description="Enable streaming response")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query": "How many active users are there?",
            "agent_id": "123e4567-e89b-12d3-a456-426614174000",
            "session_id": "abc123-session-id",
            "stream": False
        }
    })


class ChatResponse(BaseModel):
    """Chat response payload."""
    answer: str = Field(..., description="Chatbot answer text")
    chart_data: Optional[ChartData] = Field(default=None, description="Optional chart visualization")
    suggested_questions: List[str] = Field(default_factory=list, description="Follow-up questions")
    reasoning_steps: List[ReasoningStep] = Field(default_factory=list, description="Agent reasoning process")
    sources: List[SourceChunk] = Field(default_factory=list, description="Retrieved source chunks")
    embedding_info: Optional[EmbeddingInfo] = Field(default=None, description="Embedding analysis")
    comparison_insights: Optional[str] = Field(default=None, description="Auto-generated comparison analysis for cross-validation")
    trace_id: str = Field(..., description="Trace ID for debugging")
    session_id: Optional[str] = Field(default=None, description="Session ID for conversation tracking")
    agent_id: Optional[str] = Field(default=None, description="Agent ID that generated this response")
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
            "sources": [],
            "embedding_info": {
                "model": "bge-base-en-v1.5",
                "dimensions": 768,
                "search_method": "hybrid"
            },
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
            "session_id": "abc123-session-id",
            "timestamp": "2025-12-30T10:30:00Z"
        }
    })


# ==========================================
# Health/Status Schemas
# ==========================================

class ChatServiceStatus(BaseModel):
    """Chat service health status."""
    healthy: bool = Field(..., description="Whether the chat service is healthy")
    llm_available: bool = Field(default=False, description="LLM provider available")
    vector_db_available: bool = Field(default=False, description="Vector database available")
    active_sessions: int = Field(default=0, description="Number of active sessions")
    message: str = Field(default="", description="Status message")


# ==========================================
# Feedback Schemas
# ==========================================

class FeedbackRequest(BaseModel):
    """Chat feedback submission request."""
    trace_id: str = Field(..., description="Trace ID of the chat response")
    query: str = Field(..., min_length=1, max_length=2000, description="Original user query")
    selected_suggestion: Optional[str] = Field(
        default=None,
        max_length=500,
        description="If user selected a suggested question"
    )
    rating: int = Field(
        ...,
        ge=-1,
        le=1,
        description="User rating: -1 (negative), 0 (neutral), 1 (positive)"
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional user comment"
    )
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "trace_id": "550e8400e29b41d4a716446655440000",
            "query": "How many active users?",
            "rating": 1,
            "comment": "Helpful answer"
        }
    })


class FeedbackResponse(BaseModel):
    """Chat feedback submission response."""
    status: str = Field(default="success", description="Submission status")
    message: str = Field(..., description="Response message")
    feedback_id: Optional[str] = Field(default=None, description="Unique feedback ID")
