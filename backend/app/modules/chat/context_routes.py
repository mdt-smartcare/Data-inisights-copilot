"""
API routes for Dynamic Context Orchestration.

Phase 3: Dynamic Context Orchestration
======================================
Provides REST API endpoints for assembling and previewing the context
used for SQL generation.

Endpoints:
- POST /context/assemble - Assemble context for a query
- GET /context/preview - Preview assembled context as formatted prompt
- GET /context/stats - Get context assembly statistics
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.auth.permissions import get_current_user
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User
from app.modules.chat.context_orchestrator import (
    ContextOrchestrator,

    get_orchestrated_context,
    get_sql_generation_prompt,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/context", tags=["Context Orchestration"])


# ============================================
# Request/Response Models
# ============================================

class ContextAssembleRequest(BaseModel):
    """Request to assemble context for SQL generation."""
    query: str = Field(..., min_length=5, description="Natural language question")
    config_id: Optional[int] = Field(default=None, description="Agent configuration ID")
    dialect: str = Field(default="postgresql", description="Target SQL dialect")
    max_tables: int = Field(default=5, ge=1, le=20, description="Maximum tables to retrieve")
    max_dependencies: int = Field(default=3, ge=0, le=10, description="Maximum FK dependencies")
    max_examples: int = Field(default=3, ge=0, le=10, description="Maximum few-shot examples")
    category_hint: Optional[str] = Field(default=None, description="Category hint for few-shot")


class TableContextResponse(BaseModel):
    """Response model for a single table context."""
    table_name: str
    ddl: str
    column_count: int
    row_count: Optional[int] = None
    is_primary: bool
    is_dependency: bool
    relevance_score: float
    foreign_key_to: List[str]
    foreign_key_from: List[str]
    token_estimate: int


class FewShotContextResponse(BaseModel):
    """Response model for a single few-shot example."""
    question: str
    sql: str
    category: str
    description: str
    complexity: str
    relevance_score: float
    dialect_hints: List[str]
    token_estimate: int


class ContextAssembleResponse(BaseModel):
    """Response from context assembly."""
    # Tables
    tables: List[TableContextResponse]
    tables_retrieved: int
    primary_tables: int
    dependency_tables: int
    
    # Examples
    examples: List[FewShotContextResponse]
    examples_retrieved: int
    
    # Metadata
    config_id: Optional[int]
    dialect: str
    total_tables_available: int
    token_estimate: int
    assembly_time_ms: float
    
    # Relationships
    relationships_overview: Optional[str] = None


class ContextPreviewResponse(BaseModel):
    """Response with formatted prompt preview."""
    prompt: str
    token_estimate: int
    stats: Dict[str, Any]
    query: str
    dialect: str


class ContextStatsResponse(BaseModel):
    """Statistics about context assembly."""
    tables_retrieved: int
    primary_tables: int
    dependency_tables: int
    examples_retrieved: int
    total_tables_available: int
    token_estimate: int
    assembly_time_ms: float
    dialect: str


# ============================================
# API Endpoints
# ============================================

@router.post("/assemble", response_model=ContextAssembleResponse)
async def assemble_context(
    request: ContextAssembleRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Assemble context for SQL generation.
    
    Implements multi-step retrieval:
    1. Semantic Router: Find relevant tables
    2. Dependency Resolution: Add FK-related tables
    3. Few-Shot Retrieval: Get similar SQL examples
    4. Token Budget Management: Trim to fit context window
    
    Returns structured context ready for prompt assembly.
    """
    try:
        orchestrator = ContextOrchestrator(
            config_id=request.config_id,
            dialect=request.dialect,
        )
        
        context = await orchestrator.assemble_context(
            query=request.query,
            max_tables=request.max_tables,
            max_dependencies=request.max_dependencies,
            max_examples=request.max_examples,
            category_hint=request.category_hint,
        )
        
        # Convert to response models
        tables = [
            TableContextResponse(
                table_name=t.table_name,
                ddl=t.ddl,
                column_count=t.column_count,
                row_count=t.row_count,
                is_primary=t.is_primary,
                is_dependency=t.is_dependency,
                relevance_score=t.relevance_score,
                foreign_key_to=t.foreign_key_to,
                foreign_key_from=t.foreign_key_from,
                token_estimate=t.token_estimate(),
            )
            for t in context.table_contexts
        ]
        
        examples = [
            FewShotContextResponse(
                question=e.question,
                sql=e.sql,
                category=e.category,
                description=e.description,
                complexity=e.complexity,
                relevance_score=e.relevance_score,
                dialect_hints=e.dialect_hints,
                token_estimate=e.token_estimate(),
            )
            for e in context.few_shot_examples
        ]
        
        stats = context.get_stats()
        
        return ContextAssembleResponse(
            tables=tables,
            tables_retrieved=stats["tables_retrieved"],
            primary_tables=stats["primary_tables"],
            dependency_tables=stats["dependency_tables"],
            examples=examples,
            examples_retrieved=stats["examples_retrieved"],
            config_id=context.config_id,
            dialect=context.dialect,
            total_tables_available=stats["total_tables_available"],
            token_estimate=stats["token_estimate"],
            assembly_time_ms=stats["assembly_time_ms"],
            relationships_overview=context.relationships_overview,
        )
        
    except Exception as e:
        logger.error(f"Context assembly failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context assembly failed: {str(e)}"
        )


@router.get("/preview", response_model=ContextPreviewResponse)
async def preview_context(
    query: str = Query(..., min_length=5, description="Natural language question"),
    config_id: Optional[int] = Query(default=None, description="Agent configuration ID"),
    dialect: str = Query(default="postgresql", description="Target SQL dialect"),
    max_tables: int = Query(default=5, ge=1, le=20, description="Maximum tables"),
    max_examples: int = Query(default=3, ge=0, le=10, description="Maximum examples"),
    current_user: User = Depends(get_current_user),
):
    """
    Preview the assembled context as a formatted prompt.
    
    Returns the complete prompt string that would be sent to the LLM,
    including system instructions, schema DDLs, and few-shot examples.
    
    Useful for debugging and understanding what context is being used.
    """
    try:
        prompt, stats = await get_sql_generation_prompt(
            query=query,
            config_id=config_id,
            dialect=dialect,
            max_tables=max_tables,
            max_examples=max_examples,
        )
        
        return ContextPreviewResponse(
            prompt=prompt,
            token_estimate=stats["token_estimate"],
            stats=stats,
            query=query,
            dialect=dialect,
        )
        
    except Exception as e:
        logger.error(f"Context preview failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context preview failed: {str(e)}"
        )


@router.post("/stats", response_model=ContextStatsResponse)
async def get_context_stats(
    request: ContextAssembleRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Get statistics about context assembly without the full content.
    
    Lighter-weight endpoint for monitoring context usage.
    """
    try:
        context = await get_orchestrated_context(
            query=request.query,
            config_id=request.config_id,
            dialect=request.dialect,
            max_tables=request.max_tables,
            max_examples=request.max_examples,
        )
        
        stats = context.get_stats()
        
        return ContextStatsResponse(
            tables_retrieved=stats["tables_retrieved"],
            primary_tables=stats["primary_tables"],
            dependency_tables=stats["dependency_tables"],
            examples_retrieved=stats["examples_retrieved"],
            total_tables_available=stats["total_tables_available"],
            token_estimate=stats["token_estimate"],
            assembly_time_ms=stats["assembly_time_ms"],
            dialect=stats["dialect"],
        )
        
    except Exception as e:
        logger.error(f"Context stats failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get context stats: {str(e)}"
        )


@router.get("/dialects")
async def get_supported_dialects(
    current_user: User = Depends(get_current_user),
):
    """
    Get list of supported SQL dialects for context assembly.
    """
    return {
        "dialects": ["postgresql", "mysql", "sqlserver", "oracle", "duckdb", "sqlite"],
        "default": "postgresql",
        "dialect_specific_rules": {
            "postgresql": "Uses DATE_TRUNC, INTERVAL '30 days', window functions",
            "mysql": "Uses DATE_FORMAT, INTERVAL 30 DAY, CURDATE()",
            "sqlserver": "Uses TOP N, DATEADD, GETDATE()",
            "oracle": "Uses TRUNC, FETCH FIRST N ROWS, SYSDATE",
            "duckdb": "Similar to PostgreSQL, uses generate_series",
            "sqlite": "Limited window function support",
        },
    }
