"""
Tracing Infrastructure for Data Insights Copilot.

Integrates Langfuse and OpenTelemetry for comprehensive observability:
- LLM Tracing (Langfuse)
- Distributed Tracing (OpenTelemetry)
- Usage & Cost Tracking
"""
import os
import functools
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

# Langfuse Imports
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

# OpenTelemetry Imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

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

    def get_langchain_callback(self) -> Optional[LangfuseCallbackHandler]:
        """Get LangChain callback handler if enabled."""
        if self.langfuse_enabled:
            return LangfuseCallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host
            )
        return None

    @contextmanager
    def trace_operation(self, name: str, **kwargs):
        """
        Context manager for tracing generic operations.
        Wraps both Langfuse and OTEL spans.
        """
        span = None
        try:
            # Start Langfuse span
            if self.langfuse_enabled:
                span = langfuse_context.update_current_trace(
                    name=name,
                    **kwargs
                )
            
            yield span
            
        except Exception as e:
            if self.langfuse_enabled:
                langfuse_context.update_current_observation(
                    level="ERROR",
                    status_message=str(e)
                )
            raise e


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
        # Extract input text to count tokens (estimation)
        texts = []
        if args:
            texts = args[0] if isinstance(args[0], list) else [args[0]]
        
        # Execute
        start_time = os.times()
        result = func(self, *args, **kwargs)
        
        # Update trace with model info if available
        if hasattr(self, 'model_name'):
             langfuse_context.update_current_observation(
                model=self.model_name
            )
            
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
        
        # Log metadata
        langfuse_context.update_current_observation(
            input=query,
            metadata={
                "top_k": top_k,
                "results_count": len(results) if results else 0
            }
        )
        return results
    return wrapper


# Singleton Accessor
def get_tracing_manager() -> TracingManager:
    return TracingManager()
