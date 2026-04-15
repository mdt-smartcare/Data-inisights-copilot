"""
Schema Retriever for SQL Generation Context.

Phase 4: Retrieval Chain Update
===============================
Fetches top K relevant tables based on semantic intent, then forcefully
retrieves linked schemas via foreign key dependencies.

Key Features:
- Semantic search for relevant tables based on user query
- FK dependency resolution: automatically fetch referenced tables
- Strict metadata format: {"table_name": str, "foreign_keys": list[str]}
- Raw CREATE TABLE block formatting for LLM context

Usage:
    from app.modules.embeddings.schema_retriever import SchemaRetriever
    
    retriever = SchemaRetriever(config_id=123)
    
    # Get relevant schemas with FK resolution
    context = await retriever.retrieve_with_dependencies(
        query="Show orders with customer names",
        top_k=5,
    )
    
    # Format as raw DDL blocks for LLM
    ddl_context = context.to_raw_ddl_blocks()
"""
import asyncio
import json
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime

from app.core.utils.logging import get_logger
from app.modules.embeddings.vector_stores.factory import get_vector_store
from app.modules.embeddings.service import _get_embedding_provider

logger = get_logger(__name__)


SCHEMA_COLLECTION_PREFIX = "schema_config_"

# =============================================================================
# Default Retrieval Settings
# =============================================================================
# Adjust these constants to control how many tables are retrieved for context
DEFAULT_TOP_K_TABLES = 5  # Number of most relevant tables to retrieve (recommended: 3-5)
DEFAULT_MAX_DEPENDENCIES = 3  # Maximum FK dependency tables to add


@dataclass
class RetrievedTable:
    """A retrieved table schema with metadata."""
    table_name: str
    ddl: str
    foreign_keys: List[str]  # Tables this table references
    score: float = 0.0
    is_primary: bool = True  # Retrieved via semantic search
    is_dependency: bool = False  # Retrieved via FK resolution
    
    def get_raw_ddl(self) -> str:
        """
        Extract raw CREATE TABLE statement from enriched DDL.
        
        Strips comment headers but preserves inline column comments.
        """
        lines = self.ddl.split('\n')
        ddl_lines = []
        in_ddl = False
        
        for line in lines:
            # Start capturing at CREATE TABLE
            if line.strip().startswith('CREATE TABLE'):
                in_ddl = True
            
            if in_ddl:
                ddl_lines.append(line)
            
            # Stop at closing semicolon
            if in_ddl and line.strip().endswith(';'):
                break
        
        if ddl_lines:
            return '\n'.join(ddl_lines)
        
        # Fallback: return original if no CREATE TABLE found
        return self.ddl


@dataclass
class SchemaContext:
    """
    Complete schema context for SQL generation.
    
    Contains all retrieved tables (primary + dependencies) organized
    for optimal LLM prompt injection.
    """
    tables: List[RetrievedTable]
    query: str
    config_id: int
    
    # Retrieval stats
    primary_count: int = 0
    dependency_count: int = 0
    total_fk_relationships: int = 0
    retrieval_time_ms: float = 0.0
    
    def get_primary_tables(self) -> List[RetrievedTable]:
        """Get tables retrieved via semantic search."""
        return [t for t in self.tables if t.is_primary]
    
    def get_dependency_tables(self) -> List[RetrievedTable]:
        """Get tables retrieved via FK resolution."""
        return [t for t in self.tables if t.is_dependency]
    
    def to_raw_ddl_blocks(self) -> str:
        """
        Format all schemas as raw CREATE TABLE blocks.
        
        This is the format expected by the LLM for SQL generation.
        Primary tables are listed first, then dependencies.
        
        Returns:
            Formatted DDL context string with clear section headers
        """
        sections = []
        
        # Header
        sections.append("-- ============================================")
        sections.append("-- DATABASE SCHEMA CONTEXT")
        sections.append(f"-- Retrieved {len(self.tables)} tables for query")
        sections.append("-- ============================================")
        sections.append("")
        
        # Primary tables (most relevant)
        primary = self.get_primary_tables()
        if primary:
            sections.append("-- PRIMARY TABLES (directly relevant to query)")
            sections.append("")
            
            for table in sorted(primary, key=lambda t: -t.score):
                sections.append(table.get_raw_ddl())
                
                # Add FK info as comment
                if table.foreign_keys:
                    fk_list = ", ".join(table.foreign_keys)
                    sections.append(f"-- References: {fk_list}")
                
                sections.append("")
        
        # Dependency tables (for JOIN paths)
        dependencies = self.get_dependency_tables()
        if dependencies:
            sections.append("-- RELATED TABLES (for JOIN paths)")
            sections.append("")
            
            for table in dependencies:
                sections.append(table.get_raw_ddl())
                
                if table.foreign_keys:
                    fk_list = ", ".join(table.foreign_keys)
                    sections.append(f"-- References: {fk_list}")
                
                sections.append("")
        
        # Relationship summary
        if self.total_fk_relationships > 0:
            sections.append("-- ============================================")
            sections.append("-- FOREIGN KEY RELATIONSHIPS")
            sections.append("-- ============================================")
            
            for table in self.tables:
                if table.foreign_keys:
                    for fk in table.foreign_keys:
                        sections.append(f"-- {table.table_name} -> {fk}")
            
            sections.append("") 
        
        return "\n".join(sections)
    
    def to_compact_ddl(self) -> str:
        """
        Format schemas in a more compact form for smaller context windows.
        
        Strips all comments except essential FK info.
        """
        ddl_parts = []
        
        for table in self.tables:
            raw_ddl = table.get_raw_ddl()
            
            # Strip inline comments for compactness
            lines = []
            for line in raw_ddl.split('\n'):
                # Remove inline comments but keep the code
                if '--' in line:
                    line = line.split('--')[0].rstrip()
                if line.strip():
                    lines.append(line)
            
            if lines:
                ddl_parts.append('\n'.join(lines))
        
        return '\n\n'.join(ddl_parts)
    
    def get_table_names(self) -> List[str]:
        """Get list of all table names in context."""
        return [t.table_name for t in self.tables]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get retrieval statistics."""
        return {
            "total_tables": len(self.tables),
            "primary_tables": self.primary_count,
            "dependency_tables": self.dependency_count,
            "fk_relationships": self.total_fk_relationships,
            "retrieval_time_ms": self.retrieval_time_ms,
            "table_names": self.get_table_names(),
        }


class SchemaRetriever:
    """
    Retrieves relevant database schemas for SQL generation.
    
    Implements Phase 4 retrieval chain:
    1. Semantic search for top K relevant tables
    2. FK dependency resolution to ensure JOIN paths
    3. Format as raw CREATE TABLE blocks for LLM
    """
    
    def __init__(
        self,
        config_id: int,
        agent_id: Optional[str] = None,
        embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
    ):
        """
        Initialize the schema retriever.
        
        Args:
            config_id: Agent configuration ID
            agent_id: Agent UUID (for fallback collection lookup)
            embedding_model: Embedding model for semantic search
            api_key: API key for embedding model
            api_base_url: API base URL for embedding model
        """
        self.config_id = config_id
        self.agent_id = agent_id
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.api_base_url = api_base_url
        
        # Primary collection name (schema-specific)
        self.collection_name = f"{SCHEMA_COLLECTION_PREFIX}{config_id}"
        
        # Fallback collection name (main agent collection from embedding job)
        self._fallback_collection_name = f"agent_{agent_id}_config_{config_id}" if agent_id else None
        
        # Lazy-loaded components
        self._vector_store = None
        self._embed_fn = None
        self._initialized_store = False
        
        # Cache for retrieved DDLs (table_name -> ddl)
        self._ddl_cache: Dict[str, str] = {}
        self._fk_cache: Dict[str, List[str]] = {}
    
    @property
    def vector_store(self):
        """Get or create vector store instance."""
        if self._vector_store is None:
            self._vector_store = get_vector_store(self.collection_name)
        return self._vector_store
    
    async def _get_embed_fn(self):
        """Get or initialize embedding function."""
        if self._embed_fn is None:
            self._embed_fn = await _get_embedding_provider(
                self.embedding_model,
                self.api_key,
                self.api_base_url,
            )
        return self._embed_fn
    
    async def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for query."""
        embed_fn = await self._get_embed_fn()
        
        if asyncio.iscoroutinefunction(embed_fn):
            embeddings = await embed_fn([query])
        else:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, embed_fn, [query])
        
        return embeddings[0]
    
    async def _ensure_vector_store(self):
        """Ensure we have a valid vector store, checking fallback if needed."""
        if self._initialized_store:
            return
        
        # Check primary collection first
        if await self.vector_store.collection_exists():
            count = await self.vector_store.get_collection_count()
            if count > 0:
                logger.info(f"Using primary schema collection: {self.collection_name} ({count} vectors)")
                self._initialized_store = True
                return
        
        # Try fallback collection (main agent collection from embedding job)
        if self._fallback_collection_name:
            fallback_store = get_vector_store(self._fallback_collection_name)
            if await fallback_store.collection_exists():
                count = await fallback_store.get_collection_count()
                if count > 0:
                    logger.info(f"Using fallback agent collection: {self._fallback_collection_name} ({count} vectors)")
                    self._vector_store = fallback_store
                    self.collection_name = self._fallback_collection_name
                    self._initialized_store = True
                    return
        
        # Try to find collection from agent_config.vector_collection_name
        try:
            from app.modules.agents.models import AgentConfigModel
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy import select
            from app.core.config import get_settings
            
            settings = get_settings()
            db_url = f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
            
            engine = create_async_engine(db_url, echo=False)
            async with AsyncSession(engine) as session:
                stmt = select(AgentConfigModel).where(AgentConfigModel.id == self.config_id)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()
                
                if config and config.vector_collection_name:
                    collection_name = config.vector_collection_name
                    db_store = get_vector_store(collection_name)
                    if await db_store.collection_exists():
                        count = await db_store.get_collection_count()
                        if count > 0:
                            logger.info(f"Using configured collection from DB: {collection_name} ({count} vectors)")
                            self._vector_store = db_store
                            self.collection_name = collection_name
                            self._initialized_store = True
                            await engine.dispose()
                            return
            
            await engine.dispose()
        except Exception as e:
            logger.debug(f"Could not lookup collection from DB: {e}")
        
        self._initialized_store = True  # Mark as initialized even if empty
        logger.warning(f"No schema collection found for config {self.config_id}")
    
    async def retrieve_tables(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K_TABLES,
    ) -> List[RetrievedTable]:
        """
        Retrieve top K relevant tables via semantic search.
        
        Uses the Phase 3 strict metadata format:
        {"table_name": str, "foreign_keys": list[str]}
        
        Args:
            query: User's natural language query
            top_k: Number of tables to retrieve
        
        Returns:
            List of RetrievedTable with DDL and FK metadata
        """
        # Ensure we have a valid vector store (with fallback logic)
        await self._ensure_vector_store()
        
        # Check if collection exists
        if not await self.vector_store.collection_exists():
            logger.warning(f"Schema collection not found: {self.collection_name}")
            return []
        
        # Generate query embedding
        query_embedding = await self._embed_query(query)
        
        # Search vector store
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k + 1,  # +1 to account for potential _relationships doc
        )
        
        tables = []
        for result in results:
            metadata = result.get("metadata", {})
            table_name = metadata.get("table_name", "")
            
            # Skip relationships overview document
            if table_name == "_relationships":
                continue
            
            # Parse foreign_keys from strict metadata
            foreign_keys = metadata.get("foreign_keys", [])
            if isinstance(foreign_keys, str):
                try:
                    foreign_keys = json.loads(foreign_keys)
                except (json.JSONDecodeError, ValueError):
                    foreign_keys = []
            
            ddl = result.get("document", "")
            score = result.get("score", 0.0)
            
            table = RetrievedTable(
                table_name=table_name,
                ddl=ddl,
                foreign_keys=foreign_keys,
                score=score,
                is_primary=True,
                is_dependency=False,
            )
            
            tables.append(table)
            
            # Cache for dependency resolution
            self._ddl_cache[table_name] = ddl
            self._fk_cache[table_name] = foreign_keys
        
        logger.info(f"Retrieved {len(tables)} tables for query: {query[:50]}...")
        return tables[:top_k]
    
    async def resolve_fk_dependencies(
        self,
        primary_tables: List[RetrievedTable],
        max_depth: int = 1,
        max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
        include_reverse_fks: bool = True,
    ) -> List[RetrievedTable]:
        """
        Resolve FK dependencies for retrieved tables (both directions).
        
        This method handles TWO types of FK relationships:
        1. Outgoing FKs: Tables that primary tables reference (e.g., orders -> customers)
        2. Incoming FKs: Tables that reference primary tables (e.g., encounters -> patients)
        
        This ensures that if "patients" is retrieved, "encounters" (which has FK to patients)
        is also fetched to enable proper JOIN paths.
        
        Args:
            primary_tables: Tables from semantic search
            max_depth: How many levels of FK to follow (1 = direct only)
            max_dependencies: Maximum dependency tables to add
            include_reverse_fks: Also fetch tables that reference the primary tables
        
        Returns:
            List of dependency tables (not including primary)
        """
        if not primary_tables:
            return []
        
        # Collect all FK references (outgoing)
        primary_names = {t.table_name for t in primary_tables}
        needed_tables: Set[str] = set()
        
        # 1. Outgoing FKs: Tables that primary tables reference
        for table in primary_tables:
            for fk_table in table.foreign_keys:
                if fk_table and fk_table not in primary_names:
                    needed_tables.add(fk_table)
        
        # 2. Incoming FKs: Tables that reference primary tables (reverse lookup)
        # This ensures we get tables like "encounters" when "patients" is retrieved
        if include_reverse_fks:
            reverse_fk_tables = await self._find_tables_referencing(primary_names)
            for table_name in reverse_fk_tables:
                if table_name not in primary_names:
                    needed_tables.add(table_name)
        
        if not needed_tables:
            logger.debug("No FK dependencies to resolve")
            return []
        
        # Limit to prevent context overflow
        needed_list = list(needed_tables)[:max_dependencies]
        
        logger.info(f"Resolving {len(needed_list)} FK dependencies: {needed_list}")
        
        # Fetch dependency DDLs
        dependencies = []
        
        for table_name in needed_list:
            # Check cache first
            if table_name in self._ddl_cache:
                ddl = self._ddl_cache[table_name]
                foreign_keys = self._fk_cache.get(table_name, [])
            else:
                # Fetch from vector store by table name
                ddl, foreign_keys = await self._fetch_table_by_name(table_name)
            
            if ddl:
                dep = RetrievedTable(
                    table_name=table_name,
                    ddl=ddl,
                    foreign_keys=foreign_keys,
                    score=0.5,  # Lower than primary
                    is_primary=False,
                    is_dependency=True,
                )
                dependencies.append(dep)
                
                # Cache for potential deeper resolution
                self._ddl_cache[table_name] = ddl
                self._fk_cache[table_name] = foreign_keys
        
        # Optionally resolve second-level dependencies (only outgoing, no reverse)
        if max_depth > 1 and dependencies:
            second_level = await self.resolve_fk_dependencies(
                dependencies,
                max_depth=max_depth - 1,
                max_dependencies=max_dependencies - len(dependencies),
                include_reverse_fks=False,  # Don't recurse reverse FKs to avoid explosion
            )
            dependencies.extend(second_level)
        
        return dependencies
    
    async def _find_tables_referencing(self, target_tables: Set[str]) -> List[str]:
        """
        Find tables that have foreign keys pointing TO the target tables.
        
        This is a reverse FK lookup - if we have "patients", find tables
        like "encounters" that have FK references to "patients".
        
        Args:
            target_tables: Set of table names to find references to
        
        Returns:
            List of table names that reference any of the target tables
        """
        referencing_tables = []
        
        try:
            # Search for all schema documents and check their FK metadata
            # Use a generic query to get candidate tables
            query_embedding = await self._embed_query("table schema foreign key references")
            
            results = await self.vector_store.search(
                query_embedding=query_embedding,
                top_k=20,  # Get more results to scan for reverse FKs
            )
            
            for result in results:
                metadata = result.get("metadata", {})
                table_name = metadata.get("table_name", "")
                
                # Skip if already in targets or is the relationships doc
                if table_name in target_tables or table_name == "_relationships":
                    continue
                
                # Check if this table's foreign_keys include any of our target tables
                foreign_keys = metadata.get("foreign_keys", [])
                if isinstance(foreign_keys, str):
                    try:
                        foreign_keys = json.loads(foreign_keys)
                    except (json.JSONDecodeError, ValueError):
                        foreign_keys = []
                
                # If this table references any of our target tables, include it
                for fk_target in foreign_keys:
                    if fk_target in target_tables:
                        referencing_tables.append(table_name)
                        # Cache for later use
                        self._ddl_cache[table_name] = result.get("document", "")
                        self._fk_cache[table_name] = foreign_keys
                        break  # Only add once
            
            if referencing_tables:
                logger.info(f"Found {len(referencing_tables)} tables referencing {target_tables}: {referencing_tables}")
            
        except Exception as e:
            logger.warning(f"Failed to find reverse FK references: {e}")
        
        return referencing_tables
    
    async def _fetch_table_by_name(self, table_name: str) -> Tuple[str, List[str]]:
        """
        Fetch a specific table's DDL by name.
        
        Uses semantic search with table name as query.
        
        Returns:
            Tuple of (ddl_string, foreign_keys_list)
        """
        try:
            # Search for the specific table
            query_embedding = await self._embed_query(f"table {table_name}")
            
            results = await self.vector_store.search(
                query_embedding=query_embedding,
                top_k=5,  # Search a few in case of similar names
            )
            
            for result in results:
                metadata = result.get("metadata", {})
                if metadata.get("table_name") == table_name:
                    ddl = result.get("document", "")
                    foreign_keys = metadata.get("foreign_keys", [])
                    
                    if isinstance(foreign_keys, str):
                        try:
                            foreign_keys = json.loads(foreign_keys)
                        except (json.JSONDecodeError, ValueError):
                            foreign_keys = []
                    
                    return ddl, foreign_keys
            
            logger.warning(f"Table {table_name} not found in schema vectors")
            return "", []
            
        except Exception as e:
            logger.error(f"Failed to fetch table {table_name}: {e}")
            return "", []
    
    async def retrieve_with_dependencies(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K_TABLES,
        max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
        resolve_depth: int = 1,
    ) -> SchemaContext:
        """
        Full retrieval pipeline with FK dependency resolution.
        
        This is the main entry point for the Phase 4 retrieval chain:
        1. Semantic search for top K relevant tables
        2. Parse foreign_keys from strict metadata
        3. Forcefully retrieve linked schemas
        4. Return organized SchemaContext
        
        Args:
            query: User's natural language query
            top_k: Number of primary tables to retrieve
            max_dependencies: Maximum FK dependencies to add
            resolve_depth: Levels of FK relationships to follow
        
        Returns:
            SchemaContext with all tables ready for prompt injection
        """
        start_time = datetime.now()
        
        # Step 1: Semantic search for primary tables
        primary_tables = await self.retrieve_tables(query, top_k=top_k)
        
        # Step 2: Resolve FK dependencies
        dependency_tables = await self.resolve_fk_dependencies(
            primary_tables,
            max_depth=resolve_depth,
            max_dependencies=max_dependencies,
        )
        
        # Combine all tables
        all_tables = primary_tables + dependency_tables
        
        # Calculate FK relationship count
        total_fks = sum(len(t.foreign_keys) for t in all_tables)
        
        # Calculate retrieval time
        retrieval_time = (datetime.now() - start_time).total_seconds() * 1000
        
        context = SchemaContext(
            tables=all_tables,
            query=query,
            config_id=self.config_id,
            primary_count=len(primary_tables),
            dependency_count=len(dependency_tables),
            total_fk_relationships=total_fks,
            retrieval_time_ms=retrieval_time,
        )
        
        logger.info(
            f"Schema retrieval complete: {len(primary_tables)} primary + "
            f"{len(dependency_tables)} dependencies in {retrieval_time:.1f}ms"
        )
        
        return context
    
    def clear_cache(self):
        """Clear internal caches."""
        self._ddl_cache.clear()
        self._fk_cache.clear()


# =============================================================================
# Convenience Functions
# =============================================================================

async def retrieve_schema_context(
    query: str,
    config_id: int,
    agent_id: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K_TABLES,
    max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
    embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
    api_key: Optional[str] = None,
) -> SchemaContext:
    """
    Convenience function to retrieve schema context for SQL generation.
    
    Args:
        query: User's natural language query
        config_id: Agent configuration ID
        agent_id: Agent UUID for fallback collection lookup
        top_k: Number of primary tables
        max_dependencies: Maximum FK dependencies
        embedding_model: Embedding model name
        api_key: API key for embedding model
    
    Returns:
        SchemaContext with tables and DDL blocks
    """
    retriever = SchemaRetriever(
        config_id=config_id,
        agent_id=agent_id,
        embedding_model=embedding_model,
        api_key=api_key,
    )
    
    return await retriever.retrieve_with_dependencies(
        query=query,
        top_k=top_k,
        max_dependencies=max_dependencies,
    )


async def get_ddl_context_for_sql(
    query: str,
    config_id: int,
    agent_id: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K_TABLES,
    compact: bool = False,
) -> str:
    """
    Get formatted DDL context string for SQL generation prompt.
    
    This is the main entry point for injecting schema context
    into the LLM system prompt.
    
    Args:
        query: User's natural language query
        config_id: Agent configuration ID
        agent_id: Agent UUID for fallback collection lookup
        top_k: Number of tables to retrieve
        compact: Use compact format for smaller context windows
    
    Returns:
        Formatted DDL context string ready for prompt injection
    """
    context = await retrieve_schema_context(
        query=query,
        config_id=config_id,
        agent_id=agent_id,
        top_k=top_k,
    )
    
    if compact:
        return context.to_compact_ddl()
    
    return context.to_raw_ddl_blocks()
