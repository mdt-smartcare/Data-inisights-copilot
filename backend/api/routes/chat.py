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
from backend.core.tracing import get_langfuse_handler
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

    user_int_id = current_user.id
    
    # Create a single trace_id that will group all LLM calls for this request
    trace_id = str(uuid.uuid4())
    langfuse_handler = None
    
    try:
        # Get Langfuse handler for tracing
        langfuse_handler = get_langfuse_handler(
            trace_name="chat-request",
            session_id=session_id,
            user_id=user_id,
            tags=["chat"],
            trace_id=trace_id
        )
        logger.info(f"Langfuse handler created: trace_id={langfuse_handler.get_trace_id()}")
    except Exception as e:
        logger.warning(f"Langfuse handler creation failed with params, trying minimal: {e}")
        try:
            # Fallback to minimal handler
            langfuse_handler = get_langfuse_handler(trace_id=trace_id)
            logger.info(f"Langfuse handler created (minimal): trace_id={langfuse_handler.get_trace_id()}")
        except Exception as e_minimal:
            logger.error(f"Minimal Langfuse handler creation failed: {e_minimal}")
            langfuse_handler = None
    
    # Process the query
    try:
        # Get the appropriate agent service
        # This will handle access control and dedicated agent configurations
        # Super admins have access to all agents - pass is_super_admin flag to skip access check
        is_super_admin = current_user.role == 'super_admin'
        
        agent_service = get_agent_service(
            agent_id=request.agent_id,
            user_id=user_int_id,
            langfuse_trace=langfuse_handler,
            is_super_admin=is_super_admin
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
