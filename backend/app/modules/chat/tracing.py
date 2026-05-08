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
        logger.info("Langfuse tracing disabled (ENABLE_LANGFUSE=false or missing API keys)")
        return None
    
    try:
        from langfuse import Langfuse
        
        # Prefer base_url over host for consistency
        host_url = settings.langfuse_base_url or settings.langfuse_host
        
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=host_url,
        )
        
        logger.info("Langfuse client initialized", host=host_url)
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
            
            # LLM calls with get_llm_config() will be linked to this trace
            config = ctx.get_llm_config()
            result = await llm.ainvoke(prompt, config=config)
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
        self._trace_context = None  # For SDK v3
        self._spans: Dict[str, Any] = {}
        self._callback_handler = None
    
    def __enter__(self):
        """Start the trace and set as current context for child observations."""
        if self._langfuse:
            try:
                # SDK v3: Create a root span first
                start_span_fn = getattr(self._langfuse, 'start_span', None)
                if start_span_fn:
                    # Create the root span
                    self._trace = start_span_fn(
                        name=self.name,
                        input={"query_preview": self.metadata.get("query_preview")},
                        metadata={
                            **self.metadata,
                            "user_id": self.user_id,
                            "session_id": self.session_id,
                            "trace_id": self.trace_id,
                        },
                    )
                    
                    # Update trace metadata for proper session/user tracking
                    # This ensures all traces with same session_id are grouped
                    if hasattr(self._trace, 'update_trace'):
                        self._trace.update_trace(
                            session_id=self.session_id,
                            user_id=self.user_id,
                            name=self.name,
                            input={"query": self.metadata.get("query_preview")},
                        )
                    
                    logger.debug(f"Started trace (v3): {self.trace_id}, session: {self.session_id}")
                else:
                    # Fallback: SDK v2 uses .trace()
                    trace_fn = getattr(self._langfuse, 'trace', None)
                    if trace_fn:
                        self._trace = trace_fn(
                            id=self.trace_id,
                            name=self.name,
                            user_id=self.user_id,
                            session_id=self.session_id,
                            metadata=self.metadata,
                        )
                        logger.debug(f"Started trace (v2): {self.trace_id}")
                    else:
                        logger.debug("No compatible Langfuse trace method found")
            except Exception as e:
                logger.warning(f"Failed to start trace: {e}")
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the trace context.
        
        NOTE: We do NOT end the span here because async operations (like follow-up
        generation) may still be adding observations. Call end_trace() explicitly
        after all async operations complete, or let the trace end naturally via
        the Langfuse callback handler.
        """
        if self._trace:
            try:
                if exc_type:
                    # Update with error info but don't end - async tasks may still run
                    if hasattr(self._trace, 'update'):
                        self._trace.update(
                            output={"error": str(exc_val)},
                            level="ERROR",
                        )
                # Don't end the span here - let end_trace() or callback handler do it
                
                self._langfuse.flush()
            except Exception as e:
                logger.warning(f"Failed to end trace: {e}")
        
        return False  # Don't suppress exceptions
    
    def set_trace_output(self, output: Any, answer_preview: str = None):
        """
        Set the final output on the main trace.
        
        Args:
            output: Output data (dict or any serializable)
            answer_preview: Short preview of the answer for display
        """
        if not self._trace:
            return
        
        try:
            # SDK v3: update the trace with output
            if hasattr(self._trace, 'update'):
                self._trace.update(output=output)
            
            # Also update the trace metadata with answer preview
            if answer_preview and hasattr(self._trace, 'update_trace'):
                self._trace.update_trace(
                    output={"answer": answer_preview[:500] if answer_preview else None}
                )
        except Exception as e:
            logger.warning(f"Failed to set trace output: {e}")
    
    def end_trace(self, output: Any = None, level: str = "DEFAULT"):
        """
        Explicitly end the trace span.
        
        Call this after all async operations (like follow-up generation) are complete.
        This ensures the parent span's end time reflects when all work finished.
        
        Args:
            output: Optional final output data
            level: Log level (DEFAULT, DEBUG, WARNING, ERROR)
        """
        if not self._trace:
            return
        
        try:
            # End all open child spans first
            for name, span in list(self._spans.items()):
                try:
                    if hasattr(span, 'end'):
                        span.end()
                except Exception:
                    pass
            self._spans.clear()
            
            # End the main trace span
            if hasattr(self._trace, 'end'):
                end_kwargs = {}
                if output is not None:
                    end_kwargs["output"] = output
                if level != "DEFAULT":
                    end_kwargs["level"] = level
                self._trace.end(**end_kwargs)
            
            # Flush to ensure data is sent
            self.flush()
            logger.debug(f"Trace ended: {self.trace_id}")
        except Exception as e:
            logger.warning(f"Failed to end trace: {e}")
    
    
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
            # SDK v3: use parent span's start_span() method
            if hasattr(self._trace, 'start_span'):
                span = self._trace.start_span(
                    name=name,
                    input=input,
                    metadata=metadata,
                )
            elif hasattr(self._trace, 'span'):
                # SDK v2 fallback
                span = self._trace.span(
                    name=name,
                    input=input,
                    metadata=metadata,
                )
            else:
                return None
                
            span_id = getattr(span, 'id', name)
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
    
    def add_generation(
        self,
        name: str,
        model: str,
        input: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Add an LLM generation to the current trace.
        
        Use this for LLM API calls to capture model, tokens, and cost.
        
        Args:
            name: Generation name (e.g., "sql_generation", "intent_classification")
            model: Model name (e.g., "gpt-4o", "gpt-4o-mini")
            input: Input prompt/messages
            metadata: Additional metadata
            
        Returns:
            Generation ID or None if tracing disabled
        """
        if not self._trace:
            return None
        
        try:
            # SDK v3: use start_generation for LLM calls
            if hasattr(self._trace, 'start_generation'):
                gen = self._trace.start_generation(
                    name=name,
                    model=model,
                    input=input,
                    metadata=metadata,
                )
            elif hasattr(self._trace, 'generation'):
                # SDK v2 fallback
                gen = self._trace.generation(
                    name=name,
                    model=model,
                    input=input,
                    metadata=metadata,
                )
            else:
                # Fall back to span
                return self.add_span(name, input=input, metadata=metadata)
            
            gen_id = getattr(gen, 'id', name)
            self._spans[name] = gen
            return gen_id
        except Exception as e:
            logger.warning(f"Failed to add generation {name}: {e}")
            return None
    
    def end_generation(
        self,
        name: str,
        output: Any = None,
        model: Optional[str] = None,
        usage: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        End an LLM generation with output and usage info.
        
        Args:
            name: Generation name
            output: LLM output/completion
            model: Model name (if different from start)
            usage: Token usage dict with 'input', 'output', 'total' keys
            metadata: Additional metadata
        """
        gen = self._spans.pop(name, None)
        if gen:
            try:
                end_kwargs = {"output": output}
                if model:
                    end_kwargs["model"] = model
                if usage:
                    end_kwargs["usage"] = usage
                if metadata:
                    end_kwargs["metadata"] = metadata
                
                gen.end(**end_kwargs)
            except Exception as e:
                logger.warning(f"Failed to end generation {name}: {e}")
    
    def get_langchain_callback(self):
        """
        Get a LangChain callback handler for this trace.
        
        Returns callback handler that sends LangChain events to Langfuse.
        This automatically captures LLM calls, tokens, and costs.
        """
        if not self._langfuse:
            return None
        
        if self._callback_handler:
            return self._callback_handler
        
        try:
            # SDK v3: use langfuse.langchain.CallbackHandler
            from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
            
            # Create handler - it will use env vars for auth
            # update_trace=True allows updating existing trace metadata
            self._callback_handler = LangfuseCallbackHandler(update_trace=True)
            
            logger.debug(f"Created LangChain callback handler")
            return self._callback_handler
            
        except ImportError:
            logger.debug("langfuse.langchain not available")
            return None
        except Exception as e:
            logger.warning(f"Failed to create callback handler: {e}")
            return None
    
    def get_llm_config(self) -> Optional[Dict[str, Any]]:
        """
        Get LangChain config dict with Langfuse callbacks and metadata.
        
        Use this when calling LLM.ainvoke() to capture token usage and costs,
        and link the LLM call to the current session/user.
        
            config = tracing_ctx.get_llm_config()
            result = await llm.ainvoke(prompt, config=config)
        
        Returns:
            Config dict with callbacks and metadata, or None if tracing disabled
        """
        callback = self.get_langchain_callback()
        if callback:
            # Include metadata for session/user linking
            # Langfuse SDK reads langfuse_session_id and langfuse_user_id from metadata
            return {
                "callbacks": [callback],
                "metadata": {
                    "langfuse_session_id": self.session_id,
                    "langfuse_user_id": self.user_id,
                    "trace_id": self.trace_id,
                }
            }
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
