"""
Query Validation Layer — SQL error catching and iterative retry system.

Implements a robust validation and retry mechanism for SQL queries that:
1. Catches SQL execution errors (syntax, missing columns, type mismatches)
2. Analyzes error messages to understand the root cause
3. Uses LLM to fix the query based on error context
4. Retries with exponential backoff up to max_retries
5. Tracks retry statistics for monitoring

This creates a self-healing SQL generation pipeline that dramatically
improves accuracy on first-attempt failures.
"""
import re
import time
import asyncio
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

from app.core.utils.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()


class SQLErrorType(Enum):
    """Classification of SQL error types for targeted fixing."""
    SYNTAX_ERROR = "syntax_error"
    COLUMN_NOT_FOUND = "column_not_found"
    TABLE_NOT_FOUND = "table_not_found"
    TYPE_MISMATCH = "type_mismatch"
    WINDOW_FUNCTION_MISUSE = "window_function_misuse"
    AGGREGATE_MISUSE = "aggregate_misuse"
    AMBIGUOUS_COLUMN = "ambiguous_column"
    DATE_FUNCTION_ERROR = "date_function_error"
    DIVISION_BY_ZERO = "division_by_zero"
    NULL_CONSTRAINT = "null_constraint"
    PERMISSION_DENIED = "permission_denied"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class SQLValidationResult:
    """Result of SQL validation/execution attempt."""
    success: bool
    sql: str
    result: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[SQLErrorType] = None
    attempt_number: int = 1
    execution_time_ms: float = 0.0
    fix_applied: Optional[str] = None


@dataclass 
class RetryStatistics:
    """Statistics for monitoring retry behavior."""
    total_queries: int = 0
    first_attempt_success: int = 0
    retry_success: int = 0
    final_failure: int = 0
    total_retries: int = 0
    avg_retries_on_success: float = 0.0
    error_type_counts: Dict[str, int] = field(default_factory=dict)
    
    def record_success(self, attempt: int) -> None:
        """Record a successful query."""
        self.total_queries += 1
        if attempt == 1:
            self.first_attempt_success += 1
        else:
            self.retry_success += 1
            self.total_retries += attempt - 1
            # Update running average
            total_with_retries = self.retry_success
            if total_with_retries > 0:
                self.avg_retries_on_success = self.total_retries / total_with_retries
    
    def record_failure(self, attempts: int, error_type: SQLErrorType) -> None:
        """Record a failed query."""
        self.total_queries += 1
        self.final_failure += 1
        self.total_retries += attempts - 1
        
        error_key = error_type.value
        self.error_type_counts[error_key] = self.error_type_counts.get(error_key, 0) + 1


# Global statistics tracker
_retry_stats = RetryStatistics()


class QueryValidationLayer:
    """
    SQL query validation and automatic retry layer.
    
    Wraps SQL execution with error detection, analysis, and automatic
    fixing using LLM-based query correction.
    
    Features:
    - Automatic error classification
    - LLM-based query fixing
    - Configurable retry limits
    - Exponential backoff
    - Detailed error reporting
    - Statistics tracking
    
    Usage:
        validator = QueryValidationLayer(
            execute_fn=sql_service.execute_query,
            schema_context=schema,
            max_retries=3
        )
        result = await validator.execute_with_retry(sql, question)
    """
    
    def __init__(
        self,
        execute_fn: Callable[[str], Tuple[List[Dict], int]],
        schema_context: str,
        dialect: str = "duckdb",
        max_retries: int = 3,
        retry_delay_base: float = 0.5,
        llm_model: str = "gpt-4o-mini",
    ):
        """
        Initialize the validation layer.
        
        Args:
            execute_fn: Function to execute SQL queries
            schema_context: Database schema for context
            dialect: SQL dialect ("duckdb" or "postgresql")
            max_retries: Maximum number of retry attempts
            retry_delay_base: Base delay for exponential backoff (seconds)
            llm_model: LLM model to use for query fixing
        """
        self.execute_fn = execute_fn
        self.schema_context = schema_context
        self.dialect = dialect
        self.max_retries = max_retries
        self.retry_delay_base = retry_delay_base
        self.llm_model = llm_model
        
        # Import PromptBuilder for fix prompts
        from app.modules.chat.query.prompt_builder import PromptBuilder
        self.prompt_builder = PromptBuilder()
        
        logger.info(
            f"QueryValidationLayer initialized: dialect={dialect}, "
            f"max_retries={max_retries}"
        )
    
    async def execute_with_retry(
        self,
        sql: str,
        original_question: str,
        sample_data: str = "",
    ) -> SQLValidationResult:
        """
        Execute SQL with automatic retry on failure.
        
        Args:
            sql: SQL query to execute
            original_question: Original natural language question
            sample_data: Optional sample data for context
            
        Returns:
            SQLValidationResult with success/failure info and results
        """
        current_sql = sql
        last_error = None
        last_error_type = None
        
        for attempt in range(1, self.max_retries + 1):
            logger.debug(f"Attempt {attempt}/{self.max_retries}: {current_sql[:100]}...")
            
            # Try to execute
            result = await self._try_execute(current_sql)
            
            if result.success:
                result.attempt_number = attempt
                _retry_stats.record_success(attempt)
                
                if attempt > 1:
                    logger.info(
                        f"Query succeeded on attempt {attempt} after fixing "
                        f"error: {last_error_type.value if last_error_type else 'unknown'}"
                    )
                
                return result
            
            # Execution failed
            last_error = result.error
            last_error_type = result.error_type
            
            logger.warning(
                f"Attempt {attempt} failed: {result.error_type.value} - "
                f"{result.error[:100] if result.error else 'Unknown error'}..."
            )
            
            # Check if error is retryable
            if not self._is_retryable(result.error_type):
                logger.info(f"Error type {result.error_type.value} is not retryable")
                _retry_stats.record_failure(attempt, result.error_type)
                return result
            
            # Don't retry on last attempt
            if attempt >= self.max_retries:
                break
            
            # Try to fix the query
            fixed_sql = await self._fix_query(
                current_sql,
                result.error,
                result.error_type,
                original_question,
                sample_data
            )
            
            if fixed_sql and fixed_sql != current_sql:
                logger.info(f"Fixed SQL generated for attempt {attempt + 1}")
                current_sql = fixed_sql
                result.fix_applied = f"Fixed {result.error_type.value}"
            else:
                logger.warning("Could not generate a fix, retrying same query")
            
            # Exponential backoff
            delay = self.retry_delay_base * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
        
        # All retries exhausted
        _retry_stats.record_failure(self.max_retries, last_error_type or SQLErrorType.UNKNOWN)
        
        return SQLValidationResult(
            success=False,
            sql=current_sql,
            error=last_error,
            error_type=last_error_type,
            attempt_number=self.max_retries,
        )
    
    async def _try_execute(self, sql: str) -> SQLValidationResult:
        """
        Try to execute a SQL query and capture results or errors.
        """
        start_time = time.time()
        
        try:
            # Execute the query
            loop = asyncio.get_event_loop()
            results, count = await loop.run_in_executor(
                None, self.execute_fn, sql
            )
            
            execution_time = (time.time() - start_time) * 1000
            
            return SQLValidationResult(
                success=True,
                sql=sql,
                result={"rows": results, "count": count},
                execution_time_ms=execution_time,
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_str = str(e)
            error_type = self._classify_error(error_str)
            
            return SQLValidationResult(
                success=False,
                sql=sql,
                error=error_str,
                error_type=error_type,
                execution_time_ms=execution_time,
            )
    
    def _classify_error(self, error_message: str) -> SQLErrorType:
        """
        Classify a SQL error message into an error type.
        """
        error_lower = error_message.lower()
        
        # Column not found
        if any(phrase in error_lower for phrase in [
            "column", "does not exist", "unknown column", 
            "no such column", "invalid column", "not found"
        ]):
            if "table" in error_lower:
                return SQLErrorType.TABLE_NOT_FOUND
            return SQLErrorType.COLUMN_NOT_FOUND
        
        # Table not found
        if any(phrase in error_lower for phrase in [
            "table", "relation", "does not exist", 
            "no such table", "unknown table"
        ]):
            return SQLErrorType.TABLE_NOT_FOUND
        
        # Window function misuse (common in DuckDB)
        if any(phrase in error_lower for phrase in [
            "window function", "over clause", "partition by",
            "window functions are not allowed", "cannot use window"
        ]):
            return SQLErrorType.WINDOW_FUNCTION_MISUSE
        
        # Aggregate misuse
        if any(phrase in error_lower for phrase in [
            "aggregate", "group by", "must appear in group by",
            "not in group by", "aggregates not allowed"
        ]):
            return SQLErrorType.AGGREGATE_MISUSE
        
        # Type mismatch
        if any(phrase in error_lower for phrase in [
            "type mismatch", "cannot compare", "incompatible types",
            "cannot cast", "conversion failed", "invalid input syntax"
        ]):
            return SQLErrorType.TYPE_MISMATCH
        
        # Date function errors
        if any(phrase in error_lower for phrase in [
            "date", "timestamp", "interval", "datediff",
            "date_trunc", "invalid date"
        ]):
            return SQLErrorType.DATE_FUNCTION_ERROR
        
        # Ambiguous column
        if "ambiguous" in error_lower:
            return SQLErrorType.AMBIGUOUS_COLUMN
        
        # Syntax error
        if any(phrase in error_lower for phrase in [
            "syntax error", "parse error", "unexpected",
            "near", "at or near"
        ]):
            return SQLErrorType.SYNTAX_ERROR
        
        # Division by zero
        if "division by zero" in error_lower or "divide by zero" in error_lower:
            return SQLErrorType.DIVISION_BY_ZERO
        
        # Permission denied
        if "permission denied" in error_lower or "access denied" in error_lower:
            return SQLErrorType.PERMISSION_DENIED
        
        # Connection error
        if any(phrase in error_lower for phrase in [
            "connection", "timeout", "network", "refused"
        ]):
            return SQLErrorType.CONNECTION_ERROR
        
        return SQLErrorType.UNKNOWN
    
    def _is_retryable(self, error_type: SQLErrorType) -> bool:
        """
        Determine if an error type is worth retrying.
        """
        non_retryable = {
            SQLErrorType.PERMISSION_DENIED,
            SQLErrorType.CONNECTION_ERROR,
            SQLErrorType.TIMEOUT,
        }
        return error_type not in non_retryable
    
    async def _fix_query(
        self,
        failed_sql: str,
        error_message: str,
        error_type: SQLErrorType,
        original_question: str,
        sample_data: str = "",
    ) -> Optional[str]:
        """
        Use LLM to fix a failed SQL query.
        """
        try:
            from langchain_openai import ChatOpenAI
            
            # Build error-specific fix hints
            fix_hints = self._get_fix_hints(error_type, error_message)
            
            # Build the fix prompt
            fix_prompt = self._build_fix_prompt(
                failed_sql,
                error_message,
                error_type,
                original_question,
                fix_hints,
                sample_data
            )
            
            # Call LLM
            llm = ChatOpenAI(
                temperature=0,
                model_name=self.llm_model,
                api_key=settings.openai_api_key,
            )
            
            response = await llm.ainvoke(fix_prompt)
            fixed_sql = response.content.strip()
            
            # Clean up response
            fixed_sql = self._clean_sql_response(fixed_sql)
            
            return fixed_sql if fixed_sql else None
            
        except Exception as e:
            logger.error(f"Failed to generate fix: {e}")
            return None
    
    def _get_fix_hints(
        self,
        error_type: SQLErrorType,
        error_message: str,
    ) -> str:
        """
        Get specific fix hints based on error type.
        """
        hints = {
            SQLErrorType.COLUMN_NOT_FOUND: """
- Check column names against the schema (they may have different casing or underscores)
- The column might be in a different table - check all available tables
- Use table aliases consistently when joining
""",
            SQLErrorType.TABLE_NOT_FOUND: """
- Check table names against the schema exactly
- Table names are case-sensitive in some databases
- Ensure you're using the correct schema/database prefix
""",
            SQLErrorType.WINDOW_FUNCTION_MISUSE: """
CRITICAL FIX FOR WINDOW FUNCTIONS:
- Window functions (LAG, LEAD, ROW_NUMBER, RANK) CANNOT be in WHERE clause
- Window functions CANNOT be in GROUP BY clause
- ALWAYS use CTE pattern:
  WITH computed AS (
      SELECT *, ROW_NUMBER() OVER (...) AS rn
      FROM table
  )
  SELECT * FROM computed WHERE rn = 1
""",
            SQLErrorType.AGGREGATE_MISUSE: """
- Aggregates (COUNT, SUM, AVG) CANNOT be in WHERE clause - use HAVING
- All non-aggregated columns in SELECT must be in GROUP BY
- Use subquery/CTE for filtering on aggregate results
""",
            SQLErrorType.TYPE_MISMATCH: """
- Check column types in schema and cast appropriately
- For date comparisons, ensure both sides are DATE/TIMESTAMP
- Use CAST(column AS TYPE) or ::type syntax
""",
            SQLErrorType.DATE_FUNCTION_ERROR: """
DuckDB DATE RULES:
- DATEDIFF requires 3 arguments: DATEDIFF('day', start_date, end_date)
- Date subtraction: date_col - INTERVAL '90 days'
- Use CAST(varchar_col AS TIMESTAMP) for string dates
- DATE_TRUNC('month', date_col) for truncation
""",
            SQLErrorType.AMBIGUOUS_COLUMN: """
- Use table aliases for all column references
- Example: t.column_name instead of just column_name
- Prefix with table alias in JOIN conditions
""",
            SQLErrorType.SYNTAX_ERROR: """
- Check for missing commas, parentheses, or quotes
- Ensure keywords are spelled correctly
- Check that string literals use single quotes
""",
        }
        
        return hints.get(error_type, "- Review the error message and fix accordingly")
    
    def _build_fix_prompt(
        self,
        failed_sql: str,
        error_message: str,
        error_type: SQLErrorType,
        original_question: str,
        fix_hints: str,
        sample_data: str = "",
    ) -> str:
        """
        Build a prompt for the LLM to fix the SQL query.
        """
        dialect_name = "DuckDB" if self.dialect == "duckdb" else "PostgreSQL"
        
        prompt_parts = [
            f"You are a {dialect_name} SQL expert. Fix the failed SQL query.",
            "",
            "ORIGINAL QUESTION:",
            original_question,
            "",
            "DATABASE SCHEMA:",
            self.schema_context,
        ]
        
        if sample_data:
            prompt_parts.extend([
                "",
                "SAMPLE DATA:",
                sample_data,
            ])
        
        prompt_parts.extend([
            "",
            "FAILED SQL:",
            failed_sql,
            "",
            f"ERROR ({error_type.value}):",
            error_message,
            "",
            "FIX HINTS:",
            fix_hints,
            "",
            "INSTRUCTIONS:",
            "1. Analyze the error message carefully",
            "2. Apply the fix hints relevant to this error type",
            "3. Use ONLY tables and columns from the schema above",
            "4. Return ONLY the corrected SQL query, no explanation",
            "",
            "CORRECTED SQL:",
        ])
        
        return "\n".join(prompt_parts)
    
    def _clean_sql_response(self, response: str) -> str:
        """
        Clean up LLM response to extract pure SQL.
        """
        # Remove markdown code blocks
        response = re.sub(r'```sql\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        # Remove common prefixes
        response = re.sub(r'^(SQL|Query|CORRECTED SQL|Here is|Here\'s):\s*', '', response, flags=re.IGNORECASE)
        
        # Trim whitespace
        response = response.strip()
        
        # Validate it looks like SQL
        if not response:
            return ""
        
        first_word = response.split()[0].upper() if response.split() else ""
        if first_word not in {"SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "("}:
            # Try to find SQL in the response
            match = re.search(r'(SELECT|WITH)\s+.+', response, re.IGNORECASE | re.DOTALL)
            if match:
                response = match.group(0)
            else:
                return ""
        
        return response
    
    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """Get retry statistics for monitoring."""
        return {
            "total_queries": _retry_stats.total_queries,
            "first_attempt_success": _retry_stats.first_attempt_success,
            "first_attempt_success_rate": (
                _retry_stats.first_attempt_success / _retry_stats.total_queries * 100
                if _retry_stats.total_queries > 0 else 0
            ),
            "retry_success": _retry_stats.retry_success,
            "retry_success_rate": (
                _retry_stats.retry_success / (_retry_stats.retry_success + _retry_stats.final_failure) * 100
                if (_retry_stats.retry_success + _retry_stats.final_failure) > 0 else 0
            ),
            "final_failure": _retry_stats.final_failure,
            "avg_retries_on_success": _retry_stats.avg_retries_on_success,
            "error_type_breakdown": _retry_stats.error_type_counts,
        }
    
    @staticmethod
    def reset_statistics() -> None:
        """Reset retry statistics."""
        global _retry_stats
        _retry_stats = RetryStatistics()


# =============================================================================
# Convenience Functions
# =============================================================================

async def validate_and_execute_sql(
    sql: str,
    question: str,
    execute_fn: Callable[[str], Tuple[List[Dict], int]],
    schema_context: str,
    dialect: str = "duckdb",
    max_retries: int = 3,
    sample_data: str = "",
) -> SQLValidationResult:
    """
    Convenience function to validate and execute SQL with retry.
    
    Args:
        sql: SQL query to execute
        question: Original natural language question
        execute_fn: Function to execute SQL
        schema_context: Database schema
        dialect: SQL dialect
        max_retries: Maximum retries
        sample_data: Optional sample data
        
    Returns:
        SQLValidationResult with execution results
    """
    validator = QueryValidationLayer(
        execute_fn=execute_fn,
        schema_context=schema_context,
        dialect=dialect,
        max_retries=max_retries,
    )
    
    return await validator.execute_with_retry(sql, question, sample_data)
