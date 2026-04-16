"""
Custom exception classes and error handling.

Provides standardized exceptions and error responses across the application.
"""
from enum import Enum
from typing import Optional, Any, Dict
from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""
    # Authentication errors
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    
    # Authorization errors
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    
    # Resource errors
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    
    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    
    # Request errors
    REQUEST_CANCELLED = "REQUEST_CANCELLED"
    
    # General errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    BAD_REQUEST = "BAD_REQUEST"


class AppException(Exception):
    """
    Base exception for application-specific errors.
    
    All custom exceptions should inherit from this.
    """
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API response."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


# ============================================
# Authentication & Authorization Exceptions
# ============================================

class AuthenticationError(AppException):
    """Raised when authentication fails."""
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            **kwargs
        )


class AuthorizationError(AppException):
    """Raised when user lacks required permissions."""
    def __init__(self, message: str = "Insufficient permissions", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            **kwargs
        )


class TokenExpiredError(AuthenticationError):
    """Raised when JWT token has expired."""
    def __init__(self, message: str = "Token has expired", **kwargs):
        super().__init__(message=message, error_code="TOKEN_EXPIRED", **kwargs)


class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid."""
    def __init__(self, message: str = "Invalid token", **kwargs):
        super().__init__(message=message, error_code="INVALID_TOKEN", **kwargs)


# ============================================
# Resource Exceptions
# ============================================

class ResourceNotFoundError(AppException):
    """Raised when a requested resource is not found."""
    def __init__(
        self,
        resource_type: str,
        resource_id: Any,
        **kwargs
    ):
        message = f"{resource_type} with ID {resource_id} not found"
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": str(resource_id)},
            **kwargs
        )


class ResourceAlreadyExistsError(AppException):
    """Raised when trying to create a resource that already exists."""
    def __init__(
        self,
        resource_type: str,
        identifier: str,
        **kwargs
    ):
        message = f"{resource_type} with identifier '{identifier}' already exists"
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="RESOURCE_ALREADY_EXISTS",
            details={"resource_type": resource_type, "identifier": identifier},
            **kwargs
        )


class ResourceConflictError(AppException):
    """Raised when a resource operation creates a conflict."""
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="RESOURCE_CONFLICT",
            **kwargs
        )


# ============================================
# Validation Exceptions
# ============================================

class ValidationError(AppException):
    """Raised when input validation fails."""
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field
        
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            details=details,
            **kwargs
        )


class InvalidConfigurationError(ValidationError):
    """Raised when configuration is invalid."""
    def __init__(self, message: str, config_field: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            field=config_field,
            error_code="INVALID_CONFIGURATION",
            **kwargs
        )


# ============================================
# Database Exceptions
# ============================================

class DatabaseError(AppException):
    """Raised when a database operation fails."""
    def __init__(self, message: str = "Database operation failed", **kwargs):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="DATABASE_ERROR",
            **kwargs
        )


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    def __init__(self, message: str = "Failed to connect to database", **kwargs):
        super().__init__(
            message=message,
            error_code="DATABASE_CONNECTION_ERROR",
            **kwargs
        )


# ============================================
# External Service Exceptions
# ============================================

class ExternalServiceError(AppException):
    """Raised when an external service call fails."""
    def __init__(
        self,
        service_name: str,
        message: str = "External service error",
        **kwargs
    ):
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="EXTERNAL_SERVICE_ERROR",
            details={"service": service_name},
            **kwargs
        )


class LLMError(ExternalServiceError):
    """Raised when LLM API call fails."""
    def __init__(self, provider: str, message: str = "LLM API error", **kwargs):
        super().__init__(
            service_name=provider,
            message=message,
            error_code="LLM_ERROR",
            **kwargs
        )


class EmbeddingError(ExternalServiceError):
    """Raised when embedding generation fails."""
    def __init__(self, provider: str, message: str = "Embedding generation failed", **kwargs):
        super().__init__(
            service_name=provider,
            message=message,
            error_code="EMBEDDING_ERROR",
            **kwargs
        )


class VectorStoreError(ExternalServiceError):
    """Raised when vector store operation fails."""
    def __init__(self, message: str = "Vector store operation failed", **kwargs):
        super().__init__(
            service_name="vector_store",
            message=message,
            error_code="VECTOR_STORE_ERROR",
            **kwargs
        )


# ============================================
# Business Logic Exceptions
# ============================================

class AgentNotFoundError(ResourceNotFoundError):
    """Raised when an agent is not found."""
    def __init__(self, agent_id: Any, **kwargs):
        super().__init__(resource_type="Agent", resource_id=agent_id, **kwargs)


class UserNotFoundError(ResourceNotFoundError):
    """Raised when a user is not found."""
    def __init__(self, user_id: Any, **kwargs):
        super().__init__(resource_type="User", resource_id=user_id, **kwargs)


class InsufficientCreditsError(AppException):
    """Raised when user has insufficient credits."""
    def __init__(self, required: int, available: int, **kwargs):
        super().__init__(
            message=f"Insufficient credits. Required: {required}, Available: {available}",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            error_code="INSUFFICIENT_CREDITS",
            details={"required": required, "available": available},
            **kwargs
        )


class RateLimitExceededError(AppException):
    """Raised when rate limit is exceeded."""
    def __init__(self, limit: int, window: str = "minute", **kwargs):
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window}",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            details={"limit": limit, "window": window},
            **kwargs
        )


# ============================================
# Utility Functions
# ============================================

def convert_app_exception_to_http(exc: AppException) -> HTTPException:
    """
    Convert AppException to FastAPI HTTPException.
    
    Args:
        exc: AppException instance
    
    Returns:
        HTTPException instance
    """
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.to_dict()
    )


class IrrelevantQueryException(AppException):
    """
    Raised when a query cannot be answered by the database.
    
    Classifications:
    - <IRRELEVANT:PII>: Query requests personally identifiable information
    - <IRRELEVANT:CONTEXT>: Query topic not covered by database
    - <IRRELEVANT:SYNTAX>: Query is malformed or invalid
    """
    def __init__(self, message: str, classification: str, **kwargs):
        self.classification = classification
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="IRRELEVANT_QUERY",
            details={"classification": classification},
            **kwargs
        )
