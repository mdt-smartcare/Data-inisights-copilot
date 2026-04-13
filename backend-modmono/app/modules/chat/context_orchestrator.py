"""
Dynamic Context Orchestrator for SQL Generation.

Phase 3: Dynamic Context Orchestration
======================================
Prevents context window overflow and hallucination by injecting only the
necessary schemas and examples for a given user query.

Multi-Step Retrieval:
1. Semantic Router: Query vector store for top K relevant tables
2. Dependency Resolution: Fetch related tables via foreign key relationships
3. Few-Shot Retrieval: Get similar SQL examples from golden queries
4. Prompt Assembly: Construct prompt in strict order:
   - System Instructions
   - Retrieved DDLs
   - Golden Few-Shot Examples
   - User Question

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
import json
import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime


from app.core.utils.logging import get_logger
from app.core.settings import get_settings
from app.core.prompts import get_sql_generator_prompt

logger = get_logger(__name__)


# Maximum context token budget (approximate)
MAX_CONTEXT_TOKENS = 8000
TOKENS_PER_CHAR = 0.25  # Rough estimate: 4 chars per token


@dataclass
class TableContext:
    """Context for a single table including DDL and metadata."""
    table_name: str
    ddl: str
    column_count: int
    row_count: Optional[int] = None
    is_primary: bool = False  # Retrieved directly from semantic search
    is_dependency: bool = False  # Retrieved via FK relationship
    relevance_score: float = 0.0
    foreign_key_to: List[str] = field(default_factory=list)
    foreign_key_from: List[str] = field(default_factory=list)
    
    def token_estimate(self) -> int:
        """Estimate token count for this table's DDL."""
        return int(len(self.ddl) * TOKENS_PER_CHAR)


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
    
    Contains all retrieved tables, examples, and metadata organized
    in the correct order for optimal SQL generation.
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
        Assemble the final prompt in strict order:
        1. System Instructions
        2. Retrieved DDLs
        3. Golden Few-Shot Examples
        4. User Question
        """
        sections = []
        
        # 1. System Instructions
        sections.append(self.system_instructions)
        
        # 2. Retrieved DDLs (Schema Context)
        if self.table_contexts:
            sections.append("\n## Database Schema\n")
            sections.append("The following tables are relevant to your query:\n")
            
            # Sort: primary tables first, then dependencies
            sorted_tables = sorted(
                self.table_contexts,
                key=lambda t: (not t.is_primary, -t.relevance_score)
            )
            
            for table_ctx in sorted_tables:
                sections.append(table_ctx.ddl)
                sections.append("")  # Empty line between tables
            
            # Add relationships overview if available
            if self.relationships_overview:
                sections.append("\n### Table Relationships")
                sections.append(self.relationships_overview)
        
        # 3. Golden Few-Shot Examples
        if self.few_shot_examples:
            sections.append("\n## Similar SQL Examples (Few-Shot Learning)\n")
            sections.append("Use these verified examples as reference for SQL patterns:\n")
            
            for i, ex in enumerate(self.few_shot_examples, 1):
                sections.append(f"### Example {i}")
                sections.append(f"**Question:** {ex.question}")
                if ex.description:
                    sections.append(f"**Pattern:** {ex.description}")
                sections.append("**SQL:**")
                sections.append("```sql")
                sections.append(ex.sql)
                sections.append("```")
                
                if ex.dialect_hints:
                    sections.append(f"**{self.dialect.upper()} Notes:**")
                    for hint in ex.dialect_hints:
                        sections.append(f"- {hint}")
                
                sections.append("")
        
        # 4. User Question (added by the calling code, not here)
        # The user question is typically added in the message, not system prompt
        
        return "\n".join(sections)
    
    def to_messages(self) -> List[Dict[str, str]]:
        """
        Convert to chat messages format.
        
        Returns list of message dicts ready for LLM API.
        """
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
        }


class ContextOrchestrator:
    """
    Orchestrates dynamic context assembly for SQL generation.
    
    Implements multi-step retrieval to gather only the necessary
    context for a given query, preventing context overflow.
    """
    
    def __init__(
        self,
        config_id: Optional[int] = None,
        dialect: str = "postgresql",
        db_url: Optional[str] = None,
        embedding_model: str = "huggingface/BAAI/bge-large-en-v1.5",
        api_key: Optional[str] = None,
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
    ):
        """
        Initialize the context orchestrator.
        
        Args:
            config_id: Agent configuration ID for schema vectors
            dialect: Target SQL dialect
            db_url: Database URL for live FK inspection (optional)
            embedding_model: Model for semantic search
            api_key: API key for embedding model
            max_context_tokens: Maximum token budget for context
        """
        self.config_id = config_id
        self.dialect = dialect
        self.db_url = db_url
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.max_context_tokens = max_context_tokens
        self._settings = get_settings()
        
        # Lazy-loaded components
        self._schema_vectorizer = None
        self._few_shot_engine = None
        self._embed_fn = None
        
        # Cache for FK relationships (table_name -> list of related tables)
        self._fk_cache: Dict[str, List[str]] = {}
        self._reverse_fk_cache: Dict[str, List[str]] = {}
    
    async def _get_schema_vectorizer(self):
        """Get or create schema vectorizer."""
        if self._schema_vectorizer is None:
            from app.modules.embeddings.schema_vectorizer import SchemaVectorizer
            
            self._schema_vectorizer = SchemaVectorizer(
                config_id=self.config_id,
                db_url=self.db_url,
                embedding_model=self.embedding_model,
                api_key=self.api_key,
            )
        return self._schema_vectorizer
    
    async def _get_few_shot_engine(self):
        """Get or create few-shot engine."""
        if self._few_shot_engine is None:
            from app.modules.sql_examples.few_shot_engine import FewShotEngine
            
            self._few_shot_engine = FewShotEngine(
                dialect=self.dialect,
                embedding_model=self.embedding_model,
                api_key=self.api_key,
            )
        return self._few_shot_engine
    
    async def _get_embed_fn(self):
        """Get embedding function."""
        if self._embed_fn is None:
            from app.modules.embeddings.service import _get_embedding_provider
            self._embed_fn = await _get_embedding_provider(
                self.embedding_model,
                self.api_key,
            )
        return self._embed_fn
    
    async def _retrieve_relevant_tables(
        self,
        query: str,
        top_k: int = 5,
    ) -> Tuple[List[TableContext], Optional[str]]:
        """
        Step 1: Semantic Router - Retrieve relevant tables.
        
        Uses vector similarity to find tables most relevant to the query.
        
        Returns:
            Tuple of (list of TableContext, relationships overview string)
        """
        vectorizer = await self._get_schema_vectorizer()
        
        try:
            results = await vectorizer.search_tables(
                query=query,
                top_k=top_k + 1,  # +1 for relationships doc
                include_relationships=True,
            )
        except Exception as e:
            logger.warning(f"Schema vector search failed: {e}")
            return [], None
        
        table_contexts = []
        relationships_overview = None
        
        for result in results:
            table_name = result.get("table_name", "")
            
            # Handle relationships overview document
            if table_name == "_relationships":
                relationships_overview = result.get("ddl", "")
                continue
            
            ddl = result.get("ddl", "")
            metadata = result.get("metadata", {})
            score = result.get("score", 0.0)
            
            # Parse FK dependencies from metadata
            fk_deps = metadata.get("foreign_key_dependencies", [])
            if isinstance(fk_deps, str):
                try:
                    fk_deps = json.loads(fk_deps)
                except (json.JSONDecodeError, ValueError):
                    fk_deps = []
            
            table_ctx = TableContext(
                table_name=table_name,
                ddl=ddl,
                column_count=metadata.get("column_count", 0),
                row_count=metadata.get("row_count"),
                is_primary=True,
                relevance_score=score,
                foreign_key_to=fk_deps,
            )
            
            # Cache FK relationships
            self._fk_cache[table_name] = fk_deps
            for dep in fk_deps:
                if dep not in self._reverse_fk_cache:
                    self._reverse_fk_cache[dep] = []
                if table_name not in self._reverse_fk_cache[dep]:
                    self._reverse_fk_cache[dep].append(table_name)
            
            table_contexts.append(table_ctx)
        
        logger.info(f"Retrieved {len(table_contexts)} relevant tables for query")
        return table_contexts, relationships_overview
    
    async def _resolve_dependencies(
        self,
        primary_tables: List[TableContext],
        max_dependencies: int = 3,
    ) -> List[TableContext]:
        """
        Step 2: Dependency Resolution - Fetch related tables via FK.
        
        If Table A is retrieved, programmatically fetch Table B if a
        foreign key relationship exists, ensuring join paths are intact.
        """
        if not primary_tables:
            return []
        
        # Collect all FK dependencies
        needed_tables: Set[str] = set()
        primary_names = {t.table_name for t in primary_tables}
        
        for table_ctx in primary_tables:
            # Tables this one points to
            for dep in table_ctx.foreign_key_to:
                if dep not in primary_names:
                    needed_tables.add(dep)
            
            # Tables pointing to this one (reverse FKs)
            for ref in self._reverse_fk_cache.get(table_ctx.table_name, []):
                if ref not in primary_names:
                    needed_tables.add(ref)
        
        if not needed_tables:
            return []
        
        # Limit dependencies to avoid context overflow
        needed_tables = set(list(needed_tables)[:max_dependencies])
        
        logger.info(f"Resolving {len(needed_tables)} FK dependencies: {needed_tables}")
        
        # Fetch dependency DDLs
        dependency_contexts = []
        vectorizer = await self._get_schema_vectorizer()
        
        for table_name in needed_tables:
            try:
                ddl = await vectorizer.get_table_ddl(table_name)
                if ddl:
                    dep_ctx = TableContext(
                        table_name=table_name,
                        ddl=ddl,
                        column_count=0,  # Unknown for dependencies
                        is_primary=False,
                        is_dependency=True,
                        relevance_score=0.5,  # Lower than primary tables
                        foreign_key_to=self._fk_cache.get(table_name, []),
                        foreign_key_from=self._reverse_fk_cache.get(table_name, []),
                    )
                    dependency_contexts.append(dep_ctx)
            except Exception as e:
                logger.warning(f"Failed to fetch dependency {table_name}: {e}")
        
        return dependency_contexts
    
    async def _retrieve_few_shot_examples(
        self,
        query: str,
        top_k: int = 3,
        category_hint: Optional[str] = None,
    ) -> List[FewShotContext]:
        """
        Step 3: Few-Shot Retrieval - Get similar SQL examples.
        
        Queries the golden queries namespace for the top K similar
        historical questions and their corresponding SQL.
        """
        engine = await self._get_few_shot_engine()
        
        try:
            from app.modules.sql_examples.few_shot_engine import DialectTranslator, SQLDialect
            
            examples = await engine.get_few_shot_examples(
                query=query,
                top_k=top_k,
                category_filter=category_hint,
                min_score=0.3,
            )
            
            few_shot_contexts = []
            target_dialect = SQLDialect(self.dialect.lower())
            
            for ex in examples:
                # Get dialect hints if not PostgreSQL
                dialect_hints = []
                if target_dialect != SQLDialect.POSTGRESQL:
                    dialect_hints = DialectTranslator.get_dialect_hints(
                        ex.sql, target_dialect
                    )
                
                ctx = FewShotContext(
                    question=ex.question,
                    sql=ex.sql,
                    category=ex.category,
                    description=ex.description,
                    complexity=ex.complexity,
                    relevance_score=ex.score,
                    dialect_hints=dialect_hints,
                )
                few_shot_contexts.append(ctx)
            
            logger.info(f"Retrieved {len(few_shot_contexts)} few-shot examples")
            return few_shot_contexts
            
        except Exception as e:
            logger.warning(f"Few-shot retrieval failed: {e}")
            return []
    
    def _get_system_instructions(self, db_type: str = "database") -> str:
        """
        Get base system instructions for SQL generation.
        
        Includes dialect-specific rules and safety guidelines.
        """
        base_prompt = get_sql_generator_prompt()
        
        # Add dialect-specific instructions
        dialect_instructions = self._get_dialect_instructions()
        
        # Combine
        if dialect_instructions:
            return f"{base_prompt}\n\n{dialect_instructions}"
        
        return base_prompt
    
    def _get_dialect_instructions(self) -> str:
        """Get dialect-specific SQL instructions."""
        dialect_lower = self.dialect.lower()
        
        if dialect_lower in ("duckdb", "postgresql"):
            return """CRITICAL SQL RULES:
1. Window functions (LAG, LEAD, ROW_NUMBER) CANNOT be used in WHERE - use CTE pattern
2. Use DATE_TRUNC('month', date_col) for date truncation
3. Use INTERVAL '90 days' syntax for date arithmetic
4. For consecutive streak detection, use ROW_NUMBER difference technique in CTEs
5. GREATEST()/LEAST() for row-wise min/max across columns (NOT aggregate min/max)
6. Check VARCHAR date columns and CAST to TIMESTAMP before date operations"""
        
        elif dialect_lower == "mysql":
            return """CRITICAL MYSQL SQL RULES:
1. Use DATE_FORMAT() instead of DATE_TRUNC()
2. Use INTERVAL 30 DAY syntax (no quotes around number)
3. Use CURDATE() instead of CURRENT_DATE
4. For window functions, use MySQL 8.0+ syntax
5. String concatenation uses CONCAT() function
6. Use IFNULL() or COALESCE() for null handling"""
        
        elif dialect_lower == "sqlserver":
            return """CRITICAL SQL SERVER RULES:
1. Use TOP N instead of LIMIT N
2. Use DATETRUNC() (SQL Server 2022+) or DATEPART/DATEFROMPARTS
3. Use DATEADD(day, N, date) instead of INTERVAL
4. Use CAST(GETDATE() AS DATE) instead of CURRENT_DATE
5. Use STDEV() instead of STDDEV()
6. String concatenation uses + operator or CONCAT()"""
        
        return ""
    
    def _estimate_tokens(
        self,
        system_instructions: str,
        table_contexts: List[TableContext],
        few_shot_examples: List[FewShotContext],
        query: str,
    ) -> int:
        """Estimate total token count for the context."""
        total = len(system_instructions) * TOKENS_PER_CHAR
        total += sum(t.token_estimate() for t in table_contexts)
        total += sum(e.token_estimate() for e in few_shot_examples)
        total += len(query) * TOKENS_PER_CHAR
        total += 500  # Buffer for formatting
        return int(total)
    
    def _trim_to_budget(
        self,
        table_contexts: List[TableContext],
        few_shot_examples: List[FewShotContext],
        system_instructions: str,
        query: str,
    ) -> Tuple[List[TableContext], List[FewShotContext]]:
        """
        Trim context to fit within token budget.
        
        Priority order (highest to lowest):
        1. System instructions (required)
        2. Primary tables (by relevance score)
        3. Few-shot examples (by relevance score)
        4. Dependency tables (by relevance score)
        """
        budget = self.max_context_tokens
        
        # Fixed costs
        used = len(system_instructions) * TOKENS_PER_CHAR
        used += len(query) * TOKENS_PER_CHAR
        used += 500  # Buffer
        
        remaining = budget - used
        
        # Separate primary and dependency tables
        primary = [t for t in table_contexts if t.is_primary]
        dependencies = [t for t in table_contexts if t.is_dependency]
        
        # Sort by relevance
        primary.sort(key=lambda t: -t.relevance_score)
        dependencies.sort(key=lambda t: -t.relevance_score)
        few_shot_examples.sort(key=lambda e: -e.relevance_score)
        
        # Allocate budget
        final_tables = []
        final_examples = []
        
        # 1. Add primary tables (60% of remaining budget)
        primary_budget = remaining * 0.6
        for table in primary:
            tokens = table.token_estimate()
            if primary_budget >= tokens:
                final_tables.append(table)
                primary_budget -= tokens
                remaining -= tokens
        
        # 2. Add few-shot examples (25% of original remaining)
        example_budget = (budget - used - 500) * 0.25
        for example in few_shot_examples:
            tokens = example.token_estimate()
            if example_budget >= tokens:
                final_examples.append(example)
                example_budget -= tokens
                remaining -= tokens
        
        # 3. Add dependency tables (remaining budget)
        for table in dependencies:
            tokens = table.token_estimate()
            if remaining >= tokens:
                final_tables.append(table)
                remaining -= tokens
        
        return final_tables, final_examples
    
    async def assemble_context(
        self,
        query: str,
        max_tables: int = 5,
        max_dependencies: int = 3,
        max_examples: int = 3,
        category_hint: Optional[str] = None,
    ) -> AssembledContext:
        """
        Assemble complete context for SQL generation.
        
        Implements the full multi-step retrieval pipeline:
        1. Semantic Router: Retrieve relevant tables
        2. Dependency Resolution: Fetch FK-related tables
        3. Few-Shot Retrieval: Get similar examples
        4. Prompt Assembly: Organize in correct order
        
        Args:
            query: User's natural language question
            max_tables: Maximum primary tables to retrieve
            max_dependencies: Maximum FK dependencies to add
            max_examples: Maximum few-shot examples to retrieve
            category_hint: Optional category for few-shot filtering
        
        Returns:
            AssembledContext ready for prompt generation
        """
        start_time = datetime.now()
        
        # Run retrieval steps in parallel where possible
        table_task = asyncio.create_task(
            self._retrieve_relevant_tables(query, top_k=max_tables)
        )
        example_task = asyncio.create_task(
            self._retrieve_few_shot_examples(query, top_k=max_examples, category_hint=category_hint)
        )
        
        # Wait for primary retrievals
        (primary_tables, relationships_overview), few_shot_examples = await asyncio.gather(
            table_task, example_task
        )
        
        # Resolve dependencies (sequential, needs primary tables first)
        dependency_tables = await self._resolve_dependencies(
            primary_tables, max_dependencies=max_dependencies
        )
        
        # Combine all tables
        all_tables = primary_tables + dependency_tables
        
        # Get system instructions
        system_instructions = self._get_system_instructions()
        
        # Trim to budget if needed
        final_tables, final_examples = self._trim_to_budget(
            all_tables, few_shot_examples, system_instructions, query
        )
        
        # Calculate token estimate
        token_estimate = self._estimate_tokens(
            system_instructions, final_tables, final_examples, query
        )
        
        # Calculate assembly time
        assembly_time = (datetime.now() - start_time).total_seconds() * 1000
        
        context = AssembledContext(
            system_instructions=system_instructions,
            table_contexts=final_tables,
            few_shot_examples=final_examples,
            user_query=query,
            config_id=self.config_id,
            dialect=self.dialect,
            total_tables_available=len(all_tables),
            tables_retrieved=len(final_tables),
            examples_retrieved=len(final_examples),
            token_estimate=token_estimate,
            assembly_time_ms=assembly_time,
            relationships_overview=relationships_overview,
        )
        
        logger.info(
            f"Context assembled: {len(final_tables)} tables, {len(final_examples)} examples, "
            f"~{token_estimate} tokens, {assembly_time:.1f}ms"
        )
        
        return context
    
    async def get_context_for_sql_generation(
        self,
        query: str,
        max_tables: int = 5,
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
    max_tables: int = 5,
    max_examples: int = 3,
    embedding_model: str = "huggingface/BAAI/bge-large-en-v1.5",
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
    max_tables: int = 5,
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
