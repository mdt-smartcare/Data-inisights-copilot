"""
Common models and DTOs shared across all modules.

This module provides base response structures, pagination,
and error handling models used throughout the application.
"""
from typing import Any, Dict, Generic, List, Optional, TypeVar
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# Generic type for paginated responses
T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """
    Standard API response wrapper.
    
    Provides consistent response structure across all endpoints.
    Can be parametrized: BaseResponse[User], BaseResponse[dict], etc.
    """
    success: bool = Field(default=True, description="Whether the request was successful")
    message: str = Field(default="", description="Optional message")
    data: Optional[T] = Field(default=None, description="Response payload")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "",
                "data": {"id": "123", "name": "Example"}
            }
        }
    )
    
    @classmethod
    def ok(cls, data: T = None, message: str = "") -> "BaseResponse[T]":
        """Create a success response."""
        return cls(success=True, message=message, data=data)
    
    @classmethod
    def error(cls, message: str, data: T = None) -> "BaseResponse[T]":
        """Create an error response."""
        return cls(success=False, message=message, data=data)


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated response wrapper.
    
    Used for list endpoints that support pagination.
    """
    items: List[T] = Field(description="List of items")
    total: int = Field(description="Total count of items")
    page: int = Field(description="Current page number (0-indexed)")
    size: int = Field(description="Number of items per page")
    pages: int = Field(description="Total number of pages")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 100,
                "page": 0,
                "size": 20,
                "pages": 5
            }
        }
    )


class ErrorDetail(BaseModel):
    """
    Structured error information.
    
    Provides detailed error context for debugging and user feedback.
    """
    code: str = Field(description="Error code for programmatic handling")
    message: str = Field(description="Human-readable error message")
    field: Optional[str] = Field(default=None, description="Field that caused the error")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional error context")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid email format",
                "field": "email",
                "details": {"pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"}
            }
        }
    )


class ErrorResponse(BaseModel):
    """
    Standard error response format.
    
    Used by exception handlers to provide consistent error responses.
    """
    status: str = Field(default="error", description="Always 'error' for error responses")
    error: ErrorDetail = Field(description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    request_id: Optional[str] = Field(default=None, description="Request correlation ID")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "error",
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Resource not found",
                    "field": None,
                    "details": {"resource_type": "Agent", "resource_id": "abc-123"}
                },
                "timestamp": "2026-03-30T12:00:00Z",
                "request_id": "req-123-456"
            }
        }
    )


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(description="Service health status")
    version: str = Field(description="Application version")
    architecture: str = Field(description="Architecture type")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    dependencies: Optional[Dict[str, str]] = Field(default=None, description="Dependency health status")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "version": "2.0.0",
                "architecture": "modular-monolith",
                "timestamp": "2026-03-30T12:00:00Z",
                "dependencies": {
                    "database": "healthy",
                    "vector_store": "healthy"
                }
            }
        }
    )
