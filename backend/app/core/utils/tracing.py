"""
Distributed tracing with OpenTelemetry.

Provides integration for tracing requests across the application
and external services (databases, LLMs, vector stores).
"""
from typing import Optional
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


def configure_tracing(
    service_name: str = "fhir-rag-api",
    otlp_endpoint: Optional[str] = None,
    enable_console: bool = False
) -> TracerProvider:
    """
    Configure OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service for traces
        otlp_endpoint: OTLP collector endpoint (e.g., "http://localhost:4317")
        enable_console: Whether to print traces to console (useful for debugging)
    
    Returns:
        TracerProvider instance
    """
    # Create resource with service name
    resource = Resource(attributes={
        SERVICE_NAME: service_name
    })
    
    # Create tracer provider
    provider = TracerProvider(resource=resource)
    
    # Add span processors
    if otlp_endpoint:
        # Send to OTLP collector (e.g., Jaeger, Tempo, Honeycomb)
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(f"OTLP tracing configured", endpoint=otlp_endpoint)
    
    if enable_console:
        # Console output for debugging
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("Console tracing enabled")
    
    # Set as global tracer provider
    trace.set_tracer_provider(provider)
    
    return provider


def instrument_app(app):
    """
    Instrument FastAPI application with automatic tracing.
    
    Args:
        app: FastAPI application instance
    
    Usage:
        app = FastAPI()
        instrument_app(app)
    """
    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Instrument HTTP clients
    HTTPXClientInstrumentor().instrument()
    
    # SQLAlchemy instrumentation will be added when engine is created
    # via instrument_sqlalchemy_engine()
    
    logger.info("Application instrumented for tracing")


def instrument_sqlalchemy_engine(engine):
    """
    Instrument SQLAlchemy engine for database tracing.
    
    Args:
        engine: SQLAlchemy engine instance
    
    Usage:
        from app.core.database.connection import get_database
        db = get_database()
        instrument_sqlalchemy_engine(db.engine)
    """
    SQLAlchemyInstrumentor().instrument(engine=engine)
    logger.info("SQLAlchemy engine instrumented for tracing")


def get_tracer(name: str = __name__) -> trace.Tracer:
    """
    Get a tracer instance.
    
    Args:
        name: Tracer name (usually __name__)
    
    Returns:
        Tracer instance
    
    Usage:
        tracer = get_tracer(__name__)
        
        with tracer.start_as_current_span("process_data"):
            # Your code here
            pass
    """
    return trace.get_tracer(name)


@contextmanager
def trace_span(name: str, **attributes):
    """
    Context manager for creating a trace span.
    
    Args:
        name: Span name
        **attributes: Additional span attributes
    
    Usage:
        with trace_span("embedding_operation", model="text-embedding-3-small"):
            embeddings = await get_embeddings(text)
    """
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        # Add custom attributes
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span


def add_span_attribute(key: str, value) -> None:
    """
    Add an attribute to the current span.
    
    Args:
        key: Attribute key
        value: Attribute value
    
    Usage:
        add_span_attribute("user_id", user.id)
        add_span_attribute("agent_id", agent_id)
    """
    span = trace.get_current_span()
    if span:
        span.set_attribute(key, value)


def add_span_event(name: str, **attributes) -> None:
    """
    Add an event to the current span.
    
    Args:
        name: Event name
        **attributes: Event attributes
    
    Usage:
        add_span_event("cache_hit", key="user:123")
        add_span_event("llm_tokens_used", input=100, output=50)
    """
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes=attributes)
