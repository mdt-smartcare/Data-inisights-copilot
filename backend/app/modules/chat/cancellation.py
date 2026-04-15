"""
Request cancellation support for long-running chat operations.

Allows detecting when clients disconnect and cancelling in-progress work.
"""
from typing import Optional
from fastapi import Request

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class RequestCancelled(Exception):
    """Exception raised when a request is cancelled by the client."""
    pass


async def check_cancelled(request: Optional[Request] = None):
    """
    Check if the current request has been cancelled by the client.
    
    Call this periodically during long-running operations to allow
    early termination if the client has disconnected.
    
    Args:
        request: FastAPI Request object
        
    Raises:
        RequestCancelled: If the client has disconnected
    """
    if request is None:
        return
    
    # Check if the client has disconnected
    if await request.is_disconnected():
        logger.info("Client disconnected, cancelling request")
        raise RequestCancelled("Client disconnected")


def is_cancelled(request: Optional[Request] = None) -> bool:
    """
    Non-async check if request is cancelled.
    
    Note: This is a synchronous check and may not be 100% accurate.
    Prefer using check_cancelled() in async code.
    """
    if request is None:
        return False
    
    # For synchronous code, we can't easily check disconnection
    # Return False and rely on async checks
    return False
