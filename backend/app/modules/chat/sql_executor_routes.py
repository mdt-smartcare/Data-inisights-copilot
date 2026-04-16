"""
API routes for SQL Execution & Self-Correction.

Phase 4: Execution & Self-Correction Loop
==========================================
Provides REST API endpoints for SQL validation, execution with
automatic error correction, and debugging tools.

Endpoints:
- POST /sql/validate - Validate SQL syntax without executing
- POST /sql/execute - Execute SQL with automatic correction
- POST /sql/dry-run - Dry-run execution (EXPLAIN only)
- GET /sql/error-patterns - List known correctable error patterns
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth.permissions import get_current_user
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User
from app.modules.chat.sql_executor import (
    SQLExecutorWithCorrection,

    ErrorParser,
    ExecutionMode,


    ErrorSeverity,
    CORRECTABLE_ERROR_PATTERNS,
    NON_CORRECTABLE_ERROR_PATTERNS,
    MAX_CORRECTION_RETRIES,
    validate_sql_syntax,

)

logger = get_logger(__name__)

router = APIRouter(prefix="/sql", tags=["SQL Execution"])


# ============================================
# Request/Response Models
# ============================================

class SQLValidateRequest(BaseModel):
    """Request to validate SQL syntax."""
    sql: str = Field(..., min_length=5, description="SQL query to validate")
    db_url: str = Field(..., description="Database connection URL")
    dialect: str = Field(default="postgresql", description="SQL dialect")


class SQLExecuteRequest(BaseModel):
    """Request to execute SQL with correction."""
    sql: str = Field(..., min_length=5, description="SQL query to execute")
    db_url: str = Field(..., description="Database connection URL")
    original_query: str = Field(..., description="Original natural language query")
    schema_context: str = Field(default="", description="Database schema context")
    dialect: str = Field(default="postgresql", description="SQL dialect")
    max_retries: int = Field(default=3, ge=0, le=5, description="Max correction attempts")
    execution_mode: str = Field(default="execute", description="Execution mode: dry_run, read_only, execute")


class SQLErrorResponse(BaseModel):
    """Response model for SQL errors."""
    error_type: str
    message: str
    severity: str
    position: Optional[int] = None
    line: Optional[int] = None
    hint: Optional[str] = None
    detail: Optional[str] = None


class CorrectionAttemptResponse(BaseModel):
    """Response model for a correction attempt."""
    attempt: int
    original_sql: str
    error_type: str
    error_message: str
    corrected_sql: str
    was_modified: bool


class SQLValidateResponse(BaseModel):
    """Response from SQL validation."""
    valid: bool
    sql: str
    error: Optional[SQLErrorResponse] = None
    dialect: str


class SQLExecuteResponse(BaseModel):
    """Response from SQL execution with correction."""
    success: bool
    sql: str
    data: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    execution_time_ms: float = 0.0
    was_corrected: bool = False
    correction_attempts: int = 0
    correction_history: List[CorrectionAttemptResponse] = []
    error: Optional[SQLErrorResponse] = None


class ErrorPatternsResponse(BaseModel):
    """Response with known error patterns."""
    correctable_patterns: List[str]
    non_correctable_patterns: List[str]
    max_retries: int


# ============================================
# API Endpoints
# ============================================

@router.post("/validate", response_model=SQLValidateResponse)
async def validate_sql(
    request: SQLValidateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Validate SQL syntax without executing.
    
    Uses EXPLAIN to check syntax. Returns validation result
    with structured error information if invalid.
    """
    try:
        is_valid, error = validate_sql_syntax(
            sql=request.sql,
            db_url=request.db_url,
            dialect=request.dialect,
        )
        
        error_response = None
        if error:
            error_response = SQLErrorResponse(
                error_type=error.error_type,
                message=error.message,
                severity=error.severity.value,
                position=error.position,
                line=error.line,
                hint=error.hint,
                detail=error.detail,
            )
        
        return SQLValidateResponse(
            valid=is_valid,
            sql=request.sql,
            error=error_response,
            dialect=request.dialect,
        )
        
    except Exception as e:
        logger.error(f"SQL validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )


@router.post("/execute", response_model=SQLExecuteResponse)
async def execute_sql(
    request: SQLExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Execute SQL with automatic error correction.
    
    Implements the self-correction loop:
    1. Try to execute SQL
    2. If error, analyze and categorize
    3. If correctable, use LLM to fix
    4. Retry with corrected SQL
    5. Cap at max_retries attempts
    
    Returns execution result with correction history.
    """
    try:
        # Parse execution mode
        mode_map = {
            "dry_run": ExecutionMode.DRY_RUN,
            "read_only": ExecutionMode.READ_ONLY,
            "execute": ExecutionMode.EXECUTE,
        }
        execution_mode = mode_map.get(request.execution_mode.lower(), ExecutionMode.EXECUTE)
        
        executor = SQLExecutorWithCorrection(
            db_url=request.db_url,
            dialect=request.dialect,
            max_retries=request.max_retries,
        )
        
        result = await executor.execute_with_correction(
            sql=request.sql,
            original_query=request.original_query,
            schema_context=request.schema_context,
            execution_mode=execution_mode,
        )
        
        # Convert to response
        error_response = None
        if result.error:
            error_response = SQLErrorResponse(
                error_type=result.error.error_type,
                message=result.error.message,
                severity=result.error.severity.value,
                position=result.error.position,
                line=result.error.line,
                hint=result.error.hint,
                detail=result.error.detail,
            )
        
        correction_history = [
            CorrectionAttemptResponse(
                attempt=h["attempt"],
                original_sql=h["original_sql"],
                error_type=h["error_type"],
                error_message=h["error_message"],
                corrected_sql=h["corrected_sql"],
                was_modified=h["was_modified"],
            )
            for h in result.correction_history
        ]
        
        return SQLExecuteResponse(
            success=result.success,
            sql=result.sql,
            data=result.data,
            row_count=result.row_count,
            execution_time_ms=result.execution_time_ms,
            was_corrected=result.was_corrected,
            correction_attempts=result.correction_attempts,
            correction_history=correction_history,
            error=error_response,
        )
        
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {str(e)}"
        )


@router.post("/dry-run", response_model=SQLExecuteResponse)
async def dry_run_sql(
    request: SQLExecuteRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Dry-run SQL execution (EXPLAIN only).
    
    Validates SQL syntax without returning data.
    Useful for checking queries before execution.
    """
    # Force dry-run mode
    request.execution_mode = "dry_run"
    return await execute_sql(request, current_user)


@router.get("/error-patterns", response_model=ErrorPatternsResponse)
async def get_error_patterns(
    current_user: User = Depends(get_current_user),
):
    """
    Get known correctable and non-correctable error patterns.
    
    Useful for understanding what types of errors can be
    automatically fixed by the correction chain.
    """
    return ErrorPatternsResponse(
        correctable_patterns=CORRECTABLE_ERROR_PATTERNS,
        non_correctable_patterns=NON_CORRECTABLE_ERROR_PATTERNS,
        max_retries=MAX_CORRECTION_RETRIES,
    )


@router.post("/parse-error")
async def parse_error(
    error_message: str,
    sql: str,
    current_user: User = Depends(get_current_user),
):
    """
    Parse an error message into structured format.
    
    Useful for debugging and understanding error classification.
    """
    # Create a mock exception to parse
    class MockException(Exception):
        pass
    
    mock_exc = MockException(error_message)
    error = ErrorParser.parse(mock_exc, sql)
    
    return {
        "error_type": error.error_type,
        "message": error.message,
        "severity": error.severity.value,
        "position": error.position,
        "line": error.line,
        "hint": error.hint,
        "is_correctable": error.severity == ErrorSeverity.CORRECTABLE,
    }
