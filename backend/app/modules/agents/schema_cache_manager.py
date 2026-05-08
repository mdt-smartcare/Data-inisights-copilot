"""
Schema Cache Manager — Centralized cache invalidation for schema-related caches.

Provides a single point of control for invalidating schema caches across
multiple services when database schema changes are detected.

This prevents stale schema data from causing SQL generation errors when:
- Database schema is modified (new tables, columns, etc.)
- Data source configuration changes
- Admin triggers a manual refresh

Usage:
    from app.modules.agents.schema_cache_manager import schema_cache_manager
    
    # Invalidate all caches for a specific data source
    schema_cache_manager.invalidate_source(source_id)
    
    # Invalidate all schema caches globally
    schema_cache_manager.invalidate_all()
    
    # Check if cache is stale for a source
    if schema_cache_manager.is_stale(source_id, last_known_hash):
        # Re-fetch schema
        ...
"""
import time
import hashlib
from typing import Dict, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from uuid import UUID
from functools import wraps

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """Metadata for a cached schema."""
    source_id: str
    cached_at: float
    schema_hash: str
    ttl: int = 300  # Default 5 minutes


class SchemaCacheManager:
    """
    Centralized manager for schema cache invalidation.
    
    Maintains a registry of cache invalidation callbacks and tracks
    schema versions to detect when caches need refreshing.
    """
    
    def __init__(self, default_ttl: int = 300):
        """
        Initialize the cache manager.
        
        Args:
            default_ttl: Default time-to-live for cache entries in seconds
        """
        self._default_ttl = default_ttl
        
        # Registry of invalidation callbacks
        # Each callback is called with (source_id: Optional[str]) when invalidation is triggered
        self._invalidation_callbacks: list[Callable[[Optional[str]], None]] = []
        
        # Schema version tracking
        # Maps source_id -> CacheEntry
        self._schema_versions: Dict[str, CacheEntry] = {}
        
        # Track which sources have been invalidated recently (debounce)
        self._recent_invalidations: Dict[str, float] = {}
        self._debounce_seconds = 5  # Minimum seconds between invalidations for same source
        
        logger.info("SchemaCacheManager initialized")
    
    def register_invalidation_callback(
        self, 
        callback: Callable[[Optional[str]], None],
        name: str = "unknown"
    ) -> None:
        """
        Register a callback to be called when cache invalidation is triggered.
        
        Args:
            callback: Function that takes an optional source_id and clears relevant caches
            name: Descriptive name for logging
        """
        self._invalidation_callbacks.append(callback)
        logger.debug(f"Registered cache invalidation callback: {name}")
    
    def invalidate_source(self, source_id: str) -> int:
        """
        Invalidate all caches for a specific data source.
        
        Args:
            source_id: UUID string of the data source
            
        Returns:
            Number of callbacks invoked
        """
        source_id_str = str(source_id)
        
        # Debounce rapid invalidations
        now = time.time()
        last_invalidation = self._recent_invalidations.get(source_id_str, 0)
        if now - last_invalidation < self._debounce_seconds:
            logger.debug(f"Skipping invalidation for {source_id_str} (debounced)")
            return 0
        
        self._recent_invalidations[source_id_str] = now
        
        # Clear version tracking
        if source_id_str in self._schema_versions:
            del self._schema_versions[source_id_str]
        
        # Invoke all registered callbacks
        callback_count = 0
        for callback in self._invalidation_callbacks:
            try:
                callback(source_id_str)
                callback_count += 1
            except Exception as e:
                logger.warning(f"Cache invalidation callback failed: {e}")
        
        logger.info(f"Invalidated schema caches for source {source_id_str} ({callback_count} callbacks)")
        return callback_count
    
    def invalidate_all(self) -> int:
        """
        Invalidate all schema caches globally.
        
        Returns:
            Number of callbacks invoked
        """
        # Clear all version tracking
        self._schema_versions.clear()
        self._recent_invalidations.clear()
        
        # Invoke all callbacks with None (meaning all sources)
        callback_count = 0
        for callback in self._invalidation_callbacks:
            try:
                callback(None)
                callback_count += 1
            except Exception as e:
                logger.warning(f"Cache invalidation callback failed: {e}")
        
        logger.info(f"Invalidated all schema caches ({callback_count} callbacks)")
        return callback_count
    
    def register_schema_version(
        self, 
        source_id: str, 
        schema_data: Any,
        ttl: Optional[int] = None
    ) -> str:
        """
        Register a schema version for change detection.
        
        Args:
            source_id: UUID string of the data source
            schema_data: Schema data to hash for version tracking
            ttl: Optional TTL override
            
        Returns:
            Hash of the registered schema
        """
        source_id_str = str(source_id)
        schema_hash = self._compute_hash(schema_data)
        
        self._schema_versions[source_id_str] = CacheEntry(
            source_id=source_id_str,
            cached_at=time.time(),
            schema_hash=schema_hash,
            ttl=ttl or self._default_ttl
        )
        
        return schema_hash
    
    def is_stale(
        self, 
        source_id: str, 
        current_hash: Optional[str] = None
    ) -> bool:
        """
        Check if cached schema for a source is stale.
        
        Args:
            source_id: UUID string of the data source
            current_hash: Optional hash of current schema to compare
            
        Returns:
            True if cache is stale (expired or hash mismatch)
        """
        source_id_str = str(source_id)
        entry = self._schema_versions.get(source_id_str)
        
        if not entry:
            return True  # No cached version, consider stale
        
        # Check TTL
        if time.time() - entry.cached_at > entry.ttl:
            return True
        
        # Check hash if provided
        if current_hash and entry.schema_hash != current_hash:
            return True
        
        return False
    
    def get_cached_hash(self, source_id: str) -> Optional[str]:
        """Get the cached schema hash for a source."""
        source_id_str = str(source_id)
        entry = self._schema_versions.get(source_id_str)
        return entry.schema_hash if entry else None
    
    def _compute_hash(self, data: Any) -> str:
        """Compute a hash of schema data for version tracking."""
        if isinstance(data, dict):
            # Sort dict for consistent hashing
            serialized = str(sorted(data.items()))
        elif isinstance(data, (list, tuple)):
            serialized = str(data)
        else:
            serialized = str(data)
        
        return hashlib.md5(serialized.encode()).hexdigest()[:16]


# Global singleton instance
schema_cache_manager = SchemaCacheManager()


def invalidate_schema_on_change(source_id_param: str = "source_id"):
    """
    Decorator to automatically invalidate schema cache after a method that modifies schema.
    
    Usage:
        @invalidate_schema_on_change("data_source_id")
        async def update_data_source(self, data_source_id: UUID, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Try to get source_id from kwargs or args
            source_id = kwargs.get(source_id_param)
            if not source_id and len(args) > 1:
                # Assume first arg after self is source_id
                source_id = args[1] if hasattr(args[0], '__class__') else args[0]
            
            if source_id:
                schema_cache_manager.invalidate_source(str(source_id))
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            source_id = kwargs.get(source_id_param)
            if not source_id and len(args) > 1:
                source_id = args[1] if hasattr(args[0], '__class__') else args[0]
            
            if source_id:
                schema_cache_manager.invalidate_source(str(source_id))
            
            return result
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
