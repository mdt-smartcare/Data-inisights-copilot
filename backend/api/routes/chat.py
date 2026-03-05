"""
Chat endpoint for RAG chatbot queries.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Request
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

from backend.models.schemas import ChatRequest, ChatResponse, User, ErrorResponse
from backend.services.agent_service import get_agent_service
from backend.core.permissions import require_user
from backend.core.logging import get_logger
from backend.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["Chat"])
logger = get_logger(__name__)


@router.post("", response_model=ChatResponse, responses={
    401: {"model": ErrorResponse, "description": "Unauthorized"},
    500: {"model": ErrorResponse, "description": "Internal Server Error"}
})
async def chat(
    request: ChatRequest,
    fastapi_req: Request,
    current_user: User = Depends(require_user)
):
    """
    Process a chat query through the RAG pipeline.
    
    - **query**: User's question (required, 1-2000 characters)
    - **user_id**: Optional user identifier (extracted from JWT if not provided)
    
    Returns comprehensive response with answer, charts, suggestions, and reasoning.

    **Authentication Required:** Bearer token in Authorization header.
    **Requires Role:** User or above (Super Admin, Editor, User)
    """
    user_id = request.user_id or current_user.username
    
    # Extract or generate session ID for conversation tracking
    session_id = request.session_id
    if session_id is None:
        session_id = str(uuid.uuid4())
        logger.info(f"New session created: {session_id}")
    
    logger.info(
        f"Chat request from user={user_id}, session={session_id}, query_length={len(request.query)}",
        extra={"user_id": user_id, "session_id": session_id}
    )
    
    # Get user ID for agent service
    from backend.sqliteDb.db import get_db_service
    db = get_db_service()
    user_record = db.get_user_by_username(current_user.username)
    user_int_id = user_record['id'] if user_record else None
    
    # Create a single trace_id that will group all LLM calls for this request
    trace_id = str(uuid.uuid4())
    langfuse_handler = None
    
    if settings.enable_langfuse:
        try:
            # Create callback handler - Langfuse v3.x uses minimal constructor
            # Credentials are read from environment variables automatically
            langfuse_handler = LangfuseCallbackHandler(
                public_key=settings.langfuse_public_key,
                user_id=user_id,
                session_id=session_id,
                trace_name="chat-query",
                tags=["chat", "sql-query"] if request.agent_id else ["chat"],
            )
            logger.info(f"Langfuse handler created: trace_id={trace_id}")
        except TypeError as te:
            # If some params are not supported, try minimal version
            logger.warning(f"Langfuse handler creation failed with params, trying minimal: {te}")
            try:
                langfuse_handler = LangfuseCallbackHandler()
                logger.info(f"Langfuse handler created (minimal): trace_id={trace_id}")
            except Exception as e2:
                logger.warning(f"Failed to create minimal Langfuse handler: {e2}")
        except Exception as e:
            logger.warning(f"Failed to create Langfuse handler: {e}")
    
    # Process the query
    try:
        # Get agent service with Langfuse handler for tracing
        agent_service = get_agent_service(
            agent_id=request.agent_id,
            user_id=user_int_id,
            langfuse_trace=langfuse_handler  # Pass the callback handler!
        )
        
        # Process the query
        result = await agent_service.process_query(
            query=request.query,
            user_id=user_id,
            session_id=session_id
        )
        
        logger.info(f"Chat request completed: trace_id={trace_id}")
        
        # Flush to ensure trace is sent
        if langfuse_handler:
            try:
                langfuse_handler.flush()
            except Exception as e:
                logger.debug(f"Langfuse flush: {e}")
        
        return result
        
    except Exception as e:
        # Flush even on error
        if langfuse_handler:
            try:
                langfuse_handler.flush()
            except Exception:
                pass
        
        logger.error(
            f"Chat request failed for user={user_id}: {str(e)}",
            exc_info=True,
            extra={"user_id": user_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )
