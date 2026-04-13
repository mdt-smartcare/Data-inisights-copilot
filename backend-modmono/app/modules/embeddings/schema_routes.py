"""
API routes for schema vectorization (DDL-based structural indexing).

Phase 1: Ingestion & Knowledge Base Redesign
============================================
Replaces naive token chunking with table-level structural indexing.
Each table's enriched DDL is embedded as a single document.

Endpoints:
- POST /schema/vectorize - Vectorize schema for an agent config
- POST /schema/search - Search for relevant tables by query
- GET /schema/context/{config_id} - Get DDL context for SQL generation
- DELETE /schema/{config_id} - Delete schema vectors
"""
import os
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import get_current_user, require_admin
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User
from app.modules.embeddings.schema_vectorizer import (
    SchemaVectorizer,
    vectorize_schema_for_config,
    get_schema_context_for_query,
    SCHEMA_COLLECTION_PREFIX,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/schema", tags=["Schema Vectorization"])


# ============================================
# Request/Response Models
# ============================================

class SchemaVectorizeRequest(BaseModel):
    """Request to vectorize schema for an agent configuration."""
    config_id: int
    replace_existing: bool = True


class SchemaVectorizeResponse(BaseModel):
    """Response from schema vectorization."""
    success: bool
    tables_indexed: int = 0
    total_documents: int = 0
    vectors_stored: int = 0
    collection_name: str = ""
    duration_seconds: float = 0.0
    error: Optional[str] = None


class SchemaSearchRequest(BaseModel):
    """Request to search schema vectors."""
    config_id: int
    query: str
    top_k: int = 5


class SchemaSearchResult(BaseModel):
    """Single schema search result."""
    table_name: str
    ddl: str
    score: float
    metadata: Optional[dict] = None


class SchemaSearchResponse(BaseModel):
    """Response from schema search."""
    results: List[SchemaSearchResult]
    query: str
    config_id: int


class SchemaContextResponse(BaseModel):
    """Response with DDL context for SQL generation."""
    config_id: int
    query: str
    context: str
    tables_included: int


# ============================================
# Schema Vectorization Endpoints
# ============================================

@router.post("/vectorize", response_model=SchemaVectorizeResponse)
async def vectorize_schema(
    request: SchemaVectorizeRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Vectorize database schema using DDL-based structural indexing.
    
    Phase 1: Ingestion & Knowledge Base Redesign
    - Extracts complete CREATE TABLE statements including PKs, FKs, and data types
    - Enriches schemas with natural language descriptions from data dictionary
    - Embeds each table's DDL as a single document for better context retrieval
    
    This provides the LLM with proper relational context for SQL generation,
    preserving table boundaries that naive token chunking destroys.
    
    Requires Admin role.
    """
    try:
        logger.info(f"Starting schema vectorization for config {request.config_id}")
        
        result = await vectorize_schema_for_config(
            db=db,
            config_id=request.config_id,
        )
        
        return SchemaVectorizeResponse(
            success=result.get("success", False),
            tables_indexed=result.get("tables_indexed", 0),
            total_documents=result.get("total_documents", 0),
            vectors_stored=result.get("vectors_stored", 0),
            collection_name=result.get("collection_name", ""),
            duration_seconds=result.get("duration_seconds", 0.0),
            error=result.get("error"),
        )
        
    except ValueError as e:
        logger.error(f"Schema vectorization failed: {e}")
        return SchemaVectorizeResponse(
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"Schema vectorization error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Schema vectorization failed: {str(e)}"
        )


@router.post("/search", response_model=SchemaSearchResponse)
async def search_schema(
    request: SchemaSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for relevant table schemas based on a natural language query.
    
    Returns the most relevant DDL statements for the query, which can be
    used as context for SQL generation. Each result includes:
    - Table name
    - Enriched DDL with semantic annotations
    - Relevance score
    - Metadata (column count, FK dependencies, etc.)
    """
    try:
        from app.modules.agents.models import AgentConfigModel
        from app.modules.data_sources.models import DataSourceModel
        from app.modules.ai_models.models import AIModel
        
        # Get agent config to retrieve embedding model info
        stmt = select(AgentConfigModel).where(AgentConfigModel.id == request.config_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration {request.config_id} not found"
            )
        
        # Get embedding model
        embedding_model = "huggingface/BAAI/bge-large-en-v1.5"
        api_key = None
        
        if config.embedding_model_id:
            model_stmt = select(AIModel).where(AIModel.id == config.embedding_model_id)
            model_result = await db.execute(model_stmt)
            ai_model = model_result.scalar_one_or_none()
            
            if ai_model:
                embedding_model = ai_model.model_id
                if ai_model.api_key_env_var:
                    api_key = os.environ.get(ai_model.api_key_env_var)
        
        # Get data source info
        ds_stmt = select(DataSourceModel).where(DataSourceModel.id == config.data_source_id)
        ds_result = await db.execute(ds_stmt)
        data_source = ds_result.scalar_one_or_none()
        
        if not data_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Data source not found for config {request.config_id}"
            )
        
        # Initialize vectorizer based on source type
        if data_source.source_type == "database":
            vectorizer = SchemaVectorizer(
                config_id=request.config_id,
                db_url=data_source.db_url,
                embedding_model=embedding_model,
                api_key=api_key,
            )
        else:
            vectorizer = SchemaVectorizer(
                config_id=request.config_id,
                duckdb_path=data_source.duckdb_file_path,
                duckdb_table_name=data_source.duckdb_table_name,
                embedding_model=embedding_model,
                api_key=api_key,
            )
        
        # Search for relevant tables
        results = await vectorizer.search_tables(
            query=request.query,
            top_k=request.top_k,
        )
        
        return SchemaSearchResponse(
            results=[
                SchemaSearchResult(
                    table_name=r.get("table_name", ""),
                    ddl=r.get("ddl", ""),
                    score=r.get("score", 0.0),
                    metadata=r.get("metadata"),
                )
                for r in results
            ],
            query=request.query,
            config_id=request.config_id,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Schema search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Schema search failed: {str(e)}"
        )


@router.get("/context/{config_id}", response_model=SchemaContextResponse)
async def get_schema_context(
    config_id: int,
    query: str,
    top_k: int = 5,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get relevant schema context for SQL generation.
    
    This endpoint returns a combined DDL context string that can be
    directly inserted into the SQL generation prompt. It retrieves
    the most relevant table schemas based on the user's query.
    
    Args:
        config_id: Agent configuration ID
        query: User's natural language question
        top_k: Number of relevant tables to include
    
    Returns:
        Combined DDL context string with table count
    """
    try:
        from app.modules.agents.models import AgentConfigModel
        from app.modules.ai_models.models import AIModel
        
        # Get embedding model info
        stmt = select(AgentConfigModel).where(AgentConfigModel.id == config_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        
        embedding_model = "huggingface/BAAI/bge-large-en-v1.5"
        api_key = None
        
        if config and config.embedding_model_id:
            model_stmt = select(AIModel).where(AIModel.id == config.embedding_model_id)
            model_result = await db.execute(model_stmt)
            ai_model = model_result.scalar_one_or_none()
            
            if ai_model:
                embedding_model = ai_model.model_id
                if ai_model.api_key_env_var:
                    api_key = os.environ.get(ai_model.api_key_env_var)
        
        context = await get_schema_context_for_query(
            config_id=config_id,
            query=query,
            top_k=top_k,
            embedding_model=embedding_model,
            api_key=api_key,
        )
        
        return SchemaContextResponse(
            config_id=config_id,
            query=query,
            context=context,
            tables_included=context.count("CREATE TABLE") if context else 0,
        )
        
    except Exception as e:
        logger.error(f"Failed to get schema context: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get schema context: {str(e)}"
        )


@router.delete("/{config_id}", response_model=dict)
async def delete_schema_vectors(
    config_id: int,
    current_user: User = Depends(require_admin),
):
    """
    Delete schema vectors for an agent configuration.
    
    This removes the schema vector collection, so the next vectorization
    will start fresh. Requires Admin role.
    """
    try:
        from app.modules.embeddings.vector_stores.factory import get_vector_store
        
        collection_name = f"{SCHEMA_COLLECTION_PREFIX}config_{config_id}"
        vector_store = get_vector_store(collection_name)
        
        await vector_store.delete_collection()
        
        return {
            "status": "deleted",
            "config_id": config_id,
            "collection_name": collection_name,
            "message": "Schema vectors deleted successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to delete schema vectors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete schema vectors: {str(e)}"
        )
