"""
Thread-Safe Cache Manager with Tenant Isolation

Addresses multiple shortcomings:
- Thread safety for global caches
- Tenant isolation for multi-tenant deployments
- Connection health checks
- Query result caching with TTL
- Rate limiting for LLM calls

Usage:
    from app.core.thread_safe_cache import (
        ThreadSafeEngineCache,
        QueryResultCache,
        LLMRateLimiter,
        get_engine_cache,
        get_result_cache,
        get_rate_limiter,
    )
"""
import threading
import asyncio
import time
import hashlib
from typing import Dict, Optional, Any, Tuple, List, TypeVar
from dataclasses import dataclass, field
from collections import OrderedDict
from datetime import datetime, timedelta
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, InterfaceError

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


# =============================================================================
# Thread-Safe Engine Cache with Tenant Isolation
# =============================================================================

@dataclass
class EngineEntry:
    """Cache entry for a database engine."""
    engine: Engine
    created_at: datetime
    last_used: datetime
    last_health_check: datetime
    is_healthy: bool = True
    tenant_id: Optional[str] = None


class ThreadSafeEngineCache:
    """
    Thread-safe database engine cache with tenant isolation and health checks.
    
    Features:
    - Thread-safe access with RLock
    - Tenant isolation (cache keys include tenant_id)
    - Periodic health checks for stale connections
    - Automatic cleanup of unhealthy connections
    """
    
    # Health check interval (30 seconds)
    HEALTH_CHECK_INTERVAL = timedelta(seconds=30)
    
    # Maximum age for idle connections (5 minutes)
    MAX_IDLE_TIME = timedelta(minutes=5)
    
    def __init__(self):
        self._cache: Dict[str, EngineEntry] = {}
        self._lock = threading.RLock()
        self._table_names_cache: Dict[str, Tuple[List[str], datetime]] = {}
    
    def _make_key(self, db_url: str, tenant_id: Optional[str] = None) -> str:
        """Create a cache key that includes tenant isolation."""
        # Hash the URL to avoid exposing credentials in logs
        url_hash = hashlib.sha256(db_url.encode()).hexdigest()[:16]
        if tenant_id:
            return f"{tenant_id}:{url_hash}"
        return url_hash
    
    def get_or_create(
        self,
        db_url: str,
        tenant_id: Optional[str] = None,
        **engine_kwargs
    ) -> Engine:
        """
        Get an existing engine or create a new one.
        
        Args:
            db_url: Database connection URL
            tenant_id: Tenant ID for isolation
            **engine_kwargs: Additional arguments for create_engine
            
        Returns:
            SQLAlchemy Engine instance
        """
        key = self._make_key(db_url, tenant_id)
        
        with self._lock:
            # Check if we have a valid cached engine
            if key in self._cache:
                entry = self._cache[key]
                
                # Health check if needed
                if self._needs_health_check(entry):
                    if self._check_health(entry):
                        entry.last_health_check = datetime.utcnow()
                    else:
                        # Remove unhealthy engine
                        logger.warning(f"Removing unhealthy engine from cache", tenant_id=tenant_id)
                        self._remove_engine(key)
                        return self._create_engine(db_url, key, tenant_id, **engine_kwargs)
                
                entry.last_used = datetime.utcnow()
                return entry.engine
            
            # Create new engine
            return self._create_engine(db_url, key, tenant_id, **engine_kwargs)
    
    def _create_engine(
        self,
        db_url: str,
        key: str,
        tenant_id: Optional[str],
        **engine_kwargs
    ) -> Engine:
        """Create a new engine and cache it."""
        # Normalize PostgreSQL URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        # Handle DuckDB specially
        if db_url.startswith("duckdb://"):
            file_path = db_url.replace("duckdb://", "")
            engine = create_engine(
                f"duckdb:///{file_path}",
                connect_args={"read_only": True},
                **engine_kwargs
            )
        else:
            # Default connection pool settings for PostgreSQL
            default_kwargs = {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_pre_ping": True,  # Enable connection health checks
            }
            default_kwargs.update(engine_kwargs)
            engine = create_engine(db_url, **default_kwargs)
        
        now = datetime.utcnow()
        self._cache[key] = EngineEntry(
            engine=engine,
            created_at=now,
            last_used=now,
            last_health_check=now,
            is_healthy=True,
            tenant_id=tenant_id
        )
        
        logger.info(f"Created new database engine", tenant_id=tenant_id)
        return engine
    
    def _needs_health_check(self, entry: EngineEntry) -> bool:
        """Check if a health check is needed."""
        elapsed = datetime.utcnow() - entry.last_health_check
        return elapsed > self.HEALTH_CHECK_INTERVAL
    
    def _check_health(self, entry: EngineEntry) -> bool:
        """Perform a health check on the engine."""
        try:
            with entry.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            entry.is_healthy = True
            return True
        except (OperationalError, InterfaceError) as e:
            logger.warning(f"Engine health check failed: {e}")
            entry.is_healthy = False
            return False
        except Exception as e:
            logger.error(f"Unexpected error in health check: {e}")
            entry.is_healthy = False
            return False
    
    def _remove_engine(self, key: str) -> None:
        """Remove an engine from the cache."""
        if key in self._cache:
            entry = self._cache.pop(key)
            try:
                entry.engine.dispose()
            except Exception as e:
                logger.error(f"Error disposing engine: {e}")
    
    def get_table_names(
        self,
        db_url: str,
        tenant_id: Optional[str] = None,
        ttl_seconds: int = 300
    ) -> List[str]:
        """
        Get cached table names for a database.
        
        Args:
            db_url: Database URL
            tenant_id: Tenant ID for isolation
            ttl_seconds: Cache TTL in seconds
            
        Returns:
            List of table names
        """
        key = self._make_key(db_url, tenant_id)
        
        with self._lock:
            if key in self._table_names_cache:
                tables, cached_at = self._table_names_cache[key]
                if datetime.utcnow() - cached_at < timedelta(seconds=ttl_seconds):
                    return tables
            
            # Fetch from database
            engine = self.get_or_create(db_url, tenant_id)
            try:
                from sqlalchemy import inspect
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                self._table_names_cache[key] = (tables, datetime.utcnow())
                return tables
            except Exception as e:
                logger.error(f"Failed to get table names: {e}")
                return []
    
    def invalidate(
        self,
        db_url: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> None:
        """
        Invalidate cached engines.
        
        Args:
            db_url: Specific URL to invalidate (None = all)
            tenant_id: Specific tenant to invalidate (None = all)
        """
        with self._lock:
            if db_url:
                key = self._make_key(db_url, tenant_id)
                self._remove_engine(key)
                self._table_names_cache.pop(key, None)
            elif tenant_id:
                # Remove all engines for this tenant
                keys_to_remove = [
                    k for k, v in self._cache.items()
                    if v.tenant_id == tenant_id
                ]
                for key in keys_to_remove:
                    self._remove_engine(key)
                    self._table_names_cache.pop(key, None)
            else:
                # Remove all
                for key in list(self._cache.keys()):
                    self._remove_engine(key)
                self._table_names_cache.clear()
    
    def cleanup_idle(self) -> int:
        """
        Clean up idle connections.
        
        Returns:
            Number of connections cleaned up
        """
        now = datetime.utcnow()
        cleaned = 0
        
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if now - entry.last_used > self.MAX_IDLE_TIME
            ]
            for key in keys_to_remove:
                self._remove_engine(key)
                cleaned += 1
        
        if cleaned:
            logger.info(f"Cleaned up {cleaned} idle database connections")
        
        return cleaned


# =============================================================================
# Query Result Cache with TTL
# =============================================================================

@dataclass
class CachedResult:
    """Cached query result."""
    result: Any
    created_at: datetime
    query_hash: str
    schema_version: str


class QueryResultCache:
    """
    LRU cache for query results with TTL.
    
    Features:
    - LRU eviction policy
    - TTL-based expiration
    - Schema version tracking
    - Thread-safe operations
    """
    
    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: int = 300
    ):
        self._cache: OrderedDict[str, CachedResult] = OrderedDict()
        self._max_size = max_size
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.RLock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def _make_key(
        self,
        query: str,
        db_url: str,
        tenant_id: Optional[str] = None
    ) -> str:
        """Create a cache key for a query."""
        content = f"{tenant_id or ''}:{db_url}:{query}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(
        self,
        query: str,
        db_url: str,
        tenant_id: Optional[str] = None,
        schema_version: Optional[str] = None
    ) -> Optional[Any]:
        """
        Get a cached result if available.
        
        Args:
            query: SQL query string
            db_url: Database URL
            tenant_id: Tenant ID
            schema_version: Expected schema version (invalidates if different)
            
        Returns:
            Cached result or None
        """
        key = self._make_key(query, db_url, tenant_id)
        
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            if datetime.utcnow() - entry.created_at > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Check schema version
            if schema_version and entry.schema_version != schema_version:
                del self._cache[key]
                self._misses += 1
                return None
            
            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.result
    
    def put(
        self,
        query: str,
        db_url: str,
        result: Any,
        tenant_id: Optional[str] = None,
        schema_version: str = "1"
    ) -> None:
        """
        Cache a query result.
        
        Args:
            query: SQL query string
            db_url: Database URL
            result: Query result to cache
            tenant_id: Tenant ID
            schema_version: Schema version string
        """
        key = self._make_key(query, db_url, tenant_id)
        
        with self._lock:
            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = CachedResult(
                result=result,
                created_at=datetime.utcnow(),
                query_hash=key,
                schema_version=schema_version
            )
    
    def invalidate(
        self,
        db_url: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> None:
        """Invalidate cached results."""
        with self._lock:
            if db_url is None and tenant_id is None:
                self._cache.clear()
            else:
                # This is inefficient but maintains correctness
                # In production, consider using a more sophisticated key structure
                self._cache.clear()
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0,
                "size": len(self._cache),
                "max_size": self._max_size,
            }


# =============================================================================
# Rate Limiter for LLM Calls
# =============================================================================

@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""
    tokens: float
    last_update: datetime
    max_tokens: float
    refill_rate: float  # tokens per second


class LLMRateLimiter:
    """
    Token bucket rate limiter for LLM API calls.
    
    Features:
    - Per-tenant rate limiting
    - Configurable burst capacity
    - Async-friendly waiting
    - Thread-safe
    """
    
    def __init__(
        self,
        max_tokens_per_second: float = 10.0,
        burst_capacity: float = 50.0
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_tokens_per_second: Refill rate (LLM calls per second)
            burst_capacity: Maximum burst size
        """
        self._buckets: Dict[str, RateLimitBucket] = {}
        self._lock = threading.RLock()
        self._max_tokens = burst_capacity
        self._refill_rate = max_tokens_per_second
    
    def _get_bucket(self, tenant_id: str) -> RateLimitBucket:
        """Get or create a bucket for a tenant."""
        if tenant_id not in self._buckets:
            self._buckets[tenant_id] = RateLimitBucket(
                tokens=self._max_tokens,
                last_update=datetime.utcnow(),
                max_tokens=self._max_tokens,
                refill_rate=self._refill_rate
            )
        return self._buckets[tenant_id]
    
    def _refill(self, bucket: RateLimitBucket) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.utcnow()
        elapsed = (now - bucket.last_update).total_seconds()
        bucket.tokens = min(
            bucket.max_tokens,
            bucket.tokens + elapsed * bucket.refill_rate
        )
        bucket.last_update = now
    
    def acquire(
        self,
        tenant_id: str = "default",
        tokens: float = 1.0,
        wait: bool = True,
        timeout: float = 30.0
    ) -> bool:
        """
        Acquire tokens for an LLM call.
        
        Args:
            tenant_id: Tenant identifier
            tokens: Number of tokens to acquire
            wait: Whether to wait if tokens unavailable
            timeout: Maximum wait time in seconds
            
        Returns:
            True if tokens acquired, False if timed out
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                bucket = self._get_bucket(tenant_id)
                self._refill(bucket)
                
                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    return True
            
            if not wait:
                return False
            
            # Check timeout
            if time.time() - start_time > timeout:
                logger.warning(f"Rate limit timeout for tenant {tenant_id}")
                return False
            
            # Wait a bit before retrying
            time.sleep(0.1)
    
    async def acquire_async(
        self,
        tenant_id: str = "default",
        tokens: float = 1.0,
        timeout: float = 30.0
    ) -> bool:
        """
        Async version of acquire.
        
        Args:
            tenant_id: Tenant identifier
            tokens: Number of tokens to acquire
            timeout: Maximum wait time
            
        Returns:
            True if tokens acquired
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                bucket = self._get_bucket(tenant_id)
                self._refill(bucket)
                
                if bucket.tokens >= tokens:
                    bucket.tokens -= tokens
                    return True
            
            if time.time() - start_time > timeout:
                logger.warning(f"Rate limit timeout for tenant {tenant_id}")
                return False
            
            await asyncio.sleep(0.1)
    
    @contextmanager
    def limit(self, tenant_id: str = "default", tokens: float = 1.0):
        """
        Context manager for rate limiting.
        
        Usage:
            with rate_limiter.limit("tenant_123"):
                result = await llm.invoke(prompt)
        """
        if not self.acquire(tenant_id, tokens):
            raise RateLimitExceeded(f"Rate limit exceeded for tenant {tenant_id}")
        try:
            yield
        finally:
            pass  # No cleanup needed


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


# =============================================================================
# Global Instances
# =============================================================================

_engine_cache: Optional[ThreadSafeEngineCache] = None
_result_cache: Optional[QueryResultCache] = None
_rate_limiter: Optional[LLMRateLimiter] = None
_instance_lock = threading.Lock()


def get_engine_cache() -> ThreadSafeEngineCache:
    """Get the global thread-safe engine cache."""
    global _engine_cache
    with _instance_lock:
        if _engine_cache is None:
            _engine_cache = ThreadSafeEngineCache()
        return _engine_cache


def get_result_cache() -> QueryResultCache:
    """Get the global query result cache."""
    global _result_cache
    with _instance_lock:
        if _result_cache is None:
            _result_cache = QueryResultCache()
        return _result_cache


def get_rate_limiter() -> LLMRateLimiter:
    """Get the global LLM rate limiter."""
    global _rate_limiter
    with _instance_lock:
        if _rate_limiter is None:
            _rate_limiter = LLMRateLimiter()
        return _rate_limiter
