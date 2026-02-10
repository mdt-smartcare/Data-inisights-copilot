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
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

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
        
        # 2. Initialize OpenTelemetry (if configured)
        # Note: We'll add OTEL initialization logic here in future phases
        # when fully integrating the distributed tracing side
        pass

    def get_langchain_callback(
        self, 
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_name: str = "rag_query"
    ) -> Optional[LangfuseCallbackHandler]:
        """
        Get LangChain callback handler with trace context.
        
        This ensures all LLM calls within a single query are grouped
        under one parent trace in Langfuse.
        
        IMPORTANT: In Langfuse v3.x, user_id and session_id must be passed via
        metadata keys in the LangChain config, NOT via the callback handler constructor.
        The SDK looks for these keys in the metadata passed to invoke():
        - langfuse_user_id -> user_id
        - langfuse_session_id -> session_id
        - langfuse_tags -> tags
        
        Args:
            trace_id: Unique identifier for this trace (used for trace_context)
            session_id: Session ID (for reference only - actual value comes from metadata)
            user_id: User identifier (for reference only - actual value comes from metadata)
            trace_name: Name of the parent trace (e.g., "rag_query", "followup_generation")
        
        Returns:
            Configured LangfuseCallbackHandler or None if disabled
        """
        if not self.langfuse_enabled:
            return None
            
        try:
            # In Langfuse v3.x, the CallbackHandler only accepts:
            # - public_key
            # - update_trace (bool)
            # - trace_context (dict with trace_id)
            #
            # user_id and session_id are NOT constructor params.
            # They must be passed via metadata in the LangChain config:
            #   config={"metadata": {"langfuse_user_id": "...", "langfuse_session_id": "..."}}
            #
            # The SDK's _parse_langfuse_trace_attributes_from_metadata() extracts these
            # and sets them on the trace when the root chain starts.
            
            # Build trace_context if trace_id is provided
            trace_context = None
            if trace_id:
                trace_context = {"trace_id": trace_id}
            
            # Create callback handler - user_id/session_id come from metadata in config
            handler = LangfuseCallbackHandler(
                public_key=settings.langfuse_public_key,
                trace_context=trace_context,
                update_trace=True,  # Allow updating the trace with chain input/output/name
            )
            
            # Store metadata on handler for reference (not used by Langfuse, just for debugging)
            handler._session_id = session_id
            handler._user_id = user_id
            handler._trace_name = trace_name
            
            logger.debug(f"Created Langfuse callback: trace_name={trace_name}, trace_context={trace_context}")
            logger.debug(f"Note: user_id={user_id} and session_id={session_id} will be set via langfuse_* metadata keys in LangChain config")
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
        
        Call this after starting a LangChain operation to set trace-level
        attributes that couldn't be set via the callback handler constructor.
        
        Args:
            name: Trace name (e.g., "rag_query")
            session_id: Session ID for grouping conversations
            user_id: User identifier
            metadata: Additional metadata dict
            tags: List of tags for filtering
        """
        if not self.langfuse_enabled or not self.langfuse:
            return
            
        try:
            self.langfuse.update_current_trace(
                name=name,
                session_id=session_id,
                user_id=user_id,
                metadata=metadata,
                tags=tags
            )
            logger.debug(f"Updated current trace: name={name}, session_id={session_id}, user_id={user_id}")
        except Exception as e:
            logger.warning(f"Failed to update current trace: {e}")

    def create_trace(
        self,
        name: str,
        input: Any = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ):
        """
        Create a new Langfuse trace manually.
        
        Use this when you need direct control over the trace lifecycle,
        not via LangChain callbacks.
        
        Returns:
            Langfuse trace object or None if disabled
        """
        if not self.langfuse_enabled or not self.langfuse:
            return None
            
        try:
            trace = self.langfuse.trace(
                name=name,
                input=input,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata or {},
                tags=tags or []
            )
            return trace
        except Exception as e:
            logger.warning(f"Failed to create Langfuse trace: {e}")
            return None

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
        
        Creates a parent trace that can contain child spans.
        All operations within the context will be grouped under this trace.
        
        Usage:
            with tracer.trace_operation("rag_query", input=query, session_id=sid) as trace:
                # All LLM calls here will be children of this trace
                result = await agent.invoke(...)
                trace.update(output=result)
        """
        trace = None
        try:
            if self.langfuse_enabled and self.langfuse:
                trace = self.langfuse.trace(
                    name=name,
                    input=input,
                    user_id=user_id,
                    session_id=session_id,
                    metadata=metadata or {},
                    **kwargs
                )
                logger.debug(f"Started trace: {name} (id={trace.id if trace else 'N/A'})")
            
            yield trace
            
        except Exception as e:
            if trace:
                try:
                    trace.update(
                        level="ERROR",
                        status_message=str(e)
                    )
                except Exception:
                    pass  # Don't fail on tracing errors
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
