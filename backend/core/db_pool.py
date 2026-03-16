import threading
from typing import Dict
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Global cache to store SQLAlchemy Engine instances keyed by connecting URI
_engine_cache: Dict[str, Engine] = {}
_engine_cache_lock = threading.Lock()

def get_cached_engine(uri: str, pool_size: int = 5, max_overflow: int = 10, pool_pre_ping: bool = True, pool_timeout: int = 30) -> Engine:
    """
    Get or create a globally cached SQLAlchemy Engine instance for the given URI.
    
    This ensures we share connection pools per database target, 
    preventing PostgreSQL max_connections exhaustion under concurrent load.
    
    Args:
        uri: The database connection string.
        pool_size: The number of connections to keep open.
        max_overflow: The max number of connections to allow beyond pool_size.
        pool_pre_ping: If True, tests connections for liveness before checkout.
        pool_timeout: Seconds to wait before giving up on getting a connection.
        
    Returns:
        A SQLAlchemy Engine instance.
    """
    global _engine_cache

    with _engine_cache_lock:
        if uri not in _engine_cache:
            logger.info(f"Creating new SQLAlchemy Engine pool for DB URI (prefix): {uri[:15]}...")
            try:
                engine = create_engine(
                    uri,
                    pool_size=pool_size,
                    max_overflow=max_overflow,
                    pool_pre_ping=pool_pre_ping,
                    pool_timeout=pool_timeout
                )
                _engine_cache[uri] = engine
            except Exception as e:
                logger.error(f"Failed to create cached engine: {e}")
                raise

        return _engine_cache[uri]

def dispose_engines():
    """
    Dispose all cached engines gracefully. 
    Useful during application shutdown.
    """
    global _engine_cache
    with _engine_cache_lock:
        for uri, engine in _engine_cache.items():
            try:
                engine.dispose()
                logger.info(f"Disposed engine pool for URI (prefix): {uri[:15]}...")
            except Exception as e:
                logger.warning(f"Error disposing engine: {e}")
        _engine_cache.clear()
        
