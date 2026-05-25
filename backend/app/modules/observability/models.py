"""
Observability Models for tracing and monitoring.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class TraceStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


class SpanKind(str, Enum):
    INTERNAL = "internal"
    LLM = "llm"
    CHAIN = "chain"
    TOOL = "tool"
    RETRIEVER = "retriever"
    EMBEDDING = "embedding"


# ============================================
# Pydantic Schemas
# ============================================

class TraceBase(BaseModel):
    name: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TraceCreate(TraceBase):
    pass


class TraceResponse(TraceBase):
    id: str
    status: TraceStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    total_tokens: Optional[int] = None
    total_cost: Optional[float] = None

    class Config:
        from_attributes = True


class SpanBase(BaseModel):
    name: str
    trace_id: str
    parent_span_id: Optional[str] = None
    kind: SpanKind = SpanKind.INTERNAL
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class SpanCreate(SpanBase):
    pass


class SpanResponse(SpanBase):
    id: str
    status: TraceStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    tokens_used: Optional[int] = None
    cost: Optional[float] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class MetricRecord(BaseModel):
    """Model for custom metrics."""
    name: str
    value: float
    tags: Optional[Dict[str, str]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class LLMUsageMetrics(BaseModel):
    """Model for LLM usage tracking."""
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0