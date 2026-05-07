"""
Cache Manager for Prompt Templates and Configuration Files

Provides automatic cache invalidation when config files change.
Addresses the "Cache Not Auto-Invalidated" shortcoming.

Features:
- File modification time tracking
- Automatic cache refresh on file change
- Configurable refresh intervals
- Thread-safe operations

Usage:
    from app.core.cache_manager import CacheManager, get_cache_manager
    
    cache_mgr = get_cache_manager()
    
    # Register a file to watch
    cache_mgr.register_file("/path/to/config.yaml", on_change=my_callback)
    
    # Check and refresh if needed
    if cache_mgr.should_refresh("/path/to/config.yaml"):
        # Reload config
        cache_mgr.mark_refreshed("/path/to/config.yaml")
"""
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass
from functools import wraps

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class WatchedFile:
    """Metadata for a watched file."""
    path: Path
    last_modified: float
    last_checked: float
    on_change_callback: Optional[Callable[[], None]] = None


class CacheManager:
    """
    Manages cache invalidation based on file modifications.
    
    Watches configuration files and triggers cache refresh when they change.
    """
    
    # Check file modification at most every N seconds
    MIN_CHECK_INTERVAL = 5.0
    
    def __init__(self):
        self._watched_files: Dict[str, WatchedFile] = {}
        self._lock = threading.Lock()
        self._refresh_callbacks: List[Callable[[], None]] = []
    
    def register_file(
        self,
        file_path: str,
        on_change: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Register a file to watch for changes.
        
        Args:
            file_path: Path to the file to watch
            on_change: Optional callback to invoke when file changes
        """
        path = Path(file_path)
        
        with self._lock:
            mtime = self._get_mtime(path)
            self._watched_files[str(path)] = WatchedFile(
                path=path,
                last_modified=mtime,
                last_checked=time.time(),
                on_change_callback=on_change
            )
            logger.debug(f"Registered file for watching: {path}")
    
    def should_refresh(self, file_path: str) -> bool:
        """
        Check if a file has been modified and cache should be refreshed.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            True if file has changed and cache should be refreshed
        """
        path_str = str(Path(file_path))
        
        with self._lock:
            watched = self._watched_files.get(path_str)
            if not watched:
                # Not registered, register it now
                self.register_file(file_path)
                return False
            
            # Throttle checks
            now = time.time()
            if now - watched.last_checked < self.MIN_CHECK_INTERVAL:
                return False
            
            watched.last_checked = now
            
            # Check modification time
            current_mtime = self._get_mtime(watched.path)
            if current_mtime > watched.last_modified:
                logger.info(f"File modified, cache refresh needed: {file_path}")
                return True
            
            return False
    
    def mark_refreshed(self, file_path: str) -> None:
        """
        Mark a file's cache as refreshed.
        
        Call this after successfully refreshing the cache.
        
        Args:
            file_path: Path to the file
        """
        path_str = str(Path(file_path))
        
        with self._lock:
            watched = self._watched_files.get(path_str)
            if watched:
                watched.last_modified = self._get_mtime(watched.path)
                watched.last_checked = time.time()
                
                # Invoke callback if registered
                if watched.on_change_callback:
                    try:
                        watched.on_change_callback()
                    except Exception as e:
                        logger.error(f"Error in on_change callback: {e}")
    
    def check_all(self) -> List[str]:
        """
        Check all watched files for changes.
        
        Returns:
            List of file paths that have changed
        """
        changed = []
        
        with self._lock:
            for path_str, watched in self._watched_files.items():
                current_mtime = self._get_mtime(watched.path)
                if current_mtime > watched.last_modified:
                    changed.append(path_str)
        
        return changed
    
    def refresh_if_needed(self, file_path: str, refresh_func: Callable[[], None]) -> bool:
        """
        Check if file changed and call refresh function if needed.
        
        Args:
            file_path: Path to the file
            refresh_func: Function to call to refresh the cache
            
        Returns:
            True if cache was refreshed
        """
        if self.should_refresh(file_path):
            try:
                refresh_func()
                self.mark_refreshed(file_path)
                return True
            except Exception as e:
                logger.error(f"Failed to refresh cache for {file_path}: {e}")
        return False
    
    def add_global_refresh_callback(self, callback: Callable[[], None]) -> None:
        """
        Add a callback to be invoked on any cache refresh.
        
        Args:
            callback: Function to call on refresh
        """
        self._refresh_callbacks.append(callback)
    
    @staticmethod
    def _get_mtime(path: Path) -> float:
        """Get file modification time, or 0 if file doesn't exist."""
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            return 0.0


# Singleton instance
_cache_manager: Optional[CacheManager] = None
_cache_manager_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    """Get the global CacheManager instance."""
    global _cache_manager
    
    with _cache_manager_lock:
        if _cache_manager is None:
            _cache_manager = CacheManager()
        return _cache_manager


def cached_with_file_watch(file_path: str):
    """
    Decorator that caches function results and invalidates on file change.
    
    Usage:
        @cached_with_file_watch("/path/to/config.yaml")
        def load_config():
            return parse_yaml(...)
    """
    def decorator(func: Callable[[], Any]) -> Callable[[], Any]:
        cache = {"value": None, "initialized": False}
        lock = threading.Lock()
        
        @wraps(func)
        def wrapper() -> Any:
            cache_mgr = get_cache_manager()
            
            with lock:
                # Check if cache should be refreshed
                should_refresh = cache_mgr.should_refresh(file_path)
                
                if not cache["initialized"] or should_refresh:
                    cache["value"] = func()
                    cache["initialized"] = True
                    cache_mgr.mark_refreshed(file_path)
                    logger.debug(f"Cache refreshed for {func.__name__}")
                
                return cache["value"]
        
        # Allow manual cache clear
        def clear_cache():
            with lock:
                cache["value"] = None
                cache["initialized"] = False
        
        wrapper.clear_cache = clear_cache
        return wrapper
    
    return decorator


# ============================================================================
# Integration Functions for Existing Caches
# ============================================================================

def refresh_prompt_cache() -> None:
    """
    Refresh the prompt template cache.
    
    Call this when prompt template files change.
    """
    from app.core.prompts import clear_prompt_cache
    clear_prompt_cache()
    logger.info("Prompt cache refreshed due to file change")


def refresh_data_dictionary_cache(agent_id: Optional[str] = None) -> None:
    """
    Refresh the data dictionary cache.
    
    Args:
        agent_id: Specific agent to refresh, or None for all
    """
    from app.modules.chat.query.data_dictionary import reset_data_dictionary
    reset_data_dictionary(agent_id)
    logger.info(f"Data dictionary cache refreshed", agent_id=agent_id)


def setup_config_file_watching() -> None:
    """
    Set up file watching for common configuration files.
    
    Call this at application startup.
    """
    cache_mgr = get_cache_manager()
    
    # Watch prompt template directory
    prompt_dir = Path(__file__).parent.parent / "agent_spec" / "prompt_templates"
    if prompt_dir.exists():
        for template_file in prompt_dir.glob("*.md"):
            cache_mgr.register_file(
                str(template_file),
                on_change=refresh_prompt_cache
            )
        logger.info(f"Watching {len(list(prompt_dir.glob('*.md')))} prompt templates")
    
    # Watch default data dictionary
    data_dict_path = Path(__file__).parent / "config" / "data_dictionary.yaml"
    if data_dict_path.exists():
        cache_mgr.register_file(
            str(data_dict_path),
            on_change=lambda: refresh_data_dictionary_cache(None)
        )
        logger.info("Watching default data dictionary file")


def check_and_refresh_caches() -> List[str]:
    """
    Check all watched files and refresh caches as needed.
    
    Call this periodically or before processing requests.
    
    Returns:
        List of files that triggered cache refresh
    """
    cache_mgr = get_cache_manager()
    changed = cache_mgr.check_all()
    
    for file_path in changed:
        cache_mgr.mark_refreshed(file_path)
    
    return changed
