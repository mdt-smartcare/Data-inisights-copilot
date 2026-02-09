"""
WebSocket endpoints for real-time updates.
"""
from .embedding_progress import router as embedding_progress_router

__all__ = ["embedding_progress_router"]
