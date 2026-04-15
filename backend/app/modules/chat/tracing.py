"""
LLM Tracing integration for chat service.

Provides Langfuse integration for:
- Request tracing with spans
- LLM call monitoring
- Performance metrics
"""
import uuid
from typing import Optional, Any, Dict
from contextlib import contextmanager

from app.core.utils.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)

# Global Langfuse client
_langfuse_client = None


def get_langfuse_client():
    """Get or create the Langfuse client singleton."""
    global _langfuse_client
    
    if _langfuse_client is not None:
        return _langfuse_client
    
    settings = get_settings()
    
    if not settings.langfuse_enabled:
        logger.info("Langfuse tracing disabled (no API keys configured)")
        return None
    
    try:
        from langfuse import Langfuse
        
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        
        logger.info("Langfuse client initialized", host=settings.langfuse_host)
        return _langfuse_client
        
    except ImportError:
        logger.warning("langfuse package not installed")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        return None


def generate_trace_id() -> str:
    """
    Generate a Langfuse-compatible trace ID.
    
    Langfuse requires 32 lowercase hex characters (no dashes).
    """
    return uuid.uuid4().hex


class TracingContext:
    """
    Context manager for tracing a chat request.
    
    Usage:
        with TracingContext("chat_request", user_id=user_id) as ctx:
            ctx.add_span("embedding", input=query)
            # ... do work
            ctx.update_span("embedding", output=results)
    """
    
    def __init__(
        self,
        name: str,
        trace_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize a tracing context.
        
        Args:
            name: Name of the trace (e.g., "chat_request")
            trace_id: Optional trace ID (generated if not provided)
            user_id: User identifier
            session_id: Chat session ID
            metadata: Additional metadata to attach
        """
        self.name = name
        self.trace_id = trace_id or generate_trace_id()
        self.user_id = user_id
        self.session_id = session_id
        self.metadata = metadata or {}
        
        self._langfuse = get_langfuse_client()
        self._trace = None
        self._spans: Dict[str, Any] = {}
        self._callback_handler = None
    
    def __enter__(self):
        """Start the trace."""
        if self._langfuse:
            try:
                self._trace = self._langfuse.trace(
                    id=self.trace_id,
                    name=self.name,
                    user_id=self.user_id,
                    session_id=self.session_id,
                    metadata=self.metadata,
                )
                logger.debug(f"Started trace: {self.trace_id}")
            except Exception as e:
                logger.warning(f"Failed to start trace: {e}")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the trace and flush."""
        if self._trace:
            try:
                if exc_type:
                    self._trace.update(
                        output={"error": str(exc_val)},
                        level="ERROR",
                    )
                self._langfuse.flush()
            except Exception as e:
                logger.warning(f"Failed to end trace: {e}")
        
        return False  # Don't suppress exceptions
    
    def add_span(
        self,
        name: str,
        input: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Add a span to the current trace.
        
        Args:
            name: Span name (e.g., "embedding", "vector_search", "llm_generate")
            input: Input data for the span
            metadata: Additional metadata
            
        Returns:
            Span ID or None if tracing disabled
        """
        if not self._trace:
            return None
        
        try:
            span = self._trace.span(
                name=name,
                input=input,
                metadata=metadata,
            )
            span_id = span.id if hasattr(span, 'id') else name
            self._spans[name] = span
            return span_id
        except Exception as e:
            logger.warning(f"Failed to add span {name}: {e}")
            return None
    
    def update_span(
        self,
        name: str,
        output: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: str = "DEFAULT",
    ):
        """
        Update a span with output.
        
        Args:
            name: Span name
            output: Output data
            metadata: Additional metadata
            level: Log level (DEFAULT, DEBUG, WARNING, ERROR)
        """
        span = self._spans.get(name)
        if span:
            try:
                span.update(
                    output=output,
                    metadata=metadata,
                    level=level,
                )
            except Exception as e:
                logger.warning(f"Failed to update span {name}: {e}")
    
    def end_span(self, name: str):
        """End a span."""
        span = self._spans.pop(name, None)
        if span:
            try:
                span.end()
            except Exception:
                pass
    
    def get_langchain_callback(self):
        """
        Get a LangChain callback handler for this trace.
        
        Returns callback handler that sends LangChain events to Langfuse.
        """
        if not self._langfuse or not self._trace:
            return None
        
        if self._callback_handler:
            return self._callback_handler
        
        try:
            from langfuse.callback import CallbackHandler as LangfuseCallbackHandler
            
            self._callback_handler = LangfuseCallbackHandler(
                trace_id=self.trace_id,
                user_id=self.user_id,
                session_id=self.session_id,
            )
            return self._callback_handler
            
        except ImportError:
            logger.debug("langfuse.callback not available")
            return None
        except Exception as e:
            logger.warning(f"Failed to create callback handler: {e}")
            return None
    
    def flush(self):
        """Flush traces to Langfuse."""
        if self._langfuse:
            try:
                self._langfuse.flush()
            except Exception:
                pass
        
        if self._callback_handler:
            try:
                self._callback_handler.flush()
            except Exception:
                pass


@contextmanager
def trace_chat_request(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    query: Optional[str] = None,
):
    """
    Convenience context manager for tracing a chat request.
    
    Usage:
        with trace_chat_request(user_id="123", query="How many...") as ctx:
            # Do chat processing
            pass
    """
    ctx = TracingContext(
        name="chat_request",
        user_id=user_id,
        session_id=session_id,
        metadata={
            "agent_id": agent_id,
            "query_preview": query[:100] if query else None,
        },
    )
    
    with ctx:
        yield ctx
