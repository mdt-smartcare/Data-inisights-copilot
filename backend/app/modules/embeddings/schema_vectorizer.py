"""
Schema Vectorization Service for DDL-Based Structural Indexing.

Phase 1: Ingestion & Knowledge Base Redesign
============================================
Vectorizes table-level DDL documents instead of naive token chunks.
Each table's enriched DDL is embedded as a single document.

Key Benefits:
- Preserves relational boundaries (complete CREATE TABLE statements)
- Semantic enrichment with column descriptions and business logic
- Metadata filtering by table name and FK dependencies
- Efficient retrieval for SQL generation context

Usage:
    from app.modules.embeddings.schema_vectorizer import SchemaVectorizer
    
    vectorizer = SchemaVectorizer(
        config_id=123,
        db_url="postgresql://user:pass@host:5432/db",
        data_dictionary={"status_code": "Order status (1=Pending, 4=Completed)"},
    )
    
    # Extract and vectorize all table schemas
    await vectorizer.vectorize_schema()
    
    # Query for relevant tables
    results = await vectorizer.search_tables("orders with customer info")
"""
import json
import asyncio
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.utils.logging import get_logger
from app.core.utils.ddl_extractor import (
    DDLExtractor, 
    DuckDBDDLExtractor, 

    enrich_data_dictionary,

)
from app.modules.embeddings.vector_stores.factory import get_vector_store
from app.modules.embeddings.service import _get_embedding_provider

logger = get_logger(__name__)


# Collection name prefix for schema vectors
SCHEMA_COLLECTION_PREFIX = "schema_"


class SchemaVectorizer:
    """
    Service for vectorizing database schemas using DDL-based structural indexing.
    
    Unlike row-level embeddings, this creates one vector per table containing
    the complete enriched DDL statement. This preserves relational structure
    and provides better context for SQL generation.
    """
    
    def __init__(
        self,
        config_id: int,
        db_url: Optional[str] = None,
        duckdb_path: Optional[str] = None,
        duckdb_table_name: Optional[str] = None,
        data_dictionary: Optional[Dict[str, Any]] = None,
        business_rules: Optional[Dict[str, str]] = None,
        embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
    ):
        """
        Initialize schema vectorizer.
        
        Args:
            config_id: Agent configuration ID (used for collection naming)
            db_url: Database connection URL for database sources
            duckdb_path: Path to DuckDB file for file sources
            duckdb_table_name: Table name in DuckDB file
            data_dictionary: Dict mapping column names to descriptions
            business_rules: Dict mapping table.column to business logic
            embedding_model: Embedding model name
            api_key: API key for embedding model (if needed)
            api_base_url: API base URL for embedding model (if needed)
        """
        self.config_id = config_id
        self.db_url = db_url
        self.duckdb_path = duckdb_path
        self.duckdb_table_name = duckdb_table_name
        self.data_dictionary = enrich_data_dictionary(data_dictionary or {})
        self.business_rules = business_rules or {}
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.api_base_url = api_base_url
        
        # Collection name for schema vectors (separate from row vectors)
        self.collection_name = f"{SCHEMA_COLLECTION_PREFIX}config_{config_id}"
        
        # Initialize vector store
        self.vector_store = get_vector_store(self.collection_name)
        
        # Embedding function (loaded lazily)
        self._embed_fn = None
    
    async def _get_embed_fn(self) -> Callable:
        """Get or initialize the embedding function."""
        if self._embed_fn is None:
            self._embed_fn = await _get_embedding_provider(
                self.embedding_model,
                self.api_key,
                self.api_base_url,
            )
        return self._embed_fn
    
    def _extract_ddl_documents(self) -> List[Dict[str, Any]]:
        """
        Extract DDL documents from the data source.
        
        Returns list of documents ready for vectorization.
        """
        documents = []
        
        if self.db_url:
            # Extract from database
            logger.info(f"Extracting DDL from database: {self.db_url.split('@')[-1]}")
            
            extractor = DDLExtractor(
                db_url=self.db_url,
                data_dictionary=self.data_dictionary,
                business_rules=self.business_rules,
            )
            
            try:
                # Extract all table DDLs
                documents = extractor.extract_all_tables(include_row_counts=True)
                
                # Add relationships overview document
                relationships_doc = extractor.extract_relationships_document()
                documents.append(relationships_doc)
                
                logger.info(f"Extracted {len(documents)} DDL documents from database")
            finally:
                extractor.close()
        
        elif self.duckdb_path and self.duckdb_table_name:
            # Extract from DuckDB file
            logger.info(f"Extracting DDL from DuckDB: {self.duckdb_path}")
            
            extractor = DuckDBDDLExtractor(
                duckdb_path=self.duckdb_path,
                table_name=self.duckdb_table_name,
                data_dictionary=self.data_dictionary,
            )
            
            try:
                doc = extractor.extract_ddl_document()
                documents.append(doc)
                logger.info(f"Extracted DDL document for table: {self.duckdb_table_name}")
            finally:
                extractor.close()
        
        else:
            raise ValueError("Either db_url or duckdb_path+duckdb_table_name must be provided")
        
        return documents
    
    async def vectorize_schema(
        self,
        replace_existing: bool = True,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Extract and vectorize all table schemas.
        
        Args:
            replace_existing: If True, delete existing schema vectors first
            on_progress: Optional callback (current, total, message)
        
        Returns:
            Dict with vectorization results
        """
        start_time = datetime.utcnow()
        
        # Delete existing vectors if requested
        if replace_existing:
            try:
                await self.vector_store.delete_collection()
                logger.info(f"Deleted existing schema collection: {self.collection_name}")
            except Exception as e:
                logger.warning(f"Failed to delete existing collection: {e}")
        
        # Extract DDL documents
        if on_progress:
            on_progress(0, 100, "Extracting schema DDL...")
        
        documents = self._extract_ddl_documents()
        
        if not documents:
            return {
                "success": False,
                "error": "No DDL documents extracted",
                "tables_indexed": 0,
            }
        
        # Get embedding function
        if on_progress:
            on_progress(10, 100, "Loading embedding model...")
        
        embed_fn = await self._get_embed_fn()
        
        # Generate embeddings
        if on_progress:
            on_progress(20, 100, f"Generating embeddings for {len(documents)} tables...")
        
        texts = [doc["content"] for doc in documents]
        
        # Handle sync vs async embedding function
        if asyncio.iscoroutinefunction(embed_fn):
            embeddings = await embed_fn(texts)
        else:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, embed_fn, texts)
        
        # Store in vector database
        if on_progress:
            on_progress(80, 100, "Storing vectors...")
        
        ids = [doc["id"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]
        
        await self.vector_store.upsert_batch(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        
        # Verify storage
        count = await self.vector_store.get_collection_count()
        
        if on_progress:
            on_progress(100, 100, f"Indexed {count} schema documents")
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Count tables (exclude relationship overview doc)
        tables_indexed = sum(1 for doc in documents if doc["metadata"].get("doc_type") == "ddl_schema")
        
        logger.info(f"Schema vectorization complete: {tables_indexed} tables in {duration:.1f}s")
        
        return {
            "success": True,
            "tables_indexed": tables_indexed,
            "total_documents": len(documents),
            "vectors_stored": count,
            "collection_name": self.collection_name,
            "duration_seconds": duration,
        }
    
    async def search_tables(
        self,
        query: str,
        top_k: int = 5,
        include_relationships: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant tables based on a natural language query.
        
        Args:
            query: Natural language query (e.g., "orders with customer info")
            top_k: Number of results to return
            include_relationships: Whether to include relationship overview
        
        Returns:
            List of relevant DDL documents with scores
        """
        # Get embedding for query
        embed_fn = await self._get_embed_fn()
        
        if asyncio.iscoroutinefunction(embed_fn):
            query_embedding = (await embed_fn([query]))[0]
        else:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, embed_fn, [query])
            query_embedding = embeddings[0]
        
        # Search vector store
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k + 1 if include_relationships else top_k,
        )
        
        # Process results
        processed_results = []
        relationship_doc = None
        
        for result in results:
            doc_type = result.get("metadata", {}).get("doc_type")
            
            if doc_type == "ddl_relationships":
                relationship_doc = result
            else:
                processed_results.append({
                    "table_name": result.get("metadata", {}).get("table_name"),
                    "ddl": result.get("document"),
                    "score": result.get("score"),
                    "metadata": result.get("metadata"),
                })
        
        # Add relationships doc at the end if requested
        if include_relationships and relationship_doc:
            processed_results.append({
                "table_name": "_relationships",
                "ddl": relationship_doc.get("document"),
                "score": relationship_doc.get("score"),
                "metadata": relationship_doc.get("metadata"),
            })
        
        return processed_results[:top_k]
    
    async def get_table_ddl(self, table_name: str) -> Optional[str]:
        """
        Get the DDL for a specific table by name.
        
        Args:
            table_name: Name of the table
        
        Returns:
            Enriched DDL string or None if not found
        """
        # Search with table name as filter
        # For now, use semantic search with table name
        results = await self.search_tables(f"table {table_name}", top_k=5)
        
        for result in results:
            if result.get("table_name") == table_name:
                return result.get("ddl")
        
        return None
    
    async def get_all_ddls(self) -> List[Dict[str, Any]]:
        """
        Get all stored DDL documents.
        
        Returns:
            List of all DDL documents with metadata
        """
        # Use a generic query to retrieve all documents
        results = await self.search_tables(
            query="database table schema columns",
            top_k=100,
            include_relationships=True,
        )
        return results
    
    async def delete_collection(self) -> bool:
        """Delete the schema vector collection."""
        try:
            await self.vector_store.delete_collection()
            logger.info(f"Deleted schema collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete schema collection: {e}")
            return False


async def vectorize_schema_for_config(
    db: AsyncSession,
    config_id: int,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to vectorize schema for an agent config.
    
    Reads all necessary settings from the agent_config and related tables.
    
    Args:
        db: Database session
        config_id: Agent configuration ID
        on_progress: Optional progress callback
    
    Returns:
        Vectorization results
    """
    from app.modules.agents.models import AgentConfigModel
    from app.modules.data_sources.models import DataSourceModel
    from app.modules.ai_models.models import AIModel
    import os
    
    # Get agent config
    stmt = select(AgentConfigModel).where(AgentConfigModel.id == config_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    
    if not config:
        raise ValueError(f"Configuration {config_id} not found")
    
    # Get data source
    ds_stmt = select(DataSourceModel).where(DataSourceModel.id == config.data_source_id)
    ds_result = await db.execute(ds_stmt)
    data_source = ds_result.scalar_one_or_none()
    
    if not data_source:
        raise ValueError(f"Data source not found for config {config_id}")
    
    # Get embedding model info
    embedding_model = "huggingface/BAAI/bge-base-en-v1.5"
    api_key = None
    api_base_url = None
    
    if config.embedding_model_id:
        model_stmt = select(AIModel).where(AIModel.id == config.embedding_model_id)
        model_result = await db.execute(model_stmt)
        ai_model = model_result.scalar_one_or_none()
        
        if ai_model:
            embedding_model = ai_model.model_id
            api_base_url = ai_model.api_base_url
            
            if ai_model.api_key_env_var:
                api_key = os.environ.get(ai_model.api_key_env_var)
            if not api_key and ai_model.api_key_encrypted:
                from app.core.encryption import decrypt_value
                api_key = decrypt_value(ai_model.api_key_encrypted)
    
    # Parse data dictionary
    data_dictionary = {}
    if config.data_dictionary:
        if isinstance(config.data_dictionary, str):
            try:
                data_dictionary = json.loads(config.data_dictionary)
            except json.JSONDecodeError:
                pass
        else:
            data_dictionary = config.data_dictionary
    
    # Initialize vectorizer based on source type
    if data_source.source_type == "database":
        vectorizer = SchemaVectorizer(
            config_id=config_id,
            db_url=data_source.db_url,
            data_dictionary=data_dictionary,
            embedding_model=embedding_model,
            api_key=api_key,
            api_base_url=api_base_url,
        )
    elif data_source.source_type == "file":
        vectorizer = SchemaVectorizer(
            config_id=config_id,
            duckdb_path=data_source.duckdb_file_path,
            duckdb_table_name=data_source.duckdb_table_name,
            data_dictionary=data_dictionary,
            embedding_model=embedding_model,
            api_key=api_key,
            api_base_url=api_base_url,
        )
    else:
        raise ValueError(f"Unsupported source type: {data_source.source_type}")
    
    # Run vectorization
    return await vectorizer.vectorize_schema(
        replace_existing=True,
        on_progress=on_progress,
    )


async def get_schema_context_for_query(
    config_id: int,
    query: str,
    top_k: int = 5,
    embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
    api_key: Optional[str] = None,
) -> str:
    """
    Get relevant schema context for a natural language query.
    
    This is the main entry point for SQL generation to retrieve
    relevant table DDLs based on the user's question.
    
    Args:
        config_id: Agent configuration ID
        query: User's natural language query
        top_k: Number of relevant tables to retrieve
        embedding_model: Embedding model name
        api_key: API key for embedding model
    
    Returns:
        Combined DDL context string for SQL generation
    """
    collection_name = f"{SCHEMA_COLLECTION_PREFIX}config_{config_id}"
    vector_store = get_vector_store(collection_name)
    
    # Check if collection exists
    if not await vector_store.collection_exists():
        logger.warning(f"Schema collection not found for config {config_id}")
        return ""
    
    # Get embedding function
    embed_fn = await _get_embedding_provider(embedding_model, api_key)
    
    # Generate query embedding
    if asyncio.iscoroutinefunction(embed_fn):
        query_embedding = (await embed_fn([query]))[0]
    else:
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(None, embed_fn, [query])
        query_embedding = embeddings[0]
    
    # Search for relevant schemas
    results = await vector_store.search(
        query_embedding=query_embedding,
        top_k=top_k,
    )
    
    # Combine DDLs into context string
    ddl_parts = []
    for result in results:
        doc = result.get("document", "")
        if doc:
            ddl_parts.append(doc)
    
    return "\n\n".join(ddl_parts)
