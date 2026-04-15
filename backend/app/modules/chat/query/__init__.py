"""
Query Processing Module — Two-stage SQL generation with schema awareness.

This module provides sophisticated query processing for RAG-based SQL generation:
- SchemaGraph: Graph-based database schema representation with FK introspection
- SchemaLinker: Question-to-schema entity linking
- PromptBuilder: Dynamic, schema-aware prompt construction
- QueryPlanner: Two-stage query generation (NL → QueryPlan → SQL)
- ReflectionService: SQL critique and self-correction
- SchemaContextService: Dynamic schema context injection via vector search
- QueryValidationLayer: SQL error catching and iterative retry system
"""

from .models import (
    QueryPlan,
    SchemaLinkResult,
    CritiqueResponse,
    ColumnInfo,
    TableInfo,
    ForeignKey,
    JoinStep,
    JoinPath,
    Metric,
    Filter,
    OrderSpec,
    TimeRange,
    JoinSpec,
    AggFunction,
    ComparisonOperator,
)
from .schema_graph import SchemaGraph
from .schema_linker import SchemaLinker
from .prompt_builder import PromptBuilder
from .query_planner import QueryPlanner
from .reflection_service import ReflectionService
from .data_dictionary import DataDictionary
from .schema_context_service import SchemaContextService, get_schema_context_service
from .query_validation_layer import (
    QueryValidationLayer,
    SQLValidationResult,
    SQLErrorType,
    validate_and_execute_sql,
)

__all__ = [
    # Models
    "QueryPlan",
    "SchemaLinkResult",
    "CritiqueResponse",
    "ColumnInfo",
    "TableInfo",
    "ForeignKey",
    "JoinStep",
    "JoinPath",
    "Metric",
    "Filter",
    "OrderSpec",
    "TimeRange",
    "JoinSpec",
    "AggFunction",
    "ComparisonOperator",
    # Services
    "SchemaGraph",
    "SchemaLinker",
    "PromptBuilder",
    "QueryPlanner",
    "ReflectionService",
    "DataDictionary",
    # New Services
    "SchemaContextService",
    "get_schema_context_service",
    "QueryValidationLayer",
    "SQLValidationResult",
    "SQLErrorType",
    "validate_and_execute_sql",
]
