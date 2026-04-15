"""
FastAPI application entry point.

This module initializes the FastAPI application with all middleware,
routers, and lifecycle handlers.
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
# Change the path to load a different .env file (e.g., ".env.production", ".env.local")
_env_file = os.getenv("ENV_FILE", ".env")
_env_path = Path(__file__).parent.parent / _env_file
load_dotenv(_env_path, override=True)

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.database.connection import DatabaseConfig, init_database
from app.core.utils.logging import configure_logging, get_logger, bind_context, clear_context
from app.core.utils.tracing import configure_tracing, instrument_app
from app.core.utils.exceptions import AppException

# Configure logging first
settings = get_settings()
configure_logging(
    log_level="DEBUG" if settings.debug else "INFO",
    json_logs=not settings.debug
)

logger = get_logger(__name__)


# ============================================
# Application Lifespan
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown:
    - Startup: Initialize database, tracing, etc.
    - Shutdown: Close connections, cleanup resources
    """
    logger.info("Starting application", version=settings.version)
    
    # Initialize database
    try:
        db_config = DatabaseConfig.from_env(settings)
        db = init_database(db_config)
        await db.connect()
        logger.info("Database connected", database=settings.postgres_db)
        
        # Note: Run 'alembic upgrade head' to apply migrations
        # For development, you can enable auto-create tables below:
        # from app.core.database.connection import create_tables
        # await create_tables()
    except Exception as e:
        logger.error("Failed to connect to database", error=str(e))
        raise
    
    # Configure tracing (if enabled)
    if settings.debug:
        configure_tracing(
            service_name=settings.project_name,
            enable_console=True
        )
        logger.info("Tracing configured for development")
    
    logger.info("Application startup complete")
    
    yield  # Application is running
    
    # Shutdown
    logger.info("Shutting down application")
    
    try:
        await db.disconnect()
        logger.info("Database disconnected")
    except Exception as e:
        logger.error("Error during database shutdown", error=str(e))
    
    logger.info("Application shutdown complete")


# ============================================
# FastAPI Application
# ============================================

app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description=f"{settings.project_name} - Healthcare data insights with RAG",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ============================================
# Middleware
# ============================================

# CORS - must be added before other middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Trusted hosts (optional security)
if not settings.debug:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure this in production
    )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests with context."""
    # Generate request ID
    request_id = request.headers.get("X-Request-ID", str(id(request)))
    
    # Bind context for this request
    bind_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path
    )
    
    # Log request immediately when received (before processing)
    logger.info(
        "Request received",
        method=request.method,
        path=request.url.path
    )
    
    # Flush to ensure log is written immediately
    sys.stdout.flush()
    
    try:
        response = await call_next(request)
        
        logger.info(
            "Request completed",
            status_code=response.status_code
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
    except Exception as e:
        # Log any unhandled exceptions that would otherwise crash silently
        logger.error(
            "Request crashed",
            error=str(e),
            error_type=type(e).__name__
        )
        sys.stdout.flush()
        raise
    finally:
        clear_context()


# ============================================
# Exception Handlers
# ============================================

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions."""
    logger.error(
        "Application exception",
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions."""
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "HTTP_ERROR",
            "message": exc.detail,
            "details": {}
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    # Sanitize errors to ensure they are JSON serializable
    sanitized_errors = []
    for error in exc.errors():
        sanitized_error = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input"),
        }
        # Convert ctx values to strings if they contain non-serializable objects
        if "ctx" in error and error["ctx"]:
            sanitized_error["ctx"] = {
                k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
                for k, v in error["ctx"].items()
            }
        sanitized_errors.append(sanitized_error)
    
    logger.warning("Validation error", errors=sanitized_errors)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"errors": sanitized_errors}
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(
        "Unexpected exception",
        error=str(exc),
        error_type=type(exc).__name__,
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": {"error": str(exc)} if settings.debug else {}
        }
    )


# ============================================
# Health Check
# ============================================

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns application status and dependencies health.
    """
    from app.core.database.connection import get_database
    
    db = get_database()
    db_healthy = await db.health_check() if db else False
    
    return {
        "status": "healthy" if db_healthy else "degraded",
        "version": settings.version,
        "dependencies": {
            "database": "healthy" if db_healthy else "unhealthy"
        }
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "FHIR RAG API",
        "version": settings.version,
        "docs": "/api/docs"
    }


# ============================================
# Router Registration
# ============================================

# Users & Authentication
from app.modules.users.auth_routes import router as auth_router
from app.modules.users.routes import router as users_router

app.include_router(auth_router, prefix=f"{settings.api_v1_prefix}/auth", tags=["Authentication"])
app.include_router(users_router, prefix=f"{settings.api_v1_prefix}/users", tags=["Users"])

# Observability & Audit
from app.modules.audit.routes import router as audit_router
from app.modules.observability.analytics_routes import router as analytics_router

# Agents and Configs
from app.modules.agents.routes import router as agents_router

# Data Sources
from app.modules.data_sources.routes import router as data_sources_router
from app.modules.data_sources.ingestion_routes import router as ingestion_router

# AI Models Registry
from app.modules.ai_models.routes import router as ai_registry_router

app.include_router(audit_router, prefix=f"{settings.api_v1_prefix}", tags=["Audit"])
app.include_router(analytics_router, prefix=f"{settings.api_v1_prefix}", tags=["Analytics"])
# Note: agents_router already has /agents, /config prefixes and tags internally
app.include_router(agents_router, prefix=f"{settings.api_v1_prefix}")
# Note: data_sources_router already has /data-sources prefix and tags internally
app.include_router(data_sources_router, prefix=f"{settings.api_v1_prefix}")
# Ingestion - compatibility layer for frontend (/ingestion/*)
app.include_router(ingestion_router, prefix=f"{settings.api_v1_prefix}")
# AI Registry - flexible provider/model management
app.include_router(ai_registry_router, prefix=f"{settings.api_v1_prefix}")

# Embeddings - job management and progress tracking
from app.modules.embeddings.routes import router as embeddings_router
from app.modules.embeddings.websocket import router as embeddings_ws_router
from app.modules.embeddings.schema_routes import router as schema_router
app.include_router(embeddings_router, prefix=f"{settings.api_v1_prefix}", tags=["Embedding Jobs"])
app.include_router(embeddings_ws_router, prefix=f"{settings.api_v1_prefix}/ws", tags=["WebSocket"])
app.include_router(schema_router, prefix=f"{settings.api_v1_prefix}", tags=["Schema Vectorization"])

# Chat - RAG query processing
from app.modules.chat.routes import router as chat_router

# Training - SQL examples management for few-shot learning
from app.modules.sql_examples.routes import router as training_router
from app.modules.sql_examples.few_shot_routes import router as fewshot_router
from app.modules.chat.context_routes import router as context_router
from app.modules.chat.sql_executor_routes import router as sql_executor_router
app.include_router(chat_router, prefix=f"{settings.api_v1_prefix}", tags=["Chat"])
app.include_router(training_router, prefix=f"{settings.api_v1_prefix}", tags=["Training"])
app.include_router(fewshot_router, prefix=f"{settings.api_v1_prefix}", tags=["Few-Shot Examples"])
app.include_router(context_router, prefix=f"{settings.api_v1_prefix}", tags=["Context Orchestration"])
app.include_router(sql_executor_router, prefix=f"{settings.api_v1_prefix}", tags=["SQL Execution"])


# ============================================
# Instrument for Tracing
# ============================================

if settings.debug:
    instrument_app(app)


# ============================================
# Application Info
# ============================================

logger.info(
    "FastAPI application configured",
    debug=settings.debug,
    api_prefix=settings.api_v1_prefix,
    cors_origins=settings.cors_origins_list
)
