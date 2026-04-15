"""
API routes for Few-Shot Example Engineering.

Phase 2: Few-Shot Example Engineering
=====================================
Provides REST API endpoints for managing and querying the golden queries
repository used for few-shot SQL generation.

Endpoints:
- POST /fewshot/index - Index golden queries into vector store
- POST /fewshot/search - Search for relevant examples
- GET /fewshot/context - Get formatted few-shot context for SQL generation
- GET /fewshot/categories - List available categories
- GET /fewshot/stats - Get indexing statistics
- DELETE /fewshot - Clear the few-shot index
"""
import os
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import get_current_user, require_admin
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User
from app.modules.sql_examples.few_shot_engine import (
    FewShotEngine,
    FewShotExample,
    index_few_shot_examples,
    get_few_shot_context,
    SQLDialect,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/fewshot", tags=["Few-Shot Examples"])


# ============================================
# Request/Response Models
# ============================================

class FewShotIndexRequest(BaseModel):
    """Request to index golden queries."""
    replace_existing: bool = True


class FewShotIndexResponse(BaseModel):
    """Response from indexing operation."""
    success: bool
    indexed: int = 0
    collection_name: str = ""
    error: Optional[str] = None


class FewShotSearchRequest(BaseModel):
    """Request to search for few-shot examples."""
    query: str = Field(..., min_length=5, description="Natural language question")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of examples")
    category: Optional[str] = Field(default=None, description="Filter by category")
    min_complexity: Optional[str] = Field(default=None, description="Minimum complexity (basic, intermediate, advanced)")
    max_complexity: Optional[str] = Field(default=None, description="Maximum complexity")
    dialect: str = Field(default="postgresql", description="Target SQL dialect")


class FewShotExampleResponse(BaseModel):
    """Single few-shot example in response."""
    question: str
    sql: str
    category: str
    tags: List[str]
    description: str
    complexity: str
    dialect_notes: str
    score: float


class FewShotSearchResponse(BaseModel):
    """Response from few-shot search."""
    examples: List[FewShotExampleResponse]
    query: str
    dialect: str


class FewShotContextResponse(BaseModel):
    """Response with formatted few-shot context."""
    context: str
    example_count: int
    query: str
    dialect: str


class FewShotStatsResponse(BaseModel):
    """Statistics about few-shot index."""
    indexed_count: int
    categories: dict
    collection_name: str


# ============================================
# API Endpoints
# ============================================

@router.post("/index", response_model=FewShotIndexResponse)
async def index_golden_queries(
    request: FewShotIndexRequest,
    current_user: User = Depends(require_admin),
):
    """
    Index the golden queries repository into the vector store.
    
    This populates the few-shot examples collection with 50+ curated
    SQL query patterns. Should be called once during setup or when
    updating the golden queries.
    
    Requires Admin role.
    """
    try:
        logger.info(f"Starting few-shot indexing (replace={request.replace_existing})")
        
        result = await index_few_shot_examples(
            replace_existing=request.replace_existing,
        )
        
        return FewShotIndexResponse(
            success=result.get("success", False),
            indexed=result.get("indexed", 0),
            collection_name=result.get("collection_name", ""),
            error=result.get("error"),
        )
        
    except Exception as e:
        logger.error(f"Few-shot indexing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {str(e)}"
        )


@router.post("/search", response_model=FewShotSearchResponse)
async def search_few_shot_examples(
    request: FewShotSearchRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Search for relevant few-shot SQL examples.
    
    Uses vector similarity to find examples that match the user's
    natural language query. Results include the SQL pattern,
    category, and complexity level.
    """
    try:
        engine = FewShotEngine(dialect=request.dialect)
        
        examples = await engine.get_few_shot_examples(
            query=request.query,
            top_k=request.top_k,
            category_filter=request.category,
            min_complexity=request.min_complexity,
            max_complexity=request.max_complexity,
        )
        
        return FewShotSearchResponse(
            examples=[
                FewShotExampleResponse(
                    question=ex.question,
                    sql=ex.sql,
                    category=ex.category,
                    tags=ex.tags,
                    description=ex.description,
                    complexity=ex.complexity,
                    dialect_notes=ex.dialect_notes,
                    score=ex.score,
                )
                for ex in examples
            ],
            query=request.query,
            dialect=request.dialect,
        )
        
    except Exception as e:
        logger.error(f"Few-shot search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/context", response_model=FewShotContextResponse)
async def get_context_for_query(
    query: str = Query(..., min_length=5, description="Natural language question"),
    top_k: int = Query(default=3, ge=1, le=10, description="Number of examples"),
    dialect: str = Query(default="postgresql", description="Target SQL dialect"),
    current_user: User = Depends(get_current_user),
):
    """
    Get formatted few-shot context for SQL generation.
    
    Returns a ready-to-use prompt section containing relevant SQL examples
    with dialect-specific hints. This can be directly inserted into the
    LLM prompt for SQL generation.
    """
    try:
        context = await get_few_shot_context(
            query=query,
            dialect=dialect,
            top_k=top_k,
        )
        
        # Count examples in context
        example_count = context.count("### Example") if context else 0
        
        return FewShotContextResponse(
            context=context,
            example_count=example_count,
            query=query,
            dialect=dialect,
        )
        
    except Exception as e:
        logger.error(f"Failed to get few-shot context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get context: {str(e)}"
        )


@router.get("/categories", response_model=dict)
async def get_categories(
    current_user: User = Depends(get_current_user),
):
    """
    Get available categories for few-shot examples.
    
    Returns a dictionary mapping category names to descriptions,
    useful for filtering examples by SQL pattern type.
    """
    try:
        engine = FewShotEngine()
        categories = await engine.get_categories()
        
        return {
            "categories": categories,
            "count": len(categories),
        }
        
    except Exception as e:
        logger.error(f"Failed to get categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get categories: {str(e)}"
        )


@router.get("/stats", response_model=FewShotStatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
):
    """
    Get statistics about the few-shot index.
    
    Returns the number of indexed examples and available categories.
    """
    try:
        engine = FewShotEngine()
        
        count = await engine.get_example_count()
        categories = await engine.get_categories()
        
        return FewShotStatsResponse(
            indexed_count=count,
            categories=categories,
            collection_name=engine.collection_name,
        )
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.delete("", response_model=dict)
async def clear_index(
    current_user: User = Depends(require_admin),
):
    """
    Clear the few-shot examples index.
    
    Deletes all indexed examples. Re-indexing will be required.
    Requires Admin role.
    """
    try:
        engine = FewShotEngine()
        success = await engine.delete_collection()
        
        return {
            "success": success,
            "message": "Few-shot index cleared" if success else "Failed to clear index",
        }
        
    except Exception as e:
        logger.error(f"Failed to clear index: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear index: {str(e)}"
        )


@router.get("/dialects", response_model=dict)
async def get_supported_dialects(
    current_user: User = Depends(get_current_user),
):
    """
    Get list of supported SQL dialects.
    
    Returns the dialects that few-shot examples can be adapted for.
    """
    return {
        "dialects": [d.value for d in SQLDialect],
        "default": "postgresql",
        "note": "Golden queries are in PostgreSQL syntax. Dialect hints are provided for translation.",
    }
