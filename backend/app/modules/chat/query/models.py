"""
Query Plan Models — Structured intermediate representation for SQL generation.

These Pydantic models represent the decomposed query plan that bridges
natural language questions and SQL generation.

The QueryPlan is the output of Stage 1 (QueryPlanner) and input to Stage 2 (SQL Generator).
"""
from enum import Enum
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class AggFunction(str, Enum):
    """Supported SQL aggregation functions."""
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class ComparisonOperator(str, Enum):
    """SQL comparison operators for filters."""
    EQ = "="
    NE = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    LIKE = "LIKE"
    ILIKE = "ILIKE"
    IN = "IN"
    NOT_IN = "NOT IN"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    BETWEEN = "BETWEEN"


# =============================================================================
# Schema Graph Models — Used by SchemaGraph for database introspection
# =============================================================================

class ColumnInfo(BaseModel):
    """Metadata for a database column."""
    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="SQL data type")
    is_nullable: bool = Field(True, description="Whether the column allows NULL")
    is_primary_key: bool = Field(False, description="Whether this is a primary key column")
    is_foreign_key: bool = Field(False, description="Whether this is a foreign key column")
    default_value: Optional[str] = Field(None, description="Default value if any")
    description: Optional[str] = Field(None, description="Column description/comment")


class ForeignKey(BaseModel):
    """Foreign key relationship between tables."""
    source_table: str = Field(..., description="Table containing the FK column")
    source_column: str = Field(..., description="FK column name")
    target_table: str = Field(..., description="Referenced table")
    target_column: str = Field(..., description="Referenced column (usually PK)")
    constraint_name: Optional[str] = Field(None, description="FK constraint name")


class TableInfo(BaseModel):
    """Metadata for a database table."""
    name: str = Field(..., description="Table name")
    schema_name: str = Field("public", description="Schema name")
    columns: List[ColumnInfo] = Field(default_factory=list, description="Table columns")
    primary_keys: List[str] = Field(default_factory=list, description="Primary key column names")
    foreign_keys: List[ForeignKey] = Field(default_factory=list, description="Foreign key relationships")
    description: Optional[str] = Field(None, description="Table description/comment")
    row_count_estimate: Optional[int] = Field(None, description="Estimated row count")


class JoinStep(BaseModel):
    """A single step in a join path between tables."""
    from_table: str = Field(..., description="Source table in this join step")
    from_column: str = Field(..., description="Join column from source table")
    to_table: str = Field(..., description="Target table in this join step")
    to_column: str = Field(..., description="Join column from target table")
    join_type: str = Field("LEFT JOIN", description="Type of join: INNER, LEFT, RIGHT, FULL")


class JoinPath(BaseModel):
    """A path of joins connecting two tables."""
    source_table: str = Field(..., description="Starting table")
    target_table: str = Field(..., description="Ending table")
    steps: List[JoinStep] = Field(default_factory=list, description="Ordered join steps")
    hop_count: int = Field(0, description="Number of joins in the path")


# =============================================================================
# Query Plan Models — Used by QueryPlanner for query decomposition
# =============================================================================

class Metric(BaseModel):
    """A metric/aggregation to compute."""
    column: str = Field(..., description="Column to aggregate")
    function: AggFunction = Field(..., description="Aggregation function")
    alias: Optional[str] = Field(None, description="Optional alias for the result column")
    table: Optional[str] = Field(None, description="Table containing the column (for multi-table queries)")


class Filter(BaseModel):
    """A filter/WHERE condition."""
    column: str = Field(..., description="Column to filter on")
    operator: ComparisonOperator = Field(..., description="Comparison operator")
    value: Any = Field(..., description="Value(s) to compare against")
    table: Optional[str] = Field(None, description="Table containing the column")
    is_default: bool = Field(False, description="Whether this is a default filter (e.g., is_deleted = false)")


class OrderSpec(BaseModel):
    """Ordering specification."""
    column: str = Field(..., description="Column to order by")
    direction: str = Field("ASC", description="ASC or DESC")
    table: Optional[str] = Field(None, description="Table containing the column")


class TimeRange(BaseModel):
    """Time range filter specification."""
    column: str = Field(..., description="Date/timestamp column to filter")
    table: Optional[str] = Field(None, description="Table containing the column")
    start: Optional[str] = Field(None, description="Start date (ISO format)")
    end: Optional[str] = Field(None, description="End date (ISO format)")
    relative: Optional[str] = Field(
        None, description="Relative time like 'last_7_days', 'this_month', 'last_quarter'"
    )


class JoinSpec(BaseModel):
    """Join specification between tables."""
    left_table: str = Field(..., description="Left table in the join")
    left_column: str = Field(..., description="Column from left table")
    right_table: str = Field(..., description="Right table in the join")
    right_column: str = Field(..., description="Column from right table")
    join_type: str = Field("INNER", description="JOIN type: INNER, LEFT, RIGHT, FULL")


class QueryPlan(BaseModel):
    """
    Structured query plan — intermediate representation between NL and SQL.
    
    This is the output of Stage 1 (QueryPlanner) and provides a grounded,
    schema-aware decomposition of the user's question.
    """
    # Core query structure
    entities: List[str] = Field(default_factory=list, description="Tables involved in the query")
    select_columns: List[str] = Field(
        default_factory=list, description="Columns to SELECT (non-aggregated)"
    )
    metrics: List[Metric] = Field(default_factory=list, description="Aggregations to compute")
    filters: List[Filter] = Field(default_factory=list, description="WHERE conditions")
    grouping: List[str] = Field(default_factory=list, description="GROUP BY columns")
    ordering: List[OrderSpec] = Field(default_factory=list, description="ORDER BY specifications")
    limit: Optional[int] = Field(None, description="LIMIT clause value")
    
    # Advanced features
    time_range: Optional[TimeRange] = Field(None, description="Time-based filtering")
    join_strategy: List[JoinSpec] = Field(default_factory=list, description="Join specifications")
    
    # Metadata
    reasoning: str = Field("", description="Explanation of the query plan approach")
    confidence: float = Field(1.0, description="Confidence score (0-1)")


class SchemaLinkResult(BaseModel):
    """
    Result of schema linking — maps NL terms to schema elements.
    
    Used to ground the QueryPlanner in specific tables and columns
    before plan generation.
    """
    tables: List[str] = Field(default_factory=list, description="Matched table names")
    columns: Dict[str, List[str]] = Field(
        default_factory=dict, description="Matched columns by table"
    )
    join_paths: List[JoinPath] = Field(
        default_factory=list, description="Pre-computed join paths between tables"
    )
    default_filters: List[Filter] = Field(
        default_factory=list, description="Default filters to apply"
    )
    resolved_synonyms: Dict[str, str] = Field(
        default_factory=dict, description="Original term -> schema element mappings"
    )
    confidence: float = Field(1.0, description="Linking confidence score")


class CritiqueResponse(BaseModel):
    """
    Response from SQL critique/validation.
    
    Contains validation result and any issues found.
    """
    is_valid: bool = Field(..., description="Whether the SQL is valid")
    reasoning: str = Field("", description="Explanation of the critique")
    issues: List[str] = Field(default_factory=list, description="List of issues found")
    corrected_sql: Optional[str] = Field(None, description="Suggested corrected SQL if invalid")
