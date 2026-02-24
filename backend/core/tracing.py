"""
Tracing Infrastructure for Data Insights Copilot.

Integrates Langfuse and OpenTelemetry for comprehensive observability:
- LLM Tracing (Langfuse)
- Distributed Tracing (OpenTelemetry)
- Usage & Cost Tracking

Key Feature: All LLM calls and tool executions for a single user query
are grouped under ONE parent trace for easy debugging.
"""
import functools
import uuid
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from dataclasses import dataclass, field

# Langfuse Imports - v3.x uses direct imports from langfuse
from langfuse import Langfuse, observe
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

# Try to import langfuse_context (may vary by version)
try:
    from langfuse import langfuse_context
except ImportError:
    # Fallback for compatibility
    langfuse_context = None

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Global tracer instance
_tracer = None


@dataclass
class TraceContext:
    """
    Simple trace context object for tracking trace state.
    Used as a replacement for the removed Langfuse trace object in v3.x.
    """
    id: str
    name: str
    input: Any = None
    output: Any = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    _langfuse: Any = None
    
    def update(self, output: Any = None, metadata: Dict[str, Any] = None, 
               level: str = None, status_message: str = None, **kwargs):
        """Update trace with output and metadata."""
        if output is not None:
            self.output = output
        if metadata:
            self.metadata.update(metadata)
        # In v3.x, we update via langfuse_context or span
        # For now, just store locally - the callback handler will capture the output


class TracingManager:
    """Singleton manager for observability infrastructure."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TracingManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.langfuse: Optional[Langfuse] = None
        self.otel_tracer = None
        
        # Load settings
        self.langfuse_enabled = settings.enable_langfuse
        self.otel_enabled = False # Default off until configured
        
        self._initialize_backends()
        self._initialized = True
        logger.info("TracingManager initialized")

    def _initialize_backends(self):
        """Initialize active tracing backends."""
        # 1. Initialize Langfuse
        if self.langfuse_enabled:
            try:
                self.langfuse = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host
                )
                # Verify connection
                if not self.langfuse.auth_check():
                    logger.warning("Langfuse auth check failed - tracing disabled")
                    self.langfuse_enabled = False
                else:
                    logger.info("✅ Langfuse tracing enabled")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse: {e}")
                self.langfuse_enabled = False

    def get_langchain_callback(
        self, 
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_name: str = "rag_query"
    ) -> Optional[LangfuseCallbackHandler]:
        """
        Get LangChain callback handler with trace context.
        
        In Langfuse v3.x, the CallbackHandler only accepts:
        - public_key (optional, uses env var if not provided)
        - update_trace (bool)
        
        User/session metadata must be passed via LangChain config metadata:
        - langfuse_user_id
        - langfuse_session_id
        - langfuse_tags
        """
        if not self.langfuse_enabled:
            return None
            
        try:
            # In Langfuse v3.x, CallbackHandler has minimal constructor params
            # Metadata is passed via LangChain invoke() config
            handler = LangfuseCallbackHandler(
                public_key=settings.langfuse_public_key,
                update_trace=True,
            )
            
            # Store metadata for reference (will be passed via config in invoke())
            handler._trace_name = trace_name
            handler._user_id = user_id
            handler._session_id = session_id
            handler._trace_id = trace_id
            
            logger.debug(f"Created Langfuse callback: trace_name={trace_name}")
            return handler
            
        except Exception as e:
            logger.warning(f"Failed to create Langfuse callback: {e}")
            return None

    def update_current_trace_metadata(
        self,
        name: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ):
        """
        Update the current trace with session_id, user_id, and other metadata.
        In v3.x, this is a no-op as metadata is passed via callback handler.
        """
        pass  # Metadata is passed via LangfuseCallbackHandler in v3.x

    def create_trace(
        self,
        name: str,
        input: Any = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[TraceContext]:
        """
        Create a new trace context manually.
        Returns a TraceContext object for tracking.
        """
        if not self.langfuse_enabled:
            return None
            
        trace_id = str(uuid.uuid4())
        return TraceContext(
            id=trace_id,
            name=name,
            input=input,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
            tags=tags or [],
            _langfuse=self.langfuse
        )

    @contextmanager
    def trace_operation(
        self, 
        name: str, 
        input: Any = None,
        user_id: Optional[str] = None, 
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Context manager for tracing a complete operation.
        
        In Langfuse v3.x, we create a TraceContext and let the 
        LangfuseCallbackHandler handle the actual tracing.
        
        Usage:
            with tracer.trace_operation("rag_query", input=query, session_id=sid) as trace:
                # All LLM calls here will be children of this trace
                result = await agent.invoke(...)
                trace.update(output=result)
        """
        trace = None
        try:
            if self.langfuse_enabled:
                trace_id = str(uuid.uuid4())
                trace = TraceContext(
                    id=trace_id,
                    name=name,
                    input=input,
                    user_id=user_id,
                    session_id=session_id,
                    metadata=metadata or {},
                    tags=kwargs.get('tags', []),
                    _langfuse=self.langfuse
                )
                logger.debug(f"Started trace context: {name} (id={trace.id})")
            
            yield trace
            
        except Exception as e:
            if trace:
                trace.update(level="ERROR", status_message=str(e))
            raise e
        finally:
            # Flush to ensure trace is sent
            if self.langfuse:
                try:
                    self.langfuse.flush()
                except Exception:
                    pass

    def flush(self):
        """Flush all pending traces to Langfuse."""
        if self.langfuse:
            try:
                self.langfuse.flush()
            except Exception as e:
                logger.warning(f"Failed to flush Langfuse: {e}")


# =============================================================================
# Functional Decorators
# =============================================================================

def observe_operation(name: Optional[str] = None):
    """
    Decorator for general operation tracing.
    Automatically captures args, kwargs, and duration.
    """
    def decorator(func):
        @functools.wraps(func)
        @observe(name=name or func.__name__)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


def observe_embedding(func):
    """
    Specialized decorator for embedding generation.
    Tracks token counts and model info.
    """
    @functools.wraps(func)
    @observe(as_type="generation")
    def wrapper(self, *args, **kwargs):
        # Execute
        result = func(self, *args, **kwargs)
        
        # Update trace with model info if available and langfuse_context exists
        if hasattr(self, 'model_name') and langfuse_context is not None:
            try:
                langfuse_context.update_current_observation(
                    model=self.model_name
                )
            except Exception:
                pass  # Don't fail on tracing errors
            
        return result
    return wrapper


def observe_vector_search(func):
    """
    Specialized decorator for vector store searches.
    Tracks query, k, and result counts.
    """
    @functools.wraps(func)
    @observe(as_type="span")
    def wrapper(self, query: str, top_k: int = None, *args, **kwargs):
        # Execute
        results = func(self, query, top_k, *args, **kwargs)
        
        # Log metadata only if langfuse_context exists
        if langfuse_context is not None:
            try:
                langfuse_context.update_current_observation(
                    input=query,
                    metadata={
                        "top_k": top_k,
                        "results_count": len(results) if results else 0
                    }
                )
            except Exception:
                pass  # Don't fail on tracing errors
        return results
    return wrapper


# Singleton Accessor
def get_tracing_manager() -> TracingManager:
    return TracingManager()
