"""
Query Memory — Self-learning NL→SQL memory layer for healthcare data.

Inspired by  memory layer, this module provides:
1. Schema context embedding for semantic retrieval
2. NL→SQL pair storage for few-shot learning
3. Query recall for similar past questions
4. Self-improvement from confirmed queries

Uses LanceDB for vector storage.

Key features:
- Semantic search for relevant schema context per question
- Few-shot example retrieval for similar past queries
- Automatic learning from successful query+feedback pairs
- Configurable embedding models (local or API)

Usage:
    memory = QueryMemory(agent_id="uuid", embedding_model=model)
    
    # Index schema (once, when manifest changes)
    await memory.index_schema(manifest)
    
    # Fetch relevant context for a question
    context = await memory.fetch_context("patients by enrollment status")
    
    # Recall similar past queries
    examples = await memory.recall_queries("screening completion rate by site")
    
    # Store successful query
    await memory.store_query(
        question="active patients by site",
        sql="SELECT site_id, COUNT(*) FROM patient_tracker WHERE is_active = true GROUP BY 1",
        feedback="positive"
    )
"""
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# Try to import LanceDB
try:
    import lancedb
    from lancedb.pydantic import LanceModel, Vector
    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    logger.warning("lancedb not installed. QueryMemory will use fallback storage.")

# Try to import sentence-transformers for local embeddings
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


@dataclass
class SchemaItem:
    """A searchable schema item (table, column, relationship)."""
    id: str
    type: str  # "table", "column", "relationship", "metric"
    name: str
    description: str
    table_name: Optional[str] = None
    data_type: Optional[str] = None
    related_tables: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None


@dataclass
class QueryPair:
    """A stored NL→SQL pair for few-shot learning."""
    id: str
    question: str
    sql: str
    tables_used: List[str]
    created_at: str
    feedback: str = "positive"  # "positive", "negative", "unknown"
    execution_time_ms: Optional[float] = None
    row_count: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None


@dataclass
class MemorySearchResult:
    """Result from memory search."""
    items: List[Dict[str, Any]]
    query: str
    search_time_ms: float
    total_items: int


class EmbeddingProvider:
    """
    Embedding provider abstraction.
    
    Supports:
    - Local sentence-transformers models
    - OpenAI embeddings
    - Custom embedding functions
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        use_openai: bool = False,
        openai_model: str = "text-embedding-3-small"
    ):
        self.model_name = model_name
        self.use_openai = use_openai
        self.openai_model = openai_model
        self._model = None
        self._dimension = None
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            if self.use_openai:
                self._dimension = 1536 if "3-small" in self.openai_model else 3072
            else:
                # Load model to get dimension
                self._load_model()
                self._dimension = self._model.get_sentence_embedding_dimension()
        return self._dimension
    
    def _load_model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            if self.use_openai:
                # OpenAI doesn't need a local model
                pass
            elif SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.info(f"Loading embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
            else:
                raise RuntimeError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        if not texts:
            return []
        
        if self.use_openai:
            return self._embed_openai(texts)
        else:
            return self._embed_local(texts)
    
    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """Embed using local sentence-transformers model."""
        self._load_model()
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Embed using OpenAI API."""
        try:
            from openai import OpenAI
            client = OpenAI()
            
            response = client.embeddings.create(
                model=self.openai_model,
                input=texts
            )
            
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise


class QueryMemory:
    """
    Self-learning memory layer for SQL generation.
    
    Stores:
    1. Schema items (tables, columns) for semantic context retrieval
    2. Query pairs (NL→SQL) for few-shot learning
    
    Improves over time as successful queries are stored.
    """
    
    SCHEMA_TABLE = "schema_items"
    QUERY_TABLE = "query_history"
    
    def __init__(
        self,
        agent_id: str,
        db_path: Optional[str] = None,
        embedding_provider: Optional[EmbeddingProvider] = None
    ):
        """
        Initialize QueryMemory.
        
        Args:
            agent_id: Agent ID this memory belongs to
            db_path: Path to LanceDB database directory
            embedding_provider: Provider for generating embeddings
        """
        self.agent_id = agent_id
        self.db_path = Path(db_path or f"data/memory/{agent_id}")
        self.embedding_provider = embedding_provider or EmbeddingProvider()
        
        self._db = None
        self._schema_table = None
        self._query_table = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Ensure LanceDB is initialized."""
        if self._initialized:
            return
        
        if not LANCEDB_AVAILABLE:
            logger.warning("LanceDB not available, using in-memory fallback")
            self._use_fallback = True
            self._fallback_schema = []
            self._fallback_queries = []
            self._initialized = True
            return
        
        self._use_fallback = False
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.db_path))
        self._initialized = True
    
    async def index_schema(
        self,
        manifest: "SchemaManifest",
        force_rebuild: bool = False
    ) -> int:
        """
        Index schema from manifest for semantic search.
        
        Args:
            manifest: Schema manifest to index
            force_rebuild: If True, rebuild index even if exists
            
        Returns:
            Number of items indexed
        """
        self._ensure_initialized()
        start = time.time()
        
        items = []
        
        # Index tables
        for model_name, model in manifest.models.items():
            item = SchemaItem(
                id=f"table:{model_name}",
                type="table",
                name=model_name,
                description=model.description or f"Table {model_name}",
                table_name=model_name,
                related_tables=[r.target_table for r in model.relationships]
            )
            items.append(item)
            
            # Index columns
            for col in model.columns:
                col_item = SchemaItem(
                    id=f"column:{model_name}.{col.name}",
                    type="column",
                    name=col.name,
                    description=col.description or f"{col.name} ({col.data_type})",
                    table_name=model_name,
                    data_type=col.data_type
                )
                items.append(col_item)
        
        # Index metric templates
        for metric_name, metric_sql in manifest.metric_templates.items():
            item = SchemaItem(
                id=f"metric:{metric_name}",
                type="metric",
                name=metric_name,
                description=f"Metric: {metric_name}"
            )
            items.append(item)
        
        # Generate embeddings
        texts = [f"{item.name}: {item.description}" for item in items]
        embeddings = self.embedding_provider.embed(texts)
        
        for item, embedding in zip(items, embeddings):
            item.embedding = embedding
        
        # Store in LanceDB
        if self._use_fallback:
            self._fallback_schema = items
        else:
            # Create or overwrite table
            data = [
                {
                    "id": item.id,
                    "type": item.type,
                    "name": item.name,
                    "description": item.description,
                    "table_name": item.table_name or "",
                    "data_type": item.data_type or "",
                    "related_tables": item.related_tables,
                    "vector": item.embedding
                }
                for item in items
            ]
            
            if self.SCHEMA_TABLE in self._db.table_names():
                if force_rebuild:
                    self._db.drop_table(self.SCHEMA_TABLE)
                    self._schema_table = self._db.create_table(self.SCHEMA_TABLE, data)
                else:
                    # Append or update
                    self._schema_table = self._db.open_table(self.SCHEMA_TABLE)
                    # For simplicity, drop and recreate
                    self._db.drop_table(self.SCHEMA_TABLE)
                    self._schema_table = self._db.create_table(self.SCHEMA_TABLE, data)
            else:
                self._schema_table = self._db.create_table(self.SCHEMA_TABLE, data)
        
        elapsed = (time.time() - start) * 1000
        logger.info(f"Indexed {len(items)} schema items in {elapsed:.0f}ms")
        
        return len(items)
    
    async def fetch_context(
        self,
        question: str,
        limit: int = 10,
        filter_type: Optional[str] = None
    ) -> MemorySearchResult:
        """
        Fetch relevant schema context for a question.
        
        Args:
            question: User's question
            limit: Maximum items to return
            filter_type: Filter by item type ("table", "column", etc.)
            
        Returns:
            MemorySearchResult with relevant schema items
        """
        self._ensure_initialized()
        start = time.time()
        
        # Generate question embedding
        embeddings = self.embedding_provider.embed([question])
        query_embedding = embeddings[0]
        
        if self._use_fallback:
            # Simple cosine similarity search
            results = self._fallback_search(
                query_embedding,
                self._fallback_schema,
                limit,
                filter_type
            )
        else:
            if self.SCHEMA_TABLE not in self._db.table_names():
                return MemorySearchResult(
                    items=[],
                    query=question,
                    search_time_ms=0,
                    total_items=0
                )
            
            table = self._db.open_table(self.SCHEMA_TABLE)
            
            # Search with optional type filter
            search = table.search(query_embedding).limit(limit)
            
            if filter_type:
                search = search.where(f"type = '{filter_type}'")
            
            df = search.to_pandas()
            results = df.to_dict(orient="records")
        
        elapsed = (time.time() - start) * 1000
        
        return MemorySearchResult(
            items=results,
            query=question,
            search_time_ms=elapsed,
            total_items=len(results)
        )
    
    async def recall_queries(
        self,
        question: str,
        limit: int = 5,
        feedback_filter: Optional[str] = "positive"
    ) -> MemorySearchResult:
        """
        Recall similar past queries for few-shot learning.
        
        Args:
            question: User's question
            limit: Maximum examples to return
            feedback_filter: Filter by feedback ("positive", "negative", None for all)
            
        Returns:
            MemorySearchResult with similar past NL→SQL pairs
        """
        self._ensure_initialized()
        start = time.time()
        
        # Generate question embedding
        embeddings = self.embedding_provider.embed([question])
        query_embedding = embeddings[0]
        
        if self._use_fallback:
            results = self._fallback_query_search(
                query_embedding,
                limit,
                feedback_filter
            )
        else:
            if self.QUERY_TABLE not in self._db.table_names():
                return MemorySearchResult(
                    items=[],
                    query=question,
                    search_time_ms=0,
                    total_items=0
                )
            
            table = self._db.open_table(self.QUERY_TABLE)
            
            search = table.search(query_embedding).limit(limit)
            
            if feedback_filter:
                search = search.where(f"feedback = '{feedback_filter}'")
            
            df = search.to_pandas()
            results = df.to_dict(orient="records")
        
        elapsed = (time.time() - start) * 1000
        
        return MemorySearchResult(
            items=results,
            query=question,
            search_time_ms=elapsed,
            total_items=len(results)
        )
    
    async def store_query(
        self,
        question: str,
        sql: str,
        tables_used: Optional[List[str]] = None,
        feedback: str = "positive",
        execution_time_ms: Optional[float] = None,
        row_count: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Store a confirmed NL→SQL pair for future recall.
        
        Args:
            question: Original user question
            sql: Generated/confirmed SQL
            tables_used: List of tables used
            feedback: User feedback ("positive", "negative")
            execution_time_ms: Query execution time
            row_count: Number of rows returned
            tags: Optional tags for categorization
            
        Returns:
            ID of stored query
        """
        self._ensure_initialized()
        
        # Generate ID
        query_id = hashlib.md5(
            f"{question}:{sql}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Generate embedding
        embeddings = self.embedding_provider.embed([question])
        embedding = embeddings[0]
        
        pair = QueryPair(
            id=query_id,
            question=question,
            sql=sql,
            tables_used=tables_used or [],
            created_at=datetime.utcnow().isoformat(),
            feedback=feedback,
            execution_time_ms=execution_time_ms,
            row_count=row_count,
            tags=tags or [],
            embedding=embedding
        )
        
        if self._use_fallback:
            self._fallback_queries.append(pair)
        else:
            data = [{
                "id": pair.id,
                "question": pair.question,
                "sql": pair.sql,
                "tables_used": pair.tables_used,
                "created_at": pair.created_at,
                "feedback": pair.feedback,
                "execution_time_ms": pair.execution_time_ms or 0,
                "row_count": pair.row_count or 0,
                "tags": pair.tags,
                "vector": pair.embedding
            }]
            
            if self.QUERY_TABLE in self._db.table_names():
                table = self._db.open_table(self.QUERY_TABLE)
                table.add(data)
            else:
                self._db.create_table(self.QUERY_TABLE, data)
        
        logger.info(f"Stored query pair: {query_id} (feedback={feedback})")
        
        return query_id
    
    async def update_feedback(self, query_id: str, feedback: str) -> bool:
        """Update feedback for a stored query."""
        self._ensure_initialized()
        
        if self._use_fallback:
            for pair in self._fallback_queries:
                if pair.id == query_id:
                    pair.feedback = feedback
                    return True
            return False
        
        if self.QUERY_TABLE not in self._db.table_names():
            return False
        
        # LanceDB doesn't support direct updates, so we'd need to
        # delete and re-add. For now, log warning.
        logger.warning(
            f"Feedback update not fully implemented for LanceDB. "
            f"Query {query_id} feedback would be: {feedback}"
        )
        return True
    
    def _fallback_search(
        self,
        query_embedding: List[float],
        items: List[SchemaItem],
        limit: int,
        filter_type: Optional[str]
    ) -> List[Dict]:
        """Simple cosine similarity search for fallback mode."""
        import numpy as np
        
        query_vec = np.array(query_embedding)
        
        results = []
        for item in items:
            if filter_type and item.type != filter_type:
                continue
            
            if item.embedding:
                item_vec = np.array(item.embedding)
                # Cosine similarity
                similarity = np.dot(query_vec, item_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(item_vec)
                )
                results.append((similarity, item))
        
        # Sort by similarity
        results.sort(key=lambda x: x[0], reverse=True)
        
        return [
            {
                "id": item.id,
                "type": item.type,
                "name": item.name,
                "description": item.description,
                "table_name": item.table_name,
                "_distance": 1 - score
            }
            for score, item in results[:limit]
        ]
    
    def _fallback_query_search(
        self,
        query_embedding: List[float],
        limit: int,
        feedback_filter: Optional[str]
    ) -> List[Dict]:
        """Simple cosine similarity search for query pairs."""
        import numpy as np
        
        query_vec = np.array(query_embedding)
        
        results = []
        for pair in self._fallback_queries:
            if feedback_filter and pair.feedback != feedback_filter:
                continue
            
            if pair.embedding:
                pair_vec = np.array(pair.embedding)
                similarity = np.dot(query_vec, pair_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(pair_vec)
                )
                results.append((similarity, pair))
        
        results.sort(key=lambda x: x[0], reverse=True)
        
        return [
            {
                "id": pair.id,
                "question": pair.question,
                "sql": pair.sql,
                "tables_used": pair.tables_used,
                "feedback": pair.feedback,
                "_distance": 1 - score
            }
            for score, pair in results[:limit]
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        self._ensure_initialized()
        
        if self._use_fallback:
            return {
                "schema_items": len(self._fallback_schema),
                "query_pairs": len(self._fallback_queries),
                "positive_queries": sum(
                    1 for p in self._fallback_queries if p.feedback == "positive"
                ),
                "storage": "in-memory"
            }
        
        stats = {
            "schema_items": 0,
            "query_pairs": 0,
            "positive_queries": 0,
            "storage": "lancedb"
        }
        
        if self.SCHEMA_TABLE in self._db.table_names():
            table = self._db.open_table(self.SCHEMA_TABLE)
            stats["schema_items"] = table.count_rows()
        
        if self.QUERY_TABLE in self._db.table_names():
            table = self._db.open_table(self.QUERY_TABLE)
            stats["query_pairs"] = table.count_rows()
            # Count positive would require a query
        
        return stats


def format_few_shot_examples(
    examples: List[Dict[str, Any]],
    max_examples: int = 3
) -> str:
    """
    Format recalled query pairs as few-shot examples for the prompt.
    
    Args:
        examples: List of query pair dicts from recall_queries
        max_examples: Maximum examples to include
        
    Returns:
        Formatted string for prompt injection
    """
    if not examples:
        return ""
    
    parts = ["### Similar Past Queries (for reference)"]
    
    for i, ex in enumerate(examples[:max_examples]):
        parts.append(f"\nExample {i+1}:")
        parts.append(f"Question: {ex.get('question', 'N/A')}")
        parts.append(f"SQL: {ex.get('sql', 'N/A')}")
    
    return "\n".join(parts)
