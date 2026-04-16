"""
Schema Vector Store Migration Module.

Phase 3: Vector Store Migration
===============================
Migrates from fragmented token chunks to table-level DDL embeddings.

Key Features:
- Purges existing vector index containing fragmented token chunks
- Validates embedding model context window against longest DDL
- Embeds each full DDL string as a single vector
- Upserts with strict metadata: {"table_name": str, "foreign_keys": list[str]}

Usage:
    from app.modules.embeddings.schema_migration import SchemaMigrator
    
    migrator = SchemaMigrator(
        config_id=123,
        db_url="postgresql://user:pass@host:5432/db",
    )
    
    # Run full migration
    result = await migrator.migrate()
    
    # Or step by step
    await migrator.purge_existing_vectors()
    await migrator.validate_context_window()
    await migrator.embed_and_upsert_ddls()
"""
import asyncio
import hashlib
import json
from typing import Dict, List, Any, Optional, Callable, Tuple
from datetime import datetime
from dataclasses import dataclass

from app.core.utils.logging import get_logger
from app.core.utils.ddl_extractor import (
    extract_ddl_from_information_schema,
    extract_all_ddls_from_information_schema,
    get_table_ddl_with_metadata,
    DDLExtractor,
    DuckDBDDLExtractor,
    enrich_data_dictionary,
)
from app.modules.embeddings.vector_stores.factory import get_vector_store, get_vector_store_type
from app.modules.embeddings.service import _get_embedding_provider

logger = get_logger(__name__)


# =============================================================================
# Context Window Limits for Common Embedding Models
# =============================================================================
# These are token limits - actual character limits are roughly 4x tokens
EMBEDDING_MODEL_CONTEXT_WINDOWS = {
    # OpenAI Models
    "text-embedding-3-small": 8191,
    "text-embedding-3-large": 8191,
    "text-embedding-ada-002": 8191,
    
    # BGE Models (HuggingFace)
    "bge-base-en-v1.5": 512,
    "bge-base-en-v1.5": 512,
    "bge-small-en-v1.5": 512,
    "bge-m3": 8192,
    
    # Sentence Transformers
    "all-minilm-l6-v2": 256,
    "all-mpnet-base-v2": 384,
    "multi-qa-mpnet-base-dot-v1": 512,
    
    # E5 Models
    "e5-large-v2": 512,
    "e5-base-v2": 512,
    "e5-small-v2": 512,
    
    # Default fallback
    "default": 512,
}

# Approximate characters per token (conservative estimate)
CHARS_PER_TOKEN = 4


@dataclass
class MigrationResult:
    """Result of a schema migration operation."""
    success: bool
    tables_migrated: int
    vectors_created: int
    longest_ddl_chars: int
    longest_ddl_tokens: int
    model_context_window: int
    context_window_sufficient: bool
    purged_old_vectors: int
    duration_seconds: float
    errors: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "tables_migrated": self.tables_migrated,
            "vectors_created": self.vectors_created,
            "longest_ddl_chars": self.longest_ddl_chars,
            "longest_ddl_tokens": self.longest_ddl_tokens,
            "model_context_window": self.model_context_window,
            "context_window_sufficient": self.context_window_sufficient,
            "purged_old_vectors": self.purged_old_vectors,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
        }


class SchemaMigrator:
    """
    Handles migration from fragmented token chunks to table-level DDL embeddings.
    
    This migrator:
    1. Purges existing vector indexes (both row-level and old schema indexes)
    2. Validates that the embedding model's context window can handle the longest DDL
    3. Extracts clean DDL statements from information_schema
    4. Embeds each full DDL as a single vector
    5. Upserts with strict metadata format
    """
    
    def __init__(
        self,
        config_id: int,
        db_url: Optional[str] = None,
        duckdb_path: Optional[str] = None,
        duckdb_table_name: Optional[str] = None,
        data_dictionary: Optional[Dict[str, Any]] = None,
        embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        schema_name: str = "public",
    ):
        """
        Initialize the schema migrator.
        
        Args:
            config_id: Agent configuration ID
            db_url: Database connection URL (for database sources)
            duckdb_path: Path to DuckDB file (for file sources)
            duckdb_table_name: Table name in DuckDB
            data_dictionary: Optional column descriptions for enrichment
            embedding_model: Embedding model identifier
            api_key: API key for embedding model
            api_base_url: API base URL for embedding model
            schema_name: Database schema name (default: "public")
        """
        self.config_id = config_id
        self.db_url = db_url
        self.duckdb_path = duckdb_path
        self.duckdb_table_name = duckdb_table_name
        self.data_dictionary = enrich_data_dictionary(data_dictionary or {})
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.api_base_url = api_base_url
        self.schema_name = schema_name
        
        # Collection names
        self.schema_collection_name = f"schema_config_{config_id}"
        self.row_collection_name = f"agent_*_config_{config_id}"  # Pattern for row vectors
        
        # Lazy-loaded components
        self._embed_fn = None
        self._vector_store = None
        
        # Extracted DDLs cache
        self._ddl_documents: List[Dict[str, Any]] = []
    
    @property
    def vector_store(self):
        """Get or create vector store instance."""
        if self._vector_store is None:
            self._vector_store = get_vector_store(self.schema_collection_name)
        return self._vector_store
    
    async def _get_embed_fn(self) -> Callable:
        """Get or initialize the embedding function."""
        if self._embed_fn is None:
            self._embed_fn = await _get_embedding_provider(
                self.embedding_model,
                self.api_key,
                self.api_base_url,
            )
        return self._embed_fn
    
    def _get_model_context_window(self) -> int:
        """Get the context window size for the current embedding model."""
        model_name = self.embedding_model.lower()
        
        # Extract model name from provider prefix
        if "/" in model_name:
            model_name = model_name.split("/")[-1]
        
        # Check known models
        for known_model, context_window in EMBEDDING_MODEL_CONTEXT_WINDOWS.items():
            if known_model in model_name:
                return context_window
        
        # Default fallback
        logger.warning(f"Unknown embedding model '{self.embedding_model}', using default context window")
        return EMBEDDING_MODEL_CONTEXT_WINDOWS["default"]
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (conservative estimate)."""
        return len(text) // CHARS_PER_TOKEN
    
    async def purge_existing_vectors(self) -> int:
        """
        Purge existing vector indexes containing fragmented token chunks.
        
        Deletes:
        - Schema collection for this config
        - Row-level embedding collection for this config (if exists)
        
        Returns:
            Number of collections purged
        """
        purged_count = 0
        
        # Purge schema collection
        try:
            if await self.vector_store.collection_exists():
                old_count = await self.vector_store.get_collection_count()
                await self.vector_store.delete_collection()
                logger.info(f"Purged schema collection '{self.schema_collection_name}' ({old_count} vectors)")
                purged_count += old_count
        except Exception as e:
            logger.warning(f"Failed to purge schema collection: {e}")
        
        # Purge row-level collection (fragmented chunks)
        # Try common naming patterns
        row_collection_patterns = [
            f"agent_*_config_{self.config_id}",
            f"config_{self.config_id}",
            f"embeddings_config_{self.config_id}",
        ]
        
        for pattern in row_collection_patterns:
            try:
                # For exact collection name (not pattern)
                if "*" not in pattern:
                    row_store = get_vector_store(pattern)
                    if await row_store.collection_exists():
                        old_count = await row_store.get_collection_count()
                        await row_store.delete_collection()
                        logger.info(f"Purged row collection '{pattern}' ({old_count} vectors)")
                        purged_count += old_count
            except Exception as e:
                logger.debug(f"Collection '{pattern}' not found or already deleted: {e}")
        
        logger.info(f"Total vectors purged: {purged_count}")
        return purged_count
    
    def _extract_ddl_documents(self) -> List[Dict[str, Any]]:
        """
        Extract DDL documents from the data source.
        
        Uses Phase 2's information_schema extraction for database sources.
        
        Returns:
            List of DDL documents with strict metadata format
        """
        documents = []
        
        if self.db_url:
            logger.info(f"Extracting DDLs from database via information_schema")
            
            # Use Phase 2's direct information_schema extraction
            extractor = DDLExtractor(
                db_url=self.db_url,
                data_dictionary=self.data_dictionary,
            )
            
            try:
                # Get all table schemas
                raw_documents = extractor.extract_all_tables(include_row_counts=True)
                
                # Convert to strict metadata format
                for doc in raw_documents:
                    if doc.get("metadata", {}).get("doc_type") == "ddl_schema":
                        table_name = doc["metadata"].get("table_name", "")
                        fk_deps = doc["metadata"].get("foreign_key_dependencies", [])
                        
                        # Strict metadata format
                        strict_metadata = {
                            "table_name": table_name,
                            "foreign_keys": fk_deps,  # List of referenced table names
                        }
                        
                        documents.append({
                            "id": self._generate_doc_id(table_name),
                            "content": doc["content"],
                            "metadata": strict_metadata,
                        })
                
                # Add relationships overview document
                rel_doc = extractor.extract_relationships_document()
                documents.append({
                    "id": self._generate_doc_id("_relationships"),
                    "content": rel_doc["content"],
                    "metadata": {
                        "table_name": "_relationships",
                        "foreign_keys": [],
                    },
                })
                
                logger.info(f"Extracted {len(documents)} DDL documents")
                
            finally:
                extractor.close()
        
        elif self.duckdb_path and self.duckdb_table_name:
            logger.info(f"Extracting DDL from DuckDB: {self.duckdb_table_name}")
            
            extractor = DuckDBDDLExtractor(
                duckdb_path=self.duckdb_path,
                table_name=self.duckdb_table_name,
                data_dictionary=self.data_dictionary,
            )
            
            try:
                raw_doc = extractor.extract_ddl_document()
                
                # Strict metadata format
                documents.append({
                    "id": self._generate_doc_id(self.duckdb_table_name),
                    "content": raw_doc["content"],
                    "metadata": {
                        "table_name": self.duckdb_table_name,
                        "foreign_keys": [],  # File sources don't have FKs
                    },
                })
                
            finally:
                extractor.close()
        
        else:
            raise ValueError("Either db_url or duckdb_path+duckdb_table_name must be provided")
        
        self._ddl_documents = documents
        return documents
    
    def _generate_doc_id(self, table_name: str) -> str:
        """Generate a stable document ID for a table."""
        key = f"ddl_{self.config_id}_{table_name}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def validate_context_window(self, documents: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, int, int]:
        """
        Validate that the embedding model's context window can handle all DDLs.
        
        Args:
            documents: Optional pre-extracted documents (will extract if None)
        
        Returns:
            Tuple of (is_sufficient, longest_ddl_tokens, model_context_window)
        """
        if documents is None:
            documents = self._ddl_documents or self._extract_ddl_documents()
        
        if not documents:
            return True, 0, self._get_model_context_window()
        
        # Find longest DDL
        longest_chars = max(len(doc["content"]) for doc in documents)
        longest_tokens = self._estimate_tokens(longest_chars)
        model_context = self._get_model_context_window()
        
        is_sufficient = longest_tokens <= model_context
        
        if not is_sufficient:
            logger.warning(
                f"Context window may be insufficient! "
                f"Longest DDL: ~{longest_tokens} tokens, "
                f"Model context: {model_context} tokens"
            )
        else:
            logger.info(
                f"Context window OK: Longest DDL ~{longest_tokens} tokens, "
                f"Model context: {model_context} tokens"
            )
        
        return is_sufficient, longest_tokens, model_context
    
    async def embed_and_upsert_ddls(
        self,
        documents: Optional[List[Dict[str, Any]]] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> int:
        """
        Embed each full DDL string and upsert to vector store.
        
        Args:
            documents: Optional pre-extracted documents
            on_progress: Optional progress callback (current, total, message)
        
        Returns:
            Number of vectors created
        """
        if documents is None:
            documents = self._ddl_documents or self._extract_ddl_documents()
        
        if not documents:
            logger.warning("No DDL documents to embed")
            return 0
        
        # Get embedding function
        if on_progress:
            on_progress(0, len(documents), "Loading embedding model...")
        
        embed_fn = await self._get_embed_fn()
        
        # Extract texts for embedding
        texts = [doc["content"] for doc in documents]
        
        # Generate embeddings
        if on_progress:
            on_progress(1, len(documents), f"Embedding {len(documents)} DDL documents...")
        
        logger.info(f"Generating embeddings for {len(documents)} DDL documents")
        
        if asyncio.iscoroutinefunction(embed_fn):
            embeddings = await embed_fn(texts)
        else:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, embed_fn, texts)
        
        # Prepare data for upsert
        ids = [doc["id"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]
        
        # Log metadata format for verification
        logger.info(f"Upserting with strict metadata format: table_name, foreign_keys")
        for i, meta in enumerate(metadatas[:3]):  # Log first 3 for verification
            logger.debug(f"  {meta['table_name']}: foreign_keys={meta['foreign_keys']}")
        
        # Upsert to vector store
        if on_progress:
            on_progress(len(documents) - 1, len(documents), "Storing vectors...")
        
        await self.vector_store.upsert_batch(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        
        # Verify
        count = await self.vector_store.get_collection_count()
        logger.info(f"Upserted {count} DDL vectors to '{self.schema_collection_name}'")
        
        if on_progress:
            on_progress(len(documents), len(documents), f"Created {count} vectors")
        
        return count
    
    async def migrate(
        self,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> MigrationResult:
        """
        Run the full migration process.
        
        Steps:
        1. Purge existing vector index
        2. Extract DDL documents from information_schema
        3. Validate context window
        4. Embed and upsert DDLs with strict metadata
        
        Args:
            on_progress: Optional progress callback
        
        Returns:
            MigrationResult with details
        """
        start_time = datetime.utcnow()
        errors = []
        
        logger.info(f"Starting schema migration for config {self.config_id}")
        
        # Step 1: Purge existing vectors
        if on_progress:
            on_progress(0, 100, "Purging existing vectors...")
        
        try:
            purged_count = await self.purge_existing_vectors()
        except Exception as e:
            errors.append(f"Purge failed: {str(e)}")
            purged_count = 0
        
        # Step 2: Extract DDL documents
        if on_progress:
            on_progress(20, 100, "Extracting DDL from information_schema...")
        
        try:
            documents = self._extract_ddl_documents()
        except Exception as e:
            errors.append(f"DDL extraction failed: {str(e)}")
            return MigrationResult(
                success=False,
                tables_migrated=0,
                vectors_created=0,
                longest_ddl_chars=0,
                longest_ddl_tokens=0,
                model_context_window=self._get_model_context_window(),
                context_window_sufficient=False,
                purged_old_vectors=purged_count,
                duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
                errors=errors,
            )
        
        if not documents:
            errors.append("No DDL documents extracted")
            return MigrationResult(
                success=False,
                tables_migrated=0,
                vectors_created=0,
                longest_ddl_chars=0,
                longest_ddl_tokens=0,
                model_context_window=self._get_model_context_window(),
                context_window_sufficient=False,
                purged_old_vectors=purged_count,
                duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
                errors=errors,
            )
        
        # Step 3: Validate context window
        if on_progress:
            on_progress(40, 100, "Validating context window...")
        
        longest_chars = max(len(doc["content"]) for doc in documents)
        context_sufficient, longest_tokens, model_context = self.validate_context_window(documents)
        
        if not context_sufficient:
            errors.append(
                f"Context window insufficient: DDL has ~{longest_tokens} tokens, "
                f"model supports {model_context}"
            )
            # Continue anyway with a warning - some models handle overflow gracefully
        
        # Step 4: Embed and upsert
        if on_progress:
            on_progress(50, 100, "Embedding DDL documents...")
        
        try:
            vectors_created = await self.embed_and_upsert_ddls(documents, on_progress=None)
        except Exception as e:
            errors.append(f"Embedding failed: {str(e)}")
            vectors_created = 0
        
        # Calculate tables migrated (exclude _relationships doc)
        tables_migrated = sum(
            1 for doc in documents 
            if doc["metadata"]["table_name"] != "_relationships"
        )
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        if on_progress:
            on_progress(100, 100, f"Migration complete: {tables_migrated} tables")
        
        success = vectors_created > 0 and len(errors) == 0
        
        logger.info(
            f"Migration complete: {tables_migrated} tables, "
            f"{vectors_created} vectors in {duration:.1f}s"
        )
        
        return MigrationResult(
            success=success,
            tables_migrated=tables_migrated,
            vectors_created=vectors_created,
            longest_ddl_chars=longest_chars,
            longest_ddl_tokens=longest_tokens,
            model_context_window=model_context,
            context_window_sufficient=context_sufficient,
            purged_old_vectors=purged_count,
            duration_seconds=duration,
            errors=errors,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

async def migrate_schema_for_config(
    config_id: int,
    db_url: Optional[str] = None,
    duckdb_path: Optional[str] = None,
    duckdb_table_name: Optional[str] = None,
    data_dictionary: Optional[Dict[str, Any]] = None,
    embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> MigrationResult:
    """
    Convenience function to migrate schema for a config.
    
    Args:
        config_id: Agent configuration ID
        db_url: Database URL (for database sources)
        duckdb_path: DuckDB file path (for file sources)
        duckdb_table_name: Table name in DuckDB
        data_dictionary: Optional column descriptions
        embedding_model: Embedding model to use
        on_progress: Optional progress callback
    
    Returns:
        MigrationResult
    """
    migrator = SchemaMigrator(
        config_id=config_id,
        db_url=db_url,
        duckdb_path=duckdb_path,
        duckdb_table_name=duckdb_table_name,
        data_dictionary=data_dictionary,
        embedding_model=embedding_model,
    )
    
    return await migrator.migrate(on_progress=on_progress)


async def migrate_schema_from_agent_config(
    db,  # AsyncSession
    config_id: int,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> MigrationResult:
    """
    Migrate schema using settings from agent_config table.
    
    Args:
        db: Database session
        config_id: Agent configuration ID
        on_progress: Optional progress callback
    
    Returns:
        MigrationResult
    """
    from sqlalchemy import select
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
    
    # Get embedding model
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
    
    # Create migrator based on source type
    if data_source.source_type == "database":
        migrator = SchemaMigrator(
            config_id=config_id,
            db_url=data_source.db_url,
            data_dictionary=data_dictionary,
            embedding_model=embedding_model,
            api_key=api_key,
            api_base_url=api_base_url,
        )
    elif data_source.source_type == "file":
        # Resolve relative duckdb path to absolute
        from app.modules.data_sources.utils import resolve_duckdb_path
        resolved_duckdb_path = str(resolve_duckdb_path(data_source.duckdb_file_path)) if data_source.duckdb_file_path else None
        migrator = SchemaMigrator(
            config_id=config_id,
            duckdb_path=resolved_duckdb_path,
            duckdb_table_name=data_source.duckdb_table_name,
            data_dictionary=data_dictionary,
            embedding_model=embedding_model,
            api_key=api_key,
            api_base_url=api_base_url,
        )
    else:
        raise ValueError(f"Unsupported source type: {data_source.source_type}")
    
    return await migrator.migrate(on_progress=on_progress)


def get_embedding_context_window(model_name: str) -> int:
    """
    Get the context window size for an embedding model.
    
    Args:
        model_name: Embedding model identifier
    
    Returns:
        Context window size in tokens
    """
    model_lower = model_name.lower()
    
    if "/" in model_lower:
        model_lower = model_lower.split("/")[-1]
    
    for known_model, context_window in EMBEDDING_MODEL_CONTEXT_WINDOWS.items():
        if known_model in model_lower:
            return context_window
    
    return EMBEDDING_MODEL_CONTEXT_WINDOWS["default"]
