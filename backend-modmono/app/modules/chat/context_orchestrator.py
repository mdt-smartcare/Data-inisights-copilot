"""
Dynamic Context Orchestrator for SQL Generation.

Phase 4: Retrieval Chain Update
===============================
Fetches top K relevant tables based on semantic intent, then forcefully
retrieves linked schemas via foreign key dependencies.

Multi-Step Retrieval:
1. Semantic Router: Query vector store for top K relevant tables
2. Dependency Resolution: Fetch related tables via foreign key relationships
3. Few-Shot Retrieval: Get similar SQL examples from golden queries
4. Prompt Assembly: Format context as raw CREATE TABLE blocks

Usage:
    from app.modules.chat.context_orchestrator import ContextOrchestrator
    
    orchestrator = ContextOrchestrator(config_id=1, dialect="postgresql")
    
    # Get assembled context for SQL generation
    context = await orchestrator.assemble_context(
        query="Show top 10 patients by visit count",
        max_tables=5,
        max_examples=3,
    )
    
    # Use in prompt
    prompt = context.to_prompt()
"""
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from app.core.utils.logging import get_logger
from app.core.settings import get_settings
from app.core.prompt_templates import (
    build_sql_generation_prompt,
    format_raw_ddl_context,
    get_dialect_rules,
)

logger = get_logger(__name__)


# =============================================================================
# Default Retrieval Settings
# =============================================================================
# These control how many tables are retrieved for SQL generation context
DEFAULT_TOP_K_TABLES = 5  # Number of most relevant tables to retrieve (recommended: 3-5)
DEFAULT_MAX_DEPENDENCIES = 3  # Maximum FK dependency tables to add

# Maximum context token budget (approximate)
MAX_CONTEXT_TOKENS = 8000
TOKENS_PER_CHAR = 0.25  # Rough estimate: 4 chars per token


@dataclass
class TableContext:
    """Context for a single table including DDL and metadata."""
    table_name: str
    ddl: str
    foreign_keys: List[str] = field(default_factory=list)  # Phase 4: strict metadata
    column_count: int = 0
    row_count: Optional[int] = None
    is_primary: bool = False  # Retrieved directly from semantic search
    is_dependency: bool = False  # Retrieved via FK relationship
    relevance_score: float = 0.0
    
    def token_estimate(self) -> int:
        """Estimate token count for this table's DDL."""
        return int(len(self.ddl) * TOKENS_PER_CHAR)
    
    def get_raw_ddl(self) -> str:
        """Extract raw CREATE TABLE statement from enriched DDL."""
        lines = self.ddl.split('\n')
        ddl_lines = []
        in_ddl = False
        
        for line in lines:
            if line.strip().startswith('CREATE TABLE'):
                in_ddl = True
            
            if in_ddl:
                ddl_lines.append(line)
            
            if in_ddl and line.strip().endswith(';'):
                break
        
        return '\n'.join(ddl_lines) if ddl_lines else self.ddl
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for prompt formatting."""
        return {
            "table_name": self.table_name,
            "ddl": self.ddl,
            "foreign_keys": self.foreign_keys,
        }


@dataclass
class FewShotContext:
    """Context for a few-shot SQL example."""
    question: str
    sql: str
    category: str
    description: str
    complexity: str
    relevance_score: float = 0.0
    dialect_hints: List[str] = field(default_factory=list)
    
    def token_estimate(self) -> int:
        """Estimate token count for this example."""
        total = len(self.question) + len(self.sql) + len(self.description)
        return int(total * TOKENS_PER_CHAR)


@dataclass 
class AssembledContext:
    """
    Fully assembled context ready for prompt injection.
    
    Contains all retrieved tables (primary + dependencies) and examples
    organized for optimal SQL generation with raw CREATE TABLE blocks.
    """
    # Core content
    system_instructions: str
    table_contexts: List[TableContext]
    few_shot_examples: List[FewShotContext]
    user_query: str
    
    # Metadata
    config_id: Optional[int] = None
    dialect: str = "postgresql"
    total_tables_available: int = 0
    tables_retrieved: int = 0
    examples_retrieved: int = 0
    token_estimate: int = 0
    assembly_time_ms: float = 0.0
    
    # Relationship info
    relationships_overview: Optional[str] = None
    
    def to_prompt(self) -> str:
        """
        Assemble the final prompt with raw CREATE TABLE blocks.
        
        Phase 4 format:
        1. System Instructions with dialect rules
        2. Raw CREATE TABLE blocks (primary tables first)
        3. FK relationship summary
        4. Golden Few-Shot Examples
        """
        # Separate primary and dependency tables
        primary_tables = [t.to_dict() for t in self.table_contexts if t.is_primary]
        dependency_tables = [t.to_dict() for t in self.table_contexts if t.is_dependency]
        
        # Format DDL context as raw CREATE TABLE blocks
        ddl_context = format_raw_ddl_context(
            primary_tables=primary_tables,
            dependency_tables=dependency_tables,
            query_summary=self.user_query[:50] if self.user_query else "query",
        )
        
        # Format few-shot examples
        few_shot_list = [
            {
                "question": ex.question,
                "sql": ex.sql,
                "category": ex.category,
                "score": ex.relevance_score,
            }
            for ex in self.few_shot_examples
        ]
        
        # Build complete prompt using Phase 4 template
        prompt = build_sql_generation_prompt(
            schema_context=ddl_context,
            dialect=self.dialect,
            few_shot_examples=few_shot_list if few_shot_list else None,
        )
        
        return prompt
    
    def to_messages(self) -> List[Dict[str, str]]:
        """Convert to chat messages format."""
        system_prompt = self.to_prompt()
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.user_query},
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the assembled context."""
        return {
            "tables_retrieved": self.tables_retrieved,
            "primary_tables": sum(1 for t in self.table_contexts if t.is_primary),
            "dependency_tables": sum(1 for t in self.table_contexts if t.is_dependency),
            "examples_retrieved": self.examples_retrieved,
            "total_tables_available": self.total_tables_available,
            "token_estimate": self.token_estimate,
            "assembly_time_ms": self.assembly_time_ms,
            "dialect": self.dialect,
            "fk_relationships": sum(len(t.foreign_keys) for t in self.table_contexts),
        }


class ContextOrchestrator:
    """
    Orchestrates dynamic context assembly for SQL generation.
    
    Phase 4 Implementation:
    - Uses SchemaRetriever for semantic table search
    - Automatic FK dependency resolution
    - Raw CREATE TABLE block formatting
    """
    
    def __init__(
        self,
        config_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        dialect: str = "postgresql",
        db_url: Optional[str] = None,
        embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
        api_key: Optional[str] = None,
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
    ):
        """
        Initialize the context orchestrator.
        
        Args:
            config_id: Agent configuration ID for schema vectors
            agent_id: Agent UUID for fallback collection lookup
            dialect: Target SQL dialect
            db_url: Database URL for live FK inspection (optional)
            embedding_model: Model for semantic search
            api_key: API key for embedding model
            max_context_tokens: Maximum token budget for context
        """
        self.config_id = config_id
        self.agent_id = agent_id
        self.dialect = dialect
        self.db_url = db_url
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.max_context_tokens = max_context_tokens
        self._settings = get_settings()
        
        # Lazy-loaded components
        self._schema_retriever = None
        self._few_shot_engine = None
        self._embed_fn = None
    
    async def _get_schema_retriever(self):
        """Get or create Phase 4 schema retriever."""
        if self._schema_retriever is None:
            from app.modules.embeddings.schema_retriever import SchemaRetriever
            
            self._schema_retriever = SchemaRetriever(
                config_id=self.config_id,
                agent_id=self.agent_id,
                embedding_model=self.embedding_model,
                api_key=self.api_key,
            )
        return self._schema_retriever
    
    async def _get_few_shot_engine(self):
        """Get or create few-shot engine."""
        if self._few_shot_engine is None:
            try:
                from app.modules.sql_examples.few_shot_engine import FewShotEngine
                
                self._few_shot_engine = FewShotEngine(
                    dialect=self.dialect,
                    embedding_model=self.embedding_model,
                    api_key=self.api_key,
                )
            except ImportError:
                logger.warning("FewShotEngine not available")
                self._few_shot_engine = None
        return self._few_shot_engine
    
    async def _retrieve_relevant_tables(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K_TABLES,
        max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
    ) -> Tuple[List[TableContext], List[TableContext]]:
        """
        Phase 4: Retrieve relevant tables with FK dependency resolution.
        
        Steps:
        1. Semantic search for top K relevant tables
        2. Parse foreign_keys from strict metadata
        3. Forcefully retrieve linked schemas
        
        Returns:
            Tuple of (primary_tables, dependency_tables)
        """
        retriever = await self._get_schema_retriever()
        
        try:
            # Use Phase 4 schema retriever with FK resolution
            schema_context = await retriever.retrieve_with_dependencies(
                query=query,
                top_k=top_k,
                max_dependencies=max_dependencies,
            )
            
            # Convert to TableContext objects
            primary_tables = []
            dependency_tables = []
            
            for table in schema_context.tables:
                ctx = TableContext(
                    table_name=table.table_name,
                    ddl=table.ddl,
                    foreign_keys=table.foreign_keys,
                    is_primary=table.is_primary,
                    is_dependency=table.is_dependency,
                    relevance_score=table.score,
                )
                
                if table.is_primary:
                    primary_tables.append(ctx)
                else:
                    dependency_tables.append(ctx)
            
            logger.info(
                f"Retrieved {len(primary_tables)} primary + "
                f"{len(dependency_tables)} dependency tables"
            )
            
            return primary_tables, dependency_tables
            
        except Exception as e:
            logger.warning(f"Schema retrieval failed: {e}")
            return [], []
    
    async def _retrieve_few_shot_examples(
        self,
        query: str,
        top_k: int = 3,
        category_hint: Optional[str] = None,
    ) -> List[FewShotContext]:
        """
        Retrieve similar SQL examples for few-shot prompting.
        """
        engine = await self._get_few_shot_engine()
        
        if engine is None:
            return []
        
        try:
            examples = await engine.get_few_shot_examples(
                query=query,
                top_k=top_k,
                category_filter=category_hint,
                min_score=0.3,
            )
            
            few_shot_contexts = []
            for ex in examples:
                ctx = FewShotContext(
                    question=ex.question,
                    sql=ex.sql,
                    category=ex.category,
                    description=getattr(ex, 'description', ''),
                    complexity=getattr(ex, 'complexity', 'medium'),
                    relevance_score=ex.score,
                )
                few_shot_contexts.append(ctx)
            
            logger.info(f"Retrieved {len(few_shot_contexts)} few-shot examples")
            return few_shot_contexts
            
        except Exception as e:
            logger.warning(f"Few-shot retrieval failed: {e}")
            return []
    
    def _get_system_instructions(self) -> str:
        """Get base system instructions (dialect rules handled by template)."""
        return get_dialect_rules(self.dialect)
    
    def _estimate_tokens(
        self,
        table_contexts: List[TableContext],
        few_shot_examples: List[FewShotContext],
        query: str,
    ) -> int:
        """Estimate total token count for the context."""
        total = 1000  # Base system instructions
        total += sum(t.token_estimate() for t in table_contexts)
        total += sum(e.token_estimate() for e in few_shot_examples)
        total += int(len(query) * TOKENS_PER_CHAR)
        total += 500  # Buffer for formatting
        return int(total)
    
    def _trim_to_budget(
        self,
        primary_tables: List[TableContext],
        dependency_tables: List[TableContext],
        few_shot_examples: List[FewShotContext],
        query: str,
    ) -> Tuple[List[TableContext], List[FewShotContext]]:
        """
        Trim context to fit within token budget.
        
        Priority (highest to lowest):
        1. Primary tables (by relevance score)
        2. Few-shot examples (by relevance score)
        3. Dependency tables (for JOIN paths)
        """
        budget = self.max_context_tokens
        used = 1500  # Base instructions + buffer
        used += int(len(query) * TOKENS_PER_CHAR)
        
        remaining = budget - used
        
        # Sort by relevance
        primary_tables = sorted(primary_tables, key=lambda t: -t.relevance_score)
        dependency_tables = sorted(dependency_tables, key=lambda t: -t.relevance_score)
        few_shot_examples = sorted(few_shot_examples, key=lambda e: -e.relevance_score)
        
        final_tables = []
        final_examples = []
        
        # 1. Add primary tables (50% of budget)
        primary_budget = remaining * 0.5
        for table in primary_tables:
            tokens = table.token_estimate()
            if primary_budget >= tokens:
                final_tables.append(table)
                primary_budget -= tokens
                remaining -= tokens
        
        # 2. Add few-shot examples (25% of budget)
        example_budget = (budget - used) * 0.25
        for example in few_shot_examples:
            tokens = example.token_estimate()
            if example_budget >= tokens:
                final_examples.append(example)
                example_budget -= tokens
                remaining -= tokens
        
        # 3. Add dependency tables (remaining budget)
        for table in dependency_tables:
            tokens = table.token_estimate()
            if remaining >= tokens:
                final_tables.append(table)
                remaining -= tokens
        
        return final_tables, final_examples
    
    async def assemble_context(
        self,
        query: str,
        max_tables: int = DEFAULT_TOP_K_TABLES,
        max_dependencies: int = DEFAULT_MAX_DEPENDENCIES,
        max_examples: int = 3,
        category_hint: Optional[str] = None,
    ) -> AssembledContext:
        """
        Assemble complete context for SQL generation.
        
        Phase 4 Pipeline:
        1. Semantic search for relevant tables
        2. FK dependency resolution (forcefully retrieve linked schemas)
        3. Few-shot example retrieval
        4. Format as raw CREATE TABLE blocks
        
        Args:
            query: User's natural language question
            max_tables: Maximum primary tables to retrieve
            max_dependencies: Maximum FK dependencies to add
            max_examples: Maximum few-shot examples
            category_hint: Optional category for few-shot filtering
        
        Returns:
            AssembledContext with raw DDL blocks ready for LLM
        """
        start_time = datetime.now()
        
        # Run retrieval steps in parallel
        table_task = asyncio.create_task(
            self._retrieve_relevant_tables(query, top_k=max_tables, max_dependencies=max_dependencies)
        )
        example_task = asyncio.create_task(
            self._retrieve_few_shot_examples(query, top_k=max_examples, category_hint=category_hint)
        )
        
        # Wait for retrievals
        (primary_tables, dependency_tables), few_shot_examples = await asyncio.gather(
            table_task, example_task
        )
        
        # Trim to budget
        all_tables, final_examples = self._trim_to_budget(
            primary_tables, dependency_tables, few_shot_examples, query
        )
        
        # Get system instructions
        system_instructions = self._get_system_instructions()
        
        # Calculate token estimate
        token_estimate = self._estimate_tokens(all_tables, final_examples, query)
        
        # Calculate assembly time
        assembly_time = (datetime.now() - start_time).total_seconds() * 1000
        
        context = AssembledContext(
            system_instructions=system_instructions,
            table_contexts=all_tables,
            few_shot_examples=final_examples,
            user_query=query,
            config_id=self.config_id,
            dialect=self.dialect,
            total_tables_available=len(primary_tables) + len(dependency_tables),
            tables_retrieved=len(all_tables),
            examples_retrieved=len(final_examples),
            token_estimate=token_estimate,
            assembly_time_ms=assembly_time,
        )
        
        logger.info(
            f"Context assembled: {len(all_tables)} tables "
            f"({sum(1 for t in all_tables if t.is_primary)} primary, "
            f"{sum(1 for t in all_tables if t.is_dependency)} deps), "
            f"{len(final_examples)} examples, ~{token_estimate} tokens, {assembly_time:.1f}ms"
        )
        
        return context
    
    async def get_context_for_sql_generation(
        self,
        query: str,
        max_tables: int = DEFAULT_TOP_K_TABLES,
        max_examples: int = 3,
    ) -> str:
        """
        Convenience method to get assembled context as a prompt string.
        
        Args:
            query: User's natural language question
            max_tables: Maximum tables to include
            max_examples: Maximum few-shot examples
        
        Returns:
            Complete prompt string ready for LLM
        """
        context = await self.assemble_context(
            query=query,
            max_tables=max_tables,
            max_examples=max_examples,
        )
        return context.to_prompt()


async def get_orchestrated_context(
    query: str,
    config_id: Optional[int] = None,
    dialect: str = "postgresql",
    max_tables: int = DEFAULT_TOP_K_TABLES,
    max_examples: int = 3,
    embedding_model: str = "huggingface/BAAI/bge-base-en-v1.5",
    api_key: Optional[str] = None,
) -> AssembledContext:
    """
    Convenience function to get orchestrated context for SQL generation.
    
    This is the main entry point for integrating dynamic context
    orchestration into the SQL generation pipeline.
    
    Args:
        query: User's natural language question
        config_id: Agent configuration ID
        dialect: Target SQL dialect
        max_tables: Maximum tables to retrieve
        max_examples: Maximum few-shot examples
        embedding_model: Embedding model name
        api_key: API key for embedding model
    
    Returns:
        AssembledContext with all necessary context
    """
    orchestrator = ContextOrchestrator(
        config_id=config_id,
        dialect=dialect,
        embedding_model=embedding_model,
        api_key=api_key,
    )
    
    return await orchestrator.assemble_context(
        query=query,
        max_tables=max_tables,
        max_examples=max_examples,
    )


async def get_sql_generation_prompt(
    query: str,
    config_id: Optional[int] = None,
    dialect: str = "postgresql",
    max_tables: int = DEFAULT_TOP_K_TABLES,
    max_examples: int = 3,
) -> Tuple[str, Dict[str, Any]]:
    """
    Get complete prompt for SQL generation with context stats.
    
    Returns:
        Tuple of (prompt_string, stats_dict)
    """
    context = await get_orchestrated_context(
        query=query,
        config_id=config_id,
        dialect=dialect,
        max_tables=max_tables,
        max_examples=max_examples,
    )
    
    return context.to_prompt(), context.get_stats()
