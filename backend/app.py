"""
FastAPI application entrypoint for the RAG Chatbot Backend.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Load environment variables manually for libraries that rely on os.environ (like OpenAI)
load_dotenv(Path(__file__).parent / ".env")

from backend.config import get_settings
from backend.core.logging import setup_logging, get_logger
from backend.api.routes import auth, chat, feedback, health, config, data, audit, users
from backend.api.routes import embedding_progress, notifications, settings as settings_routes, observability
from backend.api.websocket import embedding_progress as embedding_ws
from backend.api.websocket import notifications as notifications_ws
from backend.services.embeddings import preload_embedding_model
from backend.services.embeddings import preload_embedding_model

# Conditional Langfuse import
try:
    from langfuse import Langfuse
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

# Initialize settings and logging
settings = get_settings()
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.project_name} v{settings.version}")
    preload_embedding_model()
    
    # Initialize Langfuse client if enabled
    if settings.enable_langfuse and LANGFUSE_AVAILABLE:
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                app.state.langfuse_client = Langfuse(
                    public_key=settings.langfuse_public_key,
                    secret_key=settings.langfuse_secret_key,
                    host=settings.langfuse_host,
                    release=f"{settings.project_name}-{settings.version}",

                    debug=True,  # Enable debug to see what's happening
                )
                app.state.langfuse_enabled = True
                logger.info(f"Langfuse client initialized successfully. Host: {settings.langfuse_host}")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse: {e}", exc_info=True)
                app.state.langfuse_client = None
                app.state.langfuse_enabled = False
        else:
            logger.warning("Langfuse is enabled but missing public_key or secret_key in configuration.")
            app.state.langfuse_client = None
            app.state.langfuse_enabled = False
    else:
        app.state.langfuse_client = None
        app.state.langfuse_enabled = False
        if settings.enable_langfuse and not LANGFUSE_AVAILABLE:
            logger.warning("Langfuse is enabled in settings, but the 'langfuse' package is not installed.")


    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"API prefix: {settings.api_v1_prefix}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    if app.state.langfuse_client:
        app.state.langfuse_client.flush()
        logger.info("Langfuse client flushed.")
        logger.info("Langfuse client flushed.")


# Create FastAPI application
app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan
)


# =============================================================================
# Global Exception Handlers - Ensure CORS headers on all error responses
# =============================================================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with proper CORS headers."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Credentials": "true",
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with proper CORS headers."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Credentials": "true",
        }
    )


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_methods_list,
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(chat.router, prefix=settings.api_v1_prefix)
app.include_router(feedback.router, prefix=settings.api_v1_prefix)
app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(config.router, prefix=settings.api_v1_prefix)
app.include_router(data.router, prefix=settings.api_v1_prefix)
app.include_router(audit.router, prefix=settings.api_v1_prefix)
app.include_router(users.router, prefix=settings.api_v1_prefix)

# Agents route
from backend.api.routes import agents
app.include_router(agents.router, prefix=f"{settings.api_v1_prefix}/agents")

# New embedding and notification routes
app.include_router(embedding_progress.router, prefix=settings.api_v1_prefix)
app.include_router(notifications.router, prefix=settings.api_v1_prefix)

# Embedding settings routes (MUST be before general settings to prevent route shadowing)
from backend.api.routes import embedding_settings
app.include_router(embedding_settings.router, prefix=settings.api_v1_prefix)

# LLM settings routes (MUST be before general settings to prevent route shadowing)
from backend.api.routes import llm_settings
app.include_router(llm_settings.router, prefix=settings.api_v1_prefix)

# Model configuration routes (compatibility + versioning)
from backend.api.routes import model_config
app.include_router(model_config.router, prefix=settings.api_v1_prefix)

# Settings management routes (has /{category} catch-all, must come after specific routes)
app.include_router(settings_routes.router, prefix=settings.api_v1_prefix)

# Observability routes
app.include_router(observability.router, prefix=settings.api_v1_prefix)

# Ingestion routes
from backend.api.routes import vector_db
app.include_router(vector_db.router, prefix=settings.api_v1_prefix)

# File ingestion routes (upload, SQL queries on files)
from backend.api.routes import ingestion
app.include_router(ingestion.router, prefix=settings.api_v1_prefix)

# Schema drift detection routes
from backend.api.routes import schema_drift
app.include_router(schema_drift.router, prefix=settings.api_v1_prefix)

# WebSocket routes (no prefix for WebSocket endpoints)
app.include_router(embedding_ws.router)
app.include_router(notifications_ws.router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return JSONResponse({
        "message": "Data Insights Copilot",
        "version": settings.version,
        "docs": f"{settings.api_v1_prefix}/docs",
        "health": f"{settings.api_v1_prefix}/health"
    })


@app.get("/health")
async def root_health():
    """Alternative health check at root level."""
    return {"status": "healthy", "service": settings.project_name}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
