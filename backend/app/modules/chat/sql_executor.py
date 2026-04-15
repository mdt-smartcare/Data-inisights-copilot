"""
SQL Execution & Self-Correction Loop.

Phase 4: Execution & Self-Correction Loop
==========================================
Catches dialect-specific syntax errors or invalid column references before
returning the result to the user, with automatic error correction.

Components:
1. Dry-Run Executor: Validates SQL using EXPLAIN or read-only execution
2. Feedback Agent: Captures and parses database error traces
3. Correction Chain: Passes errors back to LLM for self-correction (max 3 retries)

Usage:
    from app.modules.chat.sql_executor import SQLExecutorWithCorrection
    
    executor = SQLExecutorWithCorrection(
        db_url="postgresql://...",
        dialect="postgresql",
    )
    
    # Execute with automatic correction
    result = await executor.execute_with_correction(
        sql="SELECT * FROM patients WHERE age > 50",
        original_query="Show patients over 50",
        schema_context="...",
    )
"""
import re

import traceback
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


from app.core.utils.logging import get_logger
from app.core.settings import get_settings


logger = get_logger(__name__)


# Maximum retry attempts for SQL correction
MAX_CORRECTION_RETRIES = 3

# Error patterns that are correctable
CORRECTABLE_ERROR_PATTERNS = [
    r"column [\"']?(\w+)[\"']? does not exist",
    r"relation [\"']?(\w+)[\"']? does not exist",
    r"table [\"']?(\w+)[\"']? does not exist",
    r"unknown column [\"']?(\w+)[\"']?",
    r"no such column[:\s]+(\w+)",
    r"no such table[:\s]+(\w+)",
    r"syntax error at or near [\"']?(\w+)[\"']?",
    r"syntax error at position",
    r"invalid input syntax",
    r"operator does not exist",
    r"function (\w+) does not exist",
    r"aggregate functions are not allowed in WHERE",
    r"window functions are not allowed in WHERE",
    r"window functions are not allowed in GROUP BY",
    r"column [\"']?(\w+)[\"']? must appear in the GROUP BY clause",
    r"division by zero",
    r"cannot cast",
    r"invalid value for",
    r"date/time field value out of range",
    r"LIMIT must not be negative",
    r"argument of (LIMIT|OFFSET) must not be negative",
]

# Errors that cannot be corrected (security, permissions, etc.)
NON_CORRECTABLE_ERROR_PATTERNS = [
    r"permission denied",
    r"access denied",
    r"authentication failed",
    r"connection refused",
    r"timeout expired",
    r"database .* does not exist",
    r"role .* does not exist",
    r"SSL connection",
]


class ExecutionMode(Enum):
    """SQL execution modes."""
    DRY_RUN = "dry_run"        # EXPLAIN only, no data modification
    READ_ONLY = "read_only"    # Execute but with read-only transaction
    EXECUTE = "execute"        # Full execution


class ErrorSeverity(Enum):
    """Error severity levels."""
    CORRECTABLE = "correctable"      # Can be fixed by LLM
    NON_CORRECTABLE = "non_correctable"  # Cannot be fixed (permissions, etc.)
    UNKNOWN = "unknown"              # Unknown error type


@dataclass
class SQLError:
    """Structured representation of a SQL execution error."""
    error_type: str
    message: str
    severity: ErrorSeverity
    original_sql: str
    position: Optional[int] = None
    line: Optional[int] = None
    hint: Optional[str] = None
    detail: Optional[str] = None
    raw_traceback: Optional[str] = None
    
    def to_correction_prompt(self) -> str:
        """Format error for LLM correction prompt."""
        parts = [
            f"ERROR TYPE: {self.error_type}",
            f"ERROR MESSAGE: {self.message}",
        ]
        
        if self.hint:
            parts.append(f"HINT: {self.hint}")
        
        if self.detail:
            parts.append(f"DETAIL: {self.detail}")
        
        if self.position:
            parts.append(f"ERROR POSITION: Character {self.position}")
        
        if self.line:
            parts.append(f"ERROR LINE: {self.line}")
        
        parts.append(f"\nFAILED SQL:\n```sql\n{self.original_sql}\n```")
        
        return "\n".join(parts)


@dataclass
class ExecutionResult:
    """Result of SQL execution attempt."""
    success: bool
    sql: str
    data: Optional[List[Dict[str, Any]]] = None
    row_count: int = 0
    error: Optional[SQLError] = None
    execution_time_ms: float = 0.0
    was_corrected: bool = False
    correction_attempts: int = 0
    correction_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "sql": self.sql,
            "row_count": self.row_count,
            "execution_time_ms": self.execution_time_ms,
            "was_corrected": self.was_corrected,
            "correction_attempts": self.correction_attempts,
            "error": {
                "type": self.error.error_type,
                "message": self.error.message,
                "severity": self.error.severity.value,
            } if self.error else None,
        }


class ErrorParser:
    """
    Parses database error messages into structured SQLError objects.
    
    Handles error formats from PostgreSQL, DuckDB, MySQL, and SQL Server.
    """
    
    @classmethod
    def parse(cls, exception: Exception, sql: str) -> SQLError:
        """
        Parse an exception into a structured SQLError.
        
        Args:
            exception: The caught exception
            sql: The SQL that caused the error
        
        Returns:
            Structured SQLError object
        """
        error_str = str(exception)
        error_type = type(exception).__name__
        
        # Determine severity
        severity = cls._determine_severity(error_str)
        
        # Extract additional details based on error type
        hint = None
        detail = None
        position = None
        line = None
        
        # PostgreSQL-style errors
        if hasattr(exception, 'orig'):
            orig = exception.orig
            if hasattr(orig, 'pgerror'):
                error_str = orig.pgerror
            if hasattr(orig, 'diag'):
                diag = orig.diag
                hint = getattr(diag, 'hint', None) or getattr(diag, 'message_hint', None)
                detail = getattr(diag, 'message_detail', None)
                if hasattr(diag, 'statement_position'):
                    try:
                        position = int(diag.statement_position)
                    except (ValueError, TypeError):
                        pass
        
        # Try to extract position from error message
        if position is None:
            pos_match = re.search(r'at position (\d+)', error_str, re.IGNORECASE)
            if pos_match:
                position = int(pos_match.group(1))
            
            # Also try "at character X" format
            char_match = re.search(r'at character (\d+)', error_str, re.IGNORECASE)
            if char_match:
                position = int(char_match.group(1))
        
        # Try to extract line number
        line_match = re.search(r'line (\d+)', error_str, re.IGNORECASE)
        if line_match:
            line = int(line_match.group(1))
        
        # Get raw traceback for debugging
        raw_traceback = traceback.format_exc()
        
        return SQLError(
            error_type=error_type,
            message=error_str,
            severity=severity,
            original_sql=sql,
            position=position,
            line=line,
            hint=hint,
            detail=detail,
            raw_traceback=raw_traceback,
        )
    
    @classmethod
    def _determine_severity(cls, error_message: str) -> ErrorSeverity:
        """Determine if an error is correctable."""
        error_lower = error_message.lower()
        
        # Check for non-correctable errors first
        for pattern in NON_CORRECTABLE_ERROR_PATTERNS:
            if re.search(pattern, error_lower):
                return ErrorSeverity.NON_CORRECTABLE
        
        # Check for correctable errors
        for pattern in CORRECTABLE_ERROR_PATTERNS:
            if re.search(pattern, error_lower):
                return ErrorSeverity.CORRECTABLE
        
        return ErrorSeverity.UNKNOWN


class DryRunExecutor:
    """
    Executes SQL in dry-run mode to validate syntax without modifying data.
    
    Uses EXPLAIN for validation when possible, falls back to read-only
    transaction with rollback for databases that don't support EXPLAIN
    for all query types.
    """
    
    def __init__(
        self,
        engine: Engine,
        dialect: str = "postgresql",
    ):
        """
        Initialize dry-run executor.
        
        Args:
            engine: SQLAlchemy engine
            dialect: SQL dialect (postgresql, duckdb, mysql, sqlserver)
        """
        self.engine = engine
        self.dialect = dialect.lower()
    
    def validate_syntax(self, sql: str) -> Tuple[bool, Optional[SQLError]]:
        """
        Validate SQL syntax without executing.
        
        Uses EXPLAIN to check syntax. For DuckDB, also checks for
        common errors that EXPLAIN might miss.
        
        Args:
            sql: SQL query to validate
        
        Returns:
            Tuple of (is_valid, error_if_any)
        """
        # Clean the SQL
        sql = sql.strip()
        if sql.endswith(';'):
            sql = sql[:-1]
        
        try:
            with self.engine.connect() as conn:
                # Use EXPLAIN to validate syntax
                if self.dialect in ("postgresql", "duckdb"):
                    explain_sql = f"EXPLAIN {sql}"
                elif self.dialect == "mysql":
                    explain_sql = f"EXPLAIN {sql}"
                elif self.dialect == "sqlserver":
                    # SQL Server uses SET SHOWPLAN_TEXT ON
                    explain_sql = f"SET SHOWPLAN_TEXT ON; {sql}; SET SHOWPLAN_TEXT OFF"
                else:
                    # Fallback: try EXPLAIN
                    explain_sql = f"EXPLAIN {sql}"
                
                conn.execute(text(explain_sql))
                return True, None
                
        except Exception as e:
            error = ErrorParser.parse(e, sql)
            return False, error
    
    def execute_read_only(
        self, 
        sql: str,
        timeout_seconds: int = 30,
    ) -> ExecutionResult:
        """
        Execute SQL in read-only mode with automatic rollback.
        
        For SELECT queries, executes and returns results.
        For other queries, validates with EXPLAIN only.
        
        Args:
            sql: SQL query to execute
            timeout_seconds: Query timeout
        
        Returns:
            ExecutionResult with data or error
        """
        start_time = datetime.now()
        sql = sql.strip()
        if sql.endswith(';'):
            sql = sql[:-1]
        
        # Check if it's a SELECT query
        is_select = sql.upper().strip().startswith('SELECT')
        
        if not is_select:
            # For non-SELECT queries, only validate syntax
            is_valid, error = self.validate_syntax(sql)
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            if is_valid:
                return ExecutionResult(
                    success=True,
                    sql=sql,
                    data=[{"message": "Query validated (dry-run only for non-SELECT)"}],
                    row_count=0,
                    execution_time_ms=execution_time,
                )
            else:
                return ExecutionResult(
                    success=False,
                    sql=sql,
                    error=error,
                    execution_time_ms=execution_time,
                )
        
        # Execute SELECT query
        try:
            with self.engine.connect() as conn:
                # Set statement timeout if supported
                if self.dialect == "postgresql":
                    conn.execute(text(f"SET statement_timeout = '{timeout_seconds}s'"))
                elif self.dialect == "duckdb":
                    # DuckDB doesn't have statement_timeout, but we can use Python timeout
                    pass
                
                result = conn.execute(text(sql))
                rows = result.fetchall()
                columns = result.keys()
                
                # Convert to list of dicts
                data = [dict(zip(columns, row)) for row in rows]
                
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return ExecutionResult(
                    success=True,
                    sql=sql,
                    data=data,
                    row_count=len(data),
                    execution_time_ms=execution_time,
                )
                
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            error = ErrorParser.parse(e, sql)
            
            return ExecutionResult(
                success=False,
                sql=sql,
                error=error,
                execution_time_ms=execution_time,
            )


class SQLCorrectionChain:
    """
    LLM-based SQL correction chain.
    
    Takes failed SQL and error traces, passes them to the LLM with
    strict instructions to fix the syntax. Capped at MAX_CORRECTION_RETRIES.
    """
    
    # Correction prompt template
    CORRECTION_PROMPT = """You are a SQL debugging expert. A SQL query failed with an error.
Your task is to analyze the error and fix the SQL query.

## Original User Question
{original_query}

## Database Schema
{schema_context}

## Failed SQL Query
```sql
{failed_sql}
```

## Error Details
{error_details}

## Instructions
1. Analyze the error message carefully
2. Identify the exact cause of the error
3. Fix ONLY the specific issue - do not rewrite the entire query unnecessarily
4. Ensure the fix matches the database dialect: {dialect}

## Common Fixes
- "column does not exist": Check column names in schema, fix typos or use correct column
- "syntax error": Check SQL syntax for the specific dialect
- "window function in WHERE": Move window function to CTE, filter in outer query
- "aggregate in WHERE": Use HAVING clause or subquery instead
- "cannot cast": Use appropriate CAST() or type conversion
- "division by zero": Add NULLIF(denominator, 0) or CASE WHEN check

## Response Format
Return ONLY the corrected SQL query. No explanations, no markdown code blocks, just the SQL.
"""
    
    def __init__(
        self,
        dialect: str = "postgresql",
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        """
        Initialize correction chain.
        
        Args:
            dialect: Target SQL dialect
            model: LLM model to use for correction
            temperature: LLM temperature (0 for deterministic)
        """
        self.dialect = dialect
        self.model = model
        self.temperature = temperature
        self._settings = get_settings()
    
    async def correct_sql(
        self,
        failed_sql: str,
        error: SQLError,
        original_query: str,
        schema_context: str,
    ) -> Tuple[str, bool]:
        """
        Attempt to correct a failed SQL query.
        
        Args:
            failed_sql: The SQL that failed
            error: Structured error information
            original_query: Original natural language query
            schema_context: Database schema context
        
        Returns:
            Tuple of (corrected_sql, was_modified)
        """
        from openai import AsyncOpenAI
        
        # Check if error is correctable
        if error.severity == ErrorSeverity.NON_CORRECTABLE:
            logger.warning(f"Error is not correctable: {error.message}")
            return failed_sql, False
        
        # Build correction prompt
        prompt = self.CORRECTION_PROMPT.format(
            original_query=original_query,
            schema_context=schema_context,
            failed_sql=failed_sql,
            error_details=error.to_correction_prompt(),
            dialect=self.dialect.upper(),
        )
        
        try:
            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a SQL debugging expert. Return only corrected SQL, no explanations."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=2000,
            )
            
            corrected_sql = response.choices[0].message.content.strip()
            
            # Clean up response (remove markdown if present)
            corrected_sql = re.sub(r'^```sql\s*', '', corrected_sql)
            corrected_sql = re.sub(r'\s*```$', '', corrected_sql)
            corrected_sql = corrected_sql.strip()
            
            # Check if SQL was actually modified
            was_modified = corrected_sql.lower() != failed_sql.lower()
            
            if was_modified:
                logger.info(f"SQL corrected. Original length: {len(failed_sql)}, New length: {len(corrected_sql)}")
            else:
                logger.warning("LLM returned same SQL without modifications")
            
            return corrected_sql, was_modified
            
        except Exception as e:
            logger.error(f"SQL correction failed: {e}")
            return failed_sql, False


class SQLExecutorWithCorrection:
    """
    SQL Executor with automatic self-correction loop.
    
    Combines dry-run validation, error parsing, and LLM-based correction
    into a single execution pipeline with retry logic.
    """
    
    def __init__(
        self,
        db_url: str,
        dialect: str = "postgresql",
        max_retries: int = MAX_CORRECTION_RETRIES,
        model: str = "gpt-4o-mini",
    ):
        """
        Initialize executor with correction capabilities.
        
        Args:
            db_url: Database connection URL
            dialect: SQL dialect
            max_retries: Maximum correction attempts
            model: LLM model for corrections
        """
        self.db_url = db_url
        self.dialect = dialect.lower()
        self.max_retries = max_retries
        self.model = model
        
        # Initialize engine
        self._engine = self._create_engine()
        
        # Initialize components
        self.dry_run_executor = DryRunExecutor(self._engine, dialect)
        self.correction_chain = SQLCorrectionChain(dialect, model)
    
    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine."""
        if self.db_url.startswith("duckdb://"):
            file_path = self.db_url.replace("duckdb://", "")
            return create_engine(
                f"duckdb:///{file_path}",
                connect_args={"read_only": True},
            )
        else:
            return create_engine(
                self.db_url,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
            )
    
    async def execute_with_correction(
        self,
        sql: str,
        original_query: str,
        schema_context: str,
        execution_mode: ExecutionMode = ExecutionMode.EXECUTE,
    ) -> ExecutionResult:
        """
        Execute SQL with automatic correction on failure.
        
        Implements the self-correction loop:
        1. Try to execute/validate SQL
        2. If error, parse and analyze
        3. If correctable, send to LLM for fix
        4. Retry with corrected SQL
        5. Cap at max_retries attempts
        
        Args:
            sql: SQL query to execute
            original_query: Original natural language query
            schema_context: Database schema for context
            execution_mode: Execution mode (dry_run, read_only, execute)
        
        Returns:
            ExecutionResult with success/failure and correction history
        """
        current_sql = sql
        correction_history = []
        
        for attempt in range(self.max_retries + 1):
            is_retry = attempt > 0
            
            logger.info(f"SQL execution attempt {attempt + 1}/{self.max_retries + 1}")
            
            # Execute based on mode
            if execution_mode == ExecutionMode.DRY_RUN:
                is_valid, error = self.dry_run_executor.validate_syntax(current_sql)
                if is_valid:
                    return ExecutionResult(
                        success=True,
                        sql=current_sql,
                        data=[{"validation": "passed", "mode": "dry_run"}],
                        row_count=0,
                        was_corrected=is_retry,
                        correction_attempts=attempt,
                        correction_history=correction_history,
                    )
                else:
                    result = ExecutionResult(
                        success=False,
                        sql=current_sql,
                        error=error,
                        was_corrected=is_retry,
                        correction_attempts=attempt,
                    )
            else:
                # READ_ONLY or EXECUTE mode
                result = self.dry_run_executor.execute_read_only(current_sql)
                result.was_corrected = is_retry
                result.correction_attempts = attempt
            
            # If successful, return
            if result.success:
                result.correction_history = correction_history
                return result
            
            # If error, attempt correction
            error = result.error
            
            if error is None:
                logger.error("Execution failed but no error captured")
                break
            
            # Check if we should attempt correction
            if error.severity == ErrorSeverity.NON_CORRECTABLE:
                logger.warning(f"Non-correctable error: {error.message}")
                result.correction_history = correction_history
                return result
            
            if attempt >= self.max_retries:
                logger.warning(f"Max correction attempts ({self.max_retries}) reached")
                result.correction_history = correction_history
                return result
            
            # Attempt correction
            logger.info(f"Attempting SQL correction for error: {error.error_type}")
            
            corrected_sql, was_modified = await self.correction_chain.correct_sql(
                failed_sql=current_sql,
                error=error,
                original_query=original_query,
                schema_context=schema_context,
            )
            
            # Record correction attempt
            correction_history.append({
                "attempt": attempt + 1,
                "original_sql": current_sql,
                "error_type": error.error_type,
                "error_message": error.message[:200],
                "corrected_sql": corrected_sql,
                "was_modified": was_modified,
            })
            
            if not was_modified:
                logger.warning("Correction did not modify SQL, stopping retry loop")
                result.correction_history = correction_history
                return result
            
            # Use corrected SQL for next attempt
            current_sql = corrected_sql
        
        # Should not reach here, but just in case
        return ExecutionResult(
            success=False,
            sql=current_sql,
            error=SQLError(
                error_type="MaxRetriesExceeded",
                message=f"Failed after {self.max_retries} correction attempts",
                severity=ErrorSeverity.NON_CORRECTABLE,
                original_sql=sql,
            ),
            correction_attempts=self.max_retries,
            correction_history=correction_history,
        )
    
    async def validate_and_execute(
        self,
        sql: str,
        original_query: str,
        schema_context: str,
    ) -> ExecutionResult:
        """
        Validate SQL first, then execute if valid.
        
        Two-phase execution:
        1. Dry-run validation with EXPLAIN
        2. If valid, execute and return results
        
        Args:
            sql: SQL query
            original_query: Original natural language query
            schema_context: Database schema
        
        Returns:
            ExecutionResult
        """
        # Phase 1: Validate
        is_valid, validation_error = self.dry_run_executor.validate_syntax(sql)
        
        if not is_valid:
            # Attempt correction
            return await self.execute_with_correction(
                sql=sql,
                original_query=original_query,
                schema_context=schema_context,
                execution_mode=ExecutionMode.EXECUTE,
            )
        
        # Phase 2: Execute validated SQL
        result = self.dry_run_executor.execute_read_only(sql)
        
        if not result.success and result.error:
            # Runtime error (not syntax) - attempt correction
            return await self.execute_with_correction(
                sql=sql,
                original_query=original_query,
                schema_context=schema_context,
                execution_mode=ExecutionMode.EXECUTE,
            )
        
        return result


# Convenience functions

async def execute_sql_with_correction(
    sql: str,
    db_url: str,
    original_query: str,
    schema_context: str,
    dialect: str = "postgresql",
    max_retries: int = MAX_CORRECTION_RETRIES,
) -> ExecutionResult:
    """
    Execute SQL with automatic correction.
    
    Main entry point for SQL execution with self-correction loop.
    
    Args:
        sql: SQL query to execute
        db_url: Database connection URL
        original_query: Original natural language query
        schema_context: Database schema context
        dialect: SQL dialect
        max_retries: Maximum correction attempts
    
    Returns:
        ExecutionResult with data or error details
    """
    executor = SQLExecutorWithCorrection(
        db_url=db_url,
        dialect=dialect,
        max_retries=max_retries,
    )
    
    return await executor.execute_with_correction(
        sql=sql,
        original_query=original_query,
        schema_context=schema_context,
    )


def validate_sql_syntax(
    sql: str,
    db_url: str,
    dialect: str = "postgresql",
) -> Tuple[bool, Optional[SQLError]]:
    """
    Validate SQL syntax without executing.
    
    Args:
        sql: SQL query to validate
        db_url: Database connection URL
        dialect: SQL dialect
    
    Returns:
        Tuple of (is_valid, error_if_any)
    """
    if db_url.startswith("duckdb://"):
        file_path = db_url.replace("duckdb://", "")
        engine = create_engine(
            f"duckdb:///{file_path}",
            connect_args={"read_only": True},
        )
    else:
        engine = create_engine(db_url)
    
    executor = DryRunExecutor(engine, dialect)
    return executor.validate_syntax(sql)
