"""
Semantic Query Cache — NL-to-SQL Semantic Deduplication.

Embeds natural language queries and caches the generated SQL.
When a semantically similar query arrives (above threshold),
reuses the cached SQL instead of calling the LLM.

This implements the semantic caching pattern from NL2SQL best practices:
- Embed query using same model as other embeddings
- Vector search for similar past queries
- Reuse SQL if similarity > threshold (default 0.92)
- Respects schema versioning to invalidate on schema changes
"""
import hashlib
import time
from typing import Optional, Dict, List, Tuple, NamedTuple
from dataclasses import dataclass, field
from threading import RLock
from collections import OrderedDict

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CachedQuery:
    """A cached NL-to-SQL mapping."""
    nl_query: str
    generated_sql: str
    embedding: List[float]
    schema_hash: str  # Hash of schema used during generation
    created_at: float
    hit_count: int = 0
    last_hit: float = 0
    
    def is_schema_valid(self, current_schema_hash: str) -> bool:
        """Check if cached SQL is valid for current schema."""
        return self.schema_hash == current_schema_hash


class SemanticCacheResult(NamedTuple):
    """Result of semantic cache lookup."""
    hit: bool
    sql: Optional[str]
    similarity: float
    original_query: Optional[str]  # The cached query that matched


class SemanticQueryCache:
    """
    LRU cache with semantic similarity lookup for NL queries.
    
    Uses cosine similarity on query embeddings to find semantically
    similar past queries and reuse their SQL.
    
    Features:
    - Configurable similarity threshold (default 0.92)
    - Schema-aware invalidation (SQL invalidated if schema changes)
    - TTL expiration
    - Thread-safe operations
    - LRU eviction
    
    Usage:
        cache = SemanticQueryCache(embed_fn=get_embedding)
        
        # Check cache
        result = cache.get("Show me total sales by region")
        if result.hit:
            use_sql(result.sql)  # Skip LLM call
        else:
            sql = generate_sql(...)  # Call LLM
            cache.put(query, sql, schema_hash)
    """
    
    def __init__(
        self,
        embed_fn=None,
        similarity_threshold: float = 0.92,
        max_size: int = 1000,
        ttl_seconds: int = 3600,  # 1 hour default
    ):
        """
        Initialize semantic query cache.
        
        Args:
            embed_fn: Function to embed text -> List[float]
            similarity_threshold: Minimum cosine similarity for cache hit (0.0-1.0)
            max_size: Maximum cached queries (LRU eviction)
            ttl_seconds: Time-to-live for cached entries
        """
        self._embed_fn = embed_fn
        self._similarity_threshold = similarity_threshold
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        
        # LRU cache: OrderedDict maintains insertion order
        self._cache: OrderedDict[str, CachedQuery] = OrderedDict()
        self._lock = RLock()
        
        # Stats
        self._hits = 0
        self._misses = 0
        self._skips = 0  # Skipped due to no embed_fn or disabled
        
        logger.info(
            f"SemanticQueryCache initialized: threshold={similarity_threshold}, "
            f"max_size={max_size}, ttl={ttl_seconds}s"
        )
    
    def set_embed_fn(self, embed_fn):
        """Set the embedding function (can be set after init)."""
        self._embed_fn = embed_fn
        logger.info("SemanticQueryCache embed_fn configured")
    
    def get(
        self,
        nl_query: str,
        current_schema_hash: Optional[str] = None
    ) -> SemanticCacheResult:
        """
        Look up a semantically similar cached query.
        
        Args:
            nl_query: Natural language query
            current_schema_hash: Hash of current schema (for validation)
            
        Returns:
            SemanticCacheResult with hit status, SQL, and similarity
        """
        if not self._embed_fn:
            self._skips += 1
            return SemanticCacheResult(hit=False, sql=None, similarity=0.0, original_query=None)
        
        try:
            # Embed the query
            query_embedding = self._embed_fn(nl_query)
            
            with self._lock:
                best_match: Optional[CachedQuery] = None
                best_similarity = 0.0
                expired_keys = []
                now = time.time()
                
                for key, cached in self._cache.items():
                    # Check TTL
                    if now - cached.created_at > self._ttl_seconds:
                        expired_keys.append(key)
                        continue
                    
                    # Check schema validity
                    if current_schema_hash and not cached.is_schema_valid(current_schema_hash):
                        continue
                    
                    # Calculate cosine similarity
                    similarity = self._cosine_similarity(query_embedding, cached.embedding)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = cached
                
                # Cleanup expired entries
                for key in expired_keys:
                    del self._cache[key]
                
                # Check if best match exceeds threshold
                if best_match and best_similarity >= self._similarity_threshold:
                    self._hits += 1
                    best_match.hit_count += 1
                    best_match.last_hit = now
                    
                    # Move to end (most recently used)
                    self._cache.move_to_end(self._cache_key(best_match.nl_query))
                    
                    logger.info(
                        f"Semantic cache HIT: similarity={best_similarity:.3f}",
                        original_query=best_match.nl_query[:50],
                        new_query=nl_query[:50]
                    )
                    
                    return SemanticCacheResult(
                        hit=True,
                        sql=best_match.generated_sql,
                        similarity=best_similarity,
                        original_query=best_match.nl_query
                    )
                else:
                    self._misses += 1
                    return SemanticCacheResult(
                        hit=False,
                        sql=None,
                        similarity=best_similarity,
                        original_query=best_match.nl_query if best_match else None
                    )
                    
        except Exception as e:
            logger.warning(f"Semantic cache lookup failed: {e}")
            self._misses += 1
            return SemanticCacheResult(hit=False, sql=None, similarity=0.0, original_query=None)
    
    def put(
        self,
        nl_query: str,
        generated_sql: str,
        schema_hash: str,
        embedding: Optional[List[float]] = None
    ) -> bool:
        """
        Cache a query-SQL pair.
        
        Args:
            nl_query: Natural language query
            generated_sql: Generated SQL query
            schema_hash: Hash of schema used during generation
            embedding: Pre-computed embedding (computed if not provided)
            
        Returns:
            True if cached successfully
        """
        if not self._embed_fn and not embedding:
            return False
        
        try:
            # Get or compute embedding
            if embedding is None:
                embedding = self._embed_fn(nl_query)
            
            with self._lock:
                # Evict oldest if at capacity
                while len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                
                key = self._cache_key(nl_query)
                self._cache[key] = CachedQuery(
                    nl_query=nl_query,
                    generated_sql=generated_sql,
                    embedding=embedding,
                    schema_hash=schema_hash,
                    created_at=time.time()
                )
                
                logger.debug(f"Cached query: {nl_query[:50]}...")
                return True
                
        except Exception as e:
            logger.warning(f"Failed to cache query: {e}")
            return False
    
    def invalidate_for_schema(self, schema_hash: str) -> int:
        """
        Invalidate all entries for a specific schema.
        
        Called when schema changes to prevent stale SQL reuse.
        
        Returns:
            Number of entries invalidated
        """
        with self._lock:
            keys_to_remove = [
                key for key, cached in self._cache.items()
                if cached.schema_hash == schema_hash
            ]
            for key in keys_to_remove:
                del self._cache[key]
            
            if keys_to_remove:
                logger.info(f"Invalidated {len(keys_to_remove)} cached queries for schema change")
            
            return len(keys_to_remove)
    
    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared semantic cache ({count} entries)")
    
    def stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "skips": self._skips,
                "hit_rate": round(hit_rate, 3),
                "threshold": self._similarity_threshold,
                "ttl_seconds": self._ttl_seconds
            }
    
    def _cache_key(self, nl_query: str) -> str:
        """Generate cache key from query."""
        return hashlib.md5(nl_query.lower().strip().encode()).hexdigest()
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    @staticmethod
    def compute_schema_hash(schema_context: str) -> str:
        """Compute a hash of the schema for cache invalidation."""
        return hashlib.md5(schema_context.encode()).hexdigest()[:16]


# Global singleton
_semantic_cache: Optional[SemanticQueryCache] = None
_cache_lock = RLock()


def get_semantic_cache(
    embed_fn=None,
    similarity_threshold: float = 0.92,
    max_size: int = 1000,
    ttl_seconds: int = 3600
) -> SemanticQueryCache:
    """
    Get the global semantic query cache instance.
    
    Args:
        embed_fn: Embedding function (set on first call or via set_embed_fn)
        similarity_threshold: Minimum similarity for cache hit
        max_size: Maximum cache entries
        ttl_seconds: Cache TTL
        
    Returns:
        SemanticQueryCache singleton
    """
    global _semantic_cache
    
    with _cache_lock:
        if _semantic_cache is None:
            _semantic_cache = SemanticQueryCache(
                embed_fn=embed_fn,
                similarity_threshold=similarity_threshold,
                max_size=max_size,
                ttl_seconds=ttl_seconds
            )
        elif embed_fn and _semantic_cache._embed_fn is None:
            _semantic_cache.set_embed_fn(embed_fn)
    
    return _semantic_cache
