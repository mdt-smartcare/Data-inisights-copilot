"""
Few-Shot Example Engineering Service for SQL Generation.

Phase 2: Few-Shot Example Engineering
=====================================
Grounds the LLM's SQL dialect and complex join logic using validated examples
rather than relying purely on zero-shot inference.

Features:
- Curated golden queries repository with 50+ complex SQL patterns
- Dialect-aware SQL translation (PostgreSQL, MySQL, SQL Server, Oracle)
- Intent-based vector search for retrieving relevant examples
- Complexity-based filtering (basic, intermediate, advanced)
- Category-based organization (window_functions, cte_patterns, etc.)

Usage:
    from app.modules.sql_examples.few_shot_engine import FewShotEngine
    
    engine = FewShotEngine(config_id=1, dialect="postgresql")
    
    # Get few-shot examples for a user query
    examples = await engine.get_few_shot_examples(
        query="Show me the top 10 patients by visit count",
        top_k=3,
        min_complexity="basic"
    )
    
    # Format examples for LLM prompt
    prompt_section = engine.format_examples_for_prompt(examples)
"""
import json
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from app.core.utils.logging import get_logger
from app.core.settings import get_settings
from app.modules.embeddings.vector_stores.factory import get_vector_store
from app.modules.embeddings.service import _get_embedding_provider

logger = get_logger(__name__)


class SQLDialect(Enum):
    """Supported SQL dialects."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"
    ORACLE = "oracle"
    DUCKDB = "duckdb"
    SQLITE = "sqlite"


class QueryComplexity(Enum):
    """Query complexity levels."""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


# Collection name prefix for few-shot examples
FEWSHOT_COLLECTION_PREFIX = "fewshot_examples_"


@dataclass
class FewShotExample:
    """A single few-shot SQL example."""
    question: str
    sql: str
    category: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    complexity: str = "intermediate"
    dialect_notes: str = ""
    score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "sql": self.sql,
            "category": self.category,
            "tags": self.tags,
            "description": self.description,
            "complexity": self.complexity,
            "dialect_notes": self.dialect_notes,
            "score": self.score,
        }


class DialectTranslator:
    """
    Translates SQL syntax between dialects.
    
    Handles common dialect-specific transformations like:
    - LIMIT vs TOP vs FETCH FIRST
    - DATE_TRUNC vs DATE_FORMAT vs DATETRUNC
    - INTERVAL syntax differences
    - Array/string aggregation functions
    """
    
    # Dialect-specific translations
    TRANSLATIONS = {
        SQLDialect.MYSQL: {
            r"DATE_TRUNC\('(\w+)',\s*(\w+)\)": r"DATE_FORMAT(\2, '%Y-%m-01')",  # Simplified
            r"INTERVAL\s+'(\d+)\s+days'": r"INTERVAL \1 DAY",
            r"INTERVAL\s+'(\d+)\s+months'": r"INTERVAL \1 MONTH",
            r"CURRENT_DATE": "CURDATE()",
            r"PERCENTILE_CONT\(([0-9.]+)\)\s+WITHIN\s+GROUP\s+\(ORDER\s+BY\s+(\w+)\)": 
                r"-- PERCENTILE_CONT not supported in MySQL, use subquery approach",
            r"FILTER\s+\(WHERE": r"-- FILTER not supported, use CASE WHEN: CASE WHEN",
            r"generate_series\([^)]+\)": r"-- generate_series not supported, use recursive CTE",
        },
        SQLDialect.SQLSERVER: {
            r"LIMIT\s+(\d+)": r"-- Use TOP \1 at SELECT or OFFSET FETCH",
            r"DATE_TRUNC\('(\w+)',\s*(\w+)\)": r"DATETRUNC(\1, \2)",
            r"INTERVAL\s+'(\d+)\s+days'": r"DATEADD(day, \1, ",
            r"CURRENT_DATE": "CAST(GETDATE() AS DATE)",
            r"STDDEV\(": "STDEV(",
            r"::\w+": "",  # Remove PostgreSQL type casts
            r"WITH\s+RECURSIVE": "WITH",  # SQL Server doesn't need RECURSIVE keyword
        },
        SQLDialect.ORACLE: {
            r"LIMIT\s+(\d+)": r"FETCH FIRST \1 ROWS ONLY",
            r"DATE_TRUNC\('(\w+)',\s*(\w+)\)": r"TRUNC(\2, '\1')",
            r"CURRENT_DATE": "SYSDATE",
            r"INTERVAL\s+'(\d+)\s+days'": r"NUMTODSINTERVAL(\1, 'DAY')",
            r"::\w+": "",  # Remove PostgreSQL type casts
        },
    }
    
    @classmethod
    def get_dialect_hints(cls, sql: str, target_dialect: SQLDialect) -> List[str]:
        """
        Get hints for translating SQL to target dialect.
        
        Returns a list of translation hints rather than auto-translating,
        since full translation is complex and error-prone.
        """
        hints = []
        
        if target_dialect == SQLDialect.POSTGRESQL:
            return hints  # Golden queries are already in PostgreSQL
        
        # Check for PostgreSQL-specific constructs
        if "LIMIT" in sql and target_dialect == SQLDialect.SQLSERVER:
            hints.append("Replace LIMIT N with TOP N at SELECT or use OFFSET 0 ROWS FETCH FIRST N ROWS ONLY")
        
        if "DATE_TRUNC" in sql:
            if target_dialect == SQLDialect.MYSQL:
                hints.append("Replace DATE_TRUNC with DATE_FORMAT or YEAR/MONTH/DAY functions")
            elif target_dialect == SQLDialect.SQLSERVER:
                hints.append("Replace DATE_TRUNC with DATETRUNC (SQL Server 2022+) or DATEPART/DATEFROMPARTS")
            elif target_dialect == SQLDialect.ORACLE:
                hints.append("Replace DATE_TRUNC with TRUNC function")
        
        if "INTERVAL" in sql:
            if target_dialect == SQLDialect.MYSQL:
                hints.append("Change INTERVAL '30 days' to INTERVAL 30 DAY")
            elif target_dialect == SQLDialect.SQLSERVER:
                hints.append("Replace INTERVAL with DATEADD function")
        
        if "generate_series" in sql:
            hints.append("generate_series is PostgreSQL-specific. Use recursive CTE or numbers table")
        
        if "FILTER (WHERE" in sql:
            hints.append("FILTER clause is PostgreSQL-specific. Use CASE WHEN inside aggregate")
        
        if "PERCENTILE_CONT" in sql and "WITHIN GROUP" in sql:
            if target_dialect == SQLDialect.MYSQL:
                hints.append("PERCENTILE_CONT not supported in MySQL. Use window function approach")
            elif target_dialect == SQLDialect.SQLSERVER:
                hints.append("Use PERCENTILE_CONT with OVER clause instead of WITHIN GROUP")
        
        if "::" in sql:
            hints.append("PostgreSQL type cast (::) not supported. Use CAST() function")
        
        if "ARRAY_AGG" in sql:
            if target_dialect == SQLDialect.MYSQL:
                hints.append("Replace ARRAY_AGG with GROUP_CONCAT")
            elif target_dialect == SQLDialect.SQLSERVER:
                hints.append("Replace ARRAY_AGG with STRING_AGG")
        
        return hints


class FewShotEngine:
    """
    Engine for retrieving and formatting few-shot SQL examples.
    
    Uses vector similarity search to find relevant examples based on
    the user's natural language query, then formats them for the LLM prompt.
    """
    
    def __init__(
        self,
        config_id: Optional[int] = None,
        dialect: str = "postgresql",
        embedding_model: str = "huggingface/BAAI/bge-large-en-v1.5",
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
    ):
        """
        Initialize the few-shot engine.
        
        Args:
            config_id: Agent configuration ID (optional, for config-specific examples)
            dialect: Target SQL dialect
            embedding_model: Embedding model for similarity search
            api_key: API key for embedding model
            api_base_url: API base URL for embedding model
        """
        self.config_id = config_id
        self.dialect = SQLDialect(dialect.lower()) if isinstance(dialect, str) else dialect
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.api_base_url = api_base_url
        
        # Collection name (global examples + optional config-specific)
        self.collection_name = f"{FEWSHOT_COLLECTION_PREFIX}global"
        
        # Vector store
        self.vector_store = get_vector_store(self.collection_name)
        
        # Embedding function (lazy loaded)
        self._embed_fn = None
        
        # Cached golden queries
        self._golden_queries: Optional[Dict[str, Any]] = None
    
    async def _get_embed_fn(self) -> Callable:
        """Get or initialize the embedding function."""
        if self._embed_fn is None:
            self._embed_fn = await _get_embedding_provider(
                self.embedding_model,
                self.api_key,
                self.api_base_url,
            )
        return self._embed_fn
    
    def _load_golden_queries(self) -> Dict[str, Any]:
        """Load golden queries from JSON file."""
        if self._golden_queries is not None:
            return self._golden_queries
        
        golden_path = Path(__file__).parent / "golden_queries.json"
        
        if not golden_path.exists():
            logger.warning(f"Golden queries file not found: {golden_path}")
            return {"examples": [], "metadata": {}, "categories": {}}
        
        with open(golden_path, "r", encoding="utf-8") as f:
            self._golden_queries = json.load(f)
        
        logger.info(f"Loaded {len(self._golden_queries.get('examples', []))} golden queries")
        return self._golden_queries
    
    async def index_golden_queries(
        self,
        replace_existing: bool = True,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Index golden queries into the vector store.
        
        This should be called once to populate the few-shot examples collection.
        
        Args:
            replace_existing: Whether to replace existing examples
            on_progress: Optional progress callback
        
        Returns:
            Indexing results
        """
        # Load golden queries
        golden_data = self._load_golden_queries()
        examples = golden_data.get("examples", [])
        
        if not examples:
            return {"success": False, "error": "No golden queries found", "indexed": 0}
        
        # Delete existing collection if requested
        if replace_existing:
            try:
                await self.vector_store.delete_collection()
                logger.info(f"Deleted existing collection: {self.collection_name}")
            except Exception as e:
                logger.warning(f"Could not delete collection: {e}")
        
        if on_progress:
            on_progress(0, 100, "Loading embedding model...")
        
        # Get embedding function
        embed_fn = await self._get_embed_fn()
        
        if on_progress:
            on_progress(10, 100, f"Generating embeddings for {len(examples)} examples...")
        
        # Extract questions for embedding
        questions = [ex["question"] for ex in examples]
        
        # Generate embeddings
        if asyncio.iscoroutinefunction(embed_fn):
            embeddings = await embed_fn(questions)
        else:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, embed_fn, questions)
        
        if on_progress:
            on_progress(70, 100, "Storing vectors...")
        
        # Prepare documents for storage
        ids = []
        documents = []
        metadatas = []
        
        for i, ex in enumerate(examples):
            # Generate deterministic ID
            doc_id = hashlib.sha256(
                f"{ex['question']}|{ex['sql'][:100]}".encode()
            ).hexdigest()[:16]
            
            ids.append(doc_id)
            documents.append(ex["question"])
            
            # Store SQL and metadata
            metadata = {
                "question": ex["question"],
                "sql": ex["sql"],
                "category": ex.get("category", "general"),
                "tags": ",".join(ex.get("tags", [])),
                "description": ex.get("description", ""),
                "complexity": ex.get("complexity", "intermediate"),
                "dialect_notes": ex.get("dialect_notes", ""),
            }
            metadatas.append(metadata)
        
        # Upsert to vector store
        await self.vector_store.upsert_batch(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        
        # Verify
        count = await self.vector_store.get_collection_count()
        
        if on_progress:
            on_progress(100, 100, f"Indexed {count} examples")
        
        logger.info(f"Indexed {count} few-shot examples")
        
        return {
            "success": True,
            "indexed": count,
            "collection_name": self.collection_name,
        }
    
    async def get_few_shot_examples(
        self,
        query: str,
        top_k: int = 3,
        category_filter: Optional[str] = None,
        min_complexity: Optional[str] = None,
        max_complexity: Optional[str] = None,
        min_score: float = 0.3,
    ) -> List[FewShotExample]:
        """
        Retrieve relevant few-shot examples for a user query.
        
        Args:
            query: User's natural language question
            top_k: Number of examples to retrieve
            category_filter: Filter by category (e.g., "window_functions")
            min_complexity: Minimum complexity level
            max_complexity: Maximum complexity level
            min_score: Minimum similarity score
        
        Returns:
            List of relevant FewShotExample objects
        """
        # Check if collection exists
        if not await self.vector_store.collection_exists():
            logger.warning("Few-shot collection not indexed. Indexing now...")
            await self.index_golden_queries()
        
        # Get embedding function
        embed_fn = await self._get_embed_fn()
        
        # Generate query embedding
        if asyncio.iscoroutinefunction(embed_fn):
            query_embedding = (await embed_fn([query]))[0]
        else:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, embed_fn, [query])
            query_embedding = embeddings[0]
        
        # Build filter
        filter_dict = None
        if category_filter:
            filter_dict = {"category": category_filter}
        
        # Search
        results = await self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k * 2,  # Get more to filter
            filter_dict=filter_dict,
        )
        
        # Process results
        examples = []
        complexity_order = {"basic": 1, "intermediate": 2, "advanced": 3}
        
        for result in results:
            score = result.get("score", 0.0)
            
            if score < min_score:
                continue
            
            metadata = result.get("metadata", {})
            complexity = metadata.get("complexity", "intermediate")
            
            # Filter by complexity
            if min_complexity:
                if complexity_order.get(complexity, 2) < complexity_order.get(min_complexity, 1):
                    continue
            
            if max_complexity:
                if complexity_order.get(complexity, 2) > complexity_order.get(max_complexity, 3):
                    continue
            
            # Parse tags
            tags_str = metadata.get("tags", "")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            
            example = FewShotExample(
                question=metadata.get("question", ""),
                sql=metadata.get("sql", ""),
                category=metadata.get("category", "general"),
                tags=tags,
                description=metadata.get("description", ""),
                complexity=complexity,
                dialect_notes=metadata.get("dialect_notes", ""),
                score=score,
            )
            examples.append(example)
            
            if len(examples) >= top_k:
                break
        
        logger.debug(f"Retrieved {len(examples)} few-shot examples for query: {query[:50]}...")
        return examples
    
    def format_examples_for_prompt(
        self,
        examples: List[FewShotExample],
        include_dialect_hints: bool = True,
        include_descriptions: bool = True,
    ) -> str:
        """
        Format few-shot examples for inclusion in LLM prompt.
        
        Args:
            examples: List of FewShotExample objects
            include_dialect_hints: Whether to include dialect translation hints
            include_descriptions: Whether to include example descriptions
        
        Returns:
            Formatted string for prompt injection
        """
        if not examples:
            return ""
        
        lines = ["## Similar SQL Examples (Few-Shot Learning)", ""]
        lines.append("Use these verified examples as reference for SQL patterns and syntax:")
        lines.append("")
        
        for i, ex in enumerate(examples, 1):
            lines.append(f"### Example {i}")
            lines.append(f"**Question:** {ex.question}")
            
            if include_descriptions and ex.description:
                lines.append(f"**Pattern:** {ex.description}")
            
            lines.append(f"**SQL:**")
            lines.append("```sql")
            lines.append(ex.sql)
            lines.append("```")
            
            # Add dialect hints if needed
            if include_dialect_hints and self.dialect != SQLDialect.POSTGRESQL:
                hints = DialectTranslator.get_dialect_hints(ex.sql, self.dialect)
                if hints:
                    lines.append(f"**{self.dialect.value.upper()} Notes:**")
                    for hint in hints:
                        lines.append(f"- {hint}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    async def get_example_count(self) -> int:
        """Get the number of indexed examples."""
        try:
            return await self.vector_store.get_collection_count()
        except Exception:
            return 0
    
    async def get_categories(self) -> Dict[str, str]:
        """Get available categories with descriptions."""
        golden_data = self._load_golden_queries()
        return golden_data.get("categories", {})
    
    async def delete_collection(self) -> bool:
        """Delete the few-shot examples collection."""
        try:
            await self.vector_store.delete_collection()
            logger.info(f"Deleted few-shot collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False


async def get_few_shot_context(
    query: str,
    dialect: str = "postgresql",
    top_k: int = 3,
    embedding_model: str = "huggingface/BAAI/bge-large-en-v1.5",
    api_key: Optional[str] = None,
) -> str:
    """
    Convenience function to get few-shot context for SQL generation.
    
    This is the main entry point for integrating few-shot examples
    into the SQL generation pipeline.
    
    Args:
        query: User's natural language question
        dialect: Target SQL dialect
        top_k: Number of examples to include
        embedding_model: Embedding model name
        api_key: API key for embedding model
    
    Returns:
        Formatted few-shot context string
    """
    engine = FewShotEngine(
        dialect=dialect,
        embedding_model=embedding_model,
        api_key=api_key,
    )
    
    examples = await engine.get_few_shot_examples(
        query=query,
        top_k=top_k,
        min_score=0.3,
    )
    
    return engine.format_examples_for_prompt(examples)


async def index_few_shot_examples(
    replace_existing: bool = True,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Index the golden queries repository into the vector store.
    
    Call this once to set up the few-shot examples collection.
    """
    engine = FewShotEngine()
    return await engine.index_golden_queries(
        replace_existing=replace_existing,
        on_progress=on_progress,
    )
