"""
FastAPI application entry point.

This module initializes the FastAPI application with all middleware,
routers, and lifecycle handlers.
"""
from contextlib import asynccontextmanager
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

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_methods_list,
    allow_headers=settings.cors_allow_headers.split(","),
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
    
    logger.info("Request started")
    
    try:
        response = await call_next(request)
        
        logger.info(
            "Request completed",
            status_code=response.status_code
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response
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
    logger.warning("Validation error", errors=exc.errors())
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"errors": exc.errors()}
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
from app.modules.observability.routes import router as observability_router

# Agents
from app.modules.agents.routes import router as agents_router

app.include_router(observability_router, prefix=f"{settings.api_v1_prefix}", tags=["Observability"])
app.include_router(agents_router, prefix=f"{settings.api_v1_prefix}/agents", tags=["Agents"])

# TODO: Add these module routers as they are implemented:
# from app.modules.chat.presentation.routes import router as chat_router
# app.include_router(chat_router, prefix=f"{settings.api_v1_prefix}/chat", tags=["Chat"])

# from app.modules.embeddings.presentation.routes import router as embeddings_router
# app.include_router(embeddings_router, prefix=f"{settings.api_v1_prefix}/embeddings", tags=["Embeddings"])

# from app.modules.ingestion.presentation.routes import router as ingestion_router
# app.include_router(ingestion_router, prefix=f"{settings.api_v1_prefix}/ingestion", tags=["Ingestion"])


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
