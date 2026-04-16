"""
Request cancellation utilities.

Provides utilities for handling request cancellation, timeouts,
and graceful shutdown of long-running operations.
"""
import asyncio
from typing import Optional, Callable, Any
from contextlib import asynccontextmanager
from functools import wraps

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from app.core.utils.logging import get_logger
from app.core.utils.exceptions import AppException

logger = get_logger(__name__)


class CancellationError(AppException):
    """Raised when an operation is cancelled."""
    def __init__(self, message: str = "Operation cancelled", **kwargs):
        super().__init__(
            message=message,
            status_code=499,  # Client Closed Request
            error_code="OPERATION_CANCELLED",
            **kwargs
        )


class TimeoutError(AppException):
    """Raised when an operation times out."""
    def __init__(self, message: str = "Operation timed out", timeout: Optional[float] = None, **kwargs):
        details = {}
        if timeout:
            details["timeout_seconds"] = timeout
        
        super().__init__(
            message=message,
            status_code=408,  # Request Timeout
            error_code="OPERATION_TIMEOUT",
            details=details,
            **kwargs
        )


async def check_cancellation(request: Request) -> None:
    """
    Check if the client has disconnected.
    
    Args:
        request: FastAPI request object
    
    Raises:
        CancellationError: If client has disconnected
    
    Usage:
        @router.post("/long-operation")
        async def long_operation(request: Request):
            for i in range(100):
                await check_cancellation(request)
                await do_work()
    """
    if await request.is_disconnected():
        logger.info("Client disconnected, cancelling operation")
        raise CancellationError("Client disconnected")


@asynccontextmanager
async def timeout_context(seconds: float):
    """
    Context manager for operation timeout.
    
    Args:
        seconds: Timeout duration in seconds
    
    Raises:
        TimeoutError: If operation exceeds timeout
    
    Usage:
        async with timeout_context(30.0):
            result = await long_operation()
    """
    try:
        async with asyncio.timeout(seconds):
            yield
    except asyncio.TimeoutError:
        logger.warning(f"Operation timed out after {seconds}s")
        raise TimeoutError(f"Operation timed out after {seconds}s", timeout=seconds)


def with_timeout(seconds: float):
    """
    Decorator to add timeout to async functions.
    
    Args:
        seconds: Timeout duration in seconds
    
    Usage:
        @with_timeout(30.0)
        async def fetch_data():
            await slow_operation()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with timeout_context(seconds):
                return await func(*args, **kwargs)
        return wrapper
    return decorator


@asynccontextmanager
async def cancellable_operation(request: Request, check_interval: float = 0.5):
    """
    Context manager for cancellable operations.
    
    Periodically checks if client has disconnected and raises CancellationError.
    
    Args:
        request: FastAPI request object
        check_interval: How often to check for cancellation (seconds)
    
    Raises:
        CancellationError: If client disconnects
    
    Usage:
        @router.post("/process")
        async def process(request: Request):
            async with cancellable_operation(request):
                result = await long_process()
            return result
    """
    # Start background task to check for disconnection
    cancel_event = asyncio.Event()
    
    async def check_disconnect():
        while not cancel_event.is_set():
            if await request.is_disconnected():
                cancel_event.set()
                logger.info("Client disconnected during operation")
                return
            await asyncio.sleep(check_interval)
    
    check_task = asyncio.create_task(check_disconnect())
    
    try:
        yield
    finally:
        cancel_event.set()
        check_task.cancel()
        try:
            await check_task
        except asyncio.CancelledError:
            pass
    
    # Raise if cancelled
    if cancel_event.is_set():
        raise CancellationError("Client disconnected during operation")


class CancellationToken:
    """
    Token for checking cancellation state.
    
    Can be passed to long-running operations to allow graceful cancellation.
    
    Usage:
        token = CancellationToken()
        
        async def long_operation(token: CancellationToken):
            for i in range(1000):
                token.check()  # Raises if cancelled
                await do_work()
        
        # Cancel from another task
        token.cancel()
    """
    
    def __init__(self):
        self._cancelled = False
        self._reason: Optional[str] = None
    
    def cancel(self, reason: str = "Operation cancelled") -> None:
        """
        Cancel the operation.
        
        Args:
            reason: Reason for cancellation
        """
        self._cancelled = True
        self._reason = reason
        logger.info(f"Cancellation requested: {reason}")
    
    def is_cancelled(self) -> bool:
        """Check if operation is cancelled."""
        return self._cancelled
    
    def check(self) -> None:
        """
        Check if cancelled and raise if so.
        
        Raises:
            CancellationError: If operation is cancelled
        """
        if self._cancelled:
            raise CancellationError(self._reason or "Operation cancelled")
    
    async def check_async(self) -> None:
        """Async version of check() - allows for async cancellation checks."""
        self.check()


async def run_with_cancellation(
    func: Callable,
    token: CancellationToken,
    *args,
    **kwargs
) -> Any:
    """
    Run a function with cancellation support.
    
    Args:
        func: Function to run (sync or async)
        token: Cancellation token
        *args: Function arguments
        **kwargs: Function keyword arguments
    
    Returns:
        Function result
    
    Raises:
        CancellationError: If operation is cancelled
    """
    if asyncio.iscoroutinefunction(func):
        # Async function
        result = await func(*args, **kwargs, token=token)
    else:
        # Sync function - run in thread pool
        result = await run_in_threadpool(func, *args, **kwargs, token=token)
    
    return result


@asynccontextmanager
async def shutdown_handler():
    """
    Context manager for graceful shutdown handling.
    
    Usage:
        async with shutdown_handler():
            # Your startup code
            await database.connect()
        
        # On shutdown, cleanup happens here
        await database.disconnect()
    """
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        shutdown_event.set()
    
    # Register signal handlers
    import signal
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        yield shutdown_event
    finally:
        logger.info("Executing shutdown cleanup")
