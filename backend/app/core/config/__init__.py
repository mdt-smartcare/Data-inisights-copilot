"""
Configuration package.

Re-exports from settings module for backward compatibility.
"""
from app.core.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]