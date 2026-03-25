"""
Chat endpoint for RAG chatbot queries.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Request

from backend.models.schemas import ChatRequest, ChatResponse, User, ErrorResponse
from backend.services.agent_service import get_agent_service
from backend.core.permissions import require_user
from backend.core.logging import get_logger
from backend.core.cancellation import RequestCancelled
from backend.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/chat", tags=["Chat"])
logger = get_logger(__name__)


def generate_langfuse_trace_id() -> str:
    """
    Generate a Langfuse-compatible trace ID.
    Langfuse requires 32 lowercase hex characters (no dashes).
    """
    return uuid.uuid4().hex


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
    trace_id = generate_langfuse_trace_id()
    
    # Process with Langfuse tracing if enabled
    return await _process_chat_with_tracing(
        request=request,
        fastapi_req=fastapi_req,
        user_id=user_id,
        user_int_id=user_int_id,
        session_id=session_id,
        trace_id=trace_id,
        is_super_admin=current_user.role == 'super_admin'
    )


async def _process_chat_with_tracing(
    request: ChatRequest,
    fastapi_req: Request,
    user_id: str,
    user_int_id: int,
    session_id: str,
    trace_id: str,
    is_super_admin: bool
):
    """Process chat request with optional Langfuse tracing."""
    langfuse_handler = None
    langfuse_context_manager = None
    langfuse_span = None
    langfuse_trace_id = trace_id  # Default to our trace_id, will be updated if Langfuse provides one
    
    try:
        from backend.core.tracing import get_tracing_manager
        tracing_manager = get_tracing_manager()
        
        if tracing_manager.langfuse_enabled and tracing_manager.langfuse:
            from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
            
            # Use start_as_current_span to set up context - this makes all subsequent
            # operations (including callback handler) children of this span!
            langfuse_context_manager = tracing_manager.langfuse.start_as_current_span(
                name="chat_request",
                input=request.query,
                metadata={
                    "user_id": user_id,
                    "session_id": session_id,
                    "agent_id": request.agent_id,
                    "app_trace_id": trace_id  # Store our app trace_id in metadata
                }
            )
            # Enter the context
            langfuse_span = langfuse_context_manager.__enter__()
            
            # Get the actual Langfuse trace ID for feedback association
            # In Langfuse v3.9.0, the span object has a 'trace_id' attribute
            if langfuse_span is not None:
                # The span.trace_id is the correct ID to use for create_score()
                if hasattr(langfuse_span, 'trace_id') and langfuse_span.trace_id:
                    langfuse_trace_id = langfuse_span.trace_id
                    logger.info(f"Langfuse trace ID from span.trace_id: {langfuse_trace_id}")
                else:
                    logger.warning(f"Span has no trace_id, using app trace_id: {trace_id}")
            
            # Now create callback handler - it will inherit the current span context
            langfuse_handler = LangfuseCallbackHandler()
            
            logger.info(f"Langfuse tracing context created: langfuse_trace_id={langfuse_trace_id}, span_id={getattr(langfuse_span, 'id', 'unknown')}")
            
    except Exception as e:
        logger.warning(f"Langfuse setup failed: {e}")
        langfuse_handler = None
        langfuse_context_manager = None
        langfuse_span = None
    
    try:
        agent_service = get_agent_service(
            agent_id=request.agent_id,
            user_id=user_int_id,
            langfuse_trace=langfuse_handler,
            is_super_admin=is_super_admin
        )
        
        result = await agent_service.process_query(
            query=request.query,
            user_id=user_id,
            session_id=session_id,
            request=fastapi_req,
            trace_id=trace_id
        )
        
        # Use the Langfuse trace ID for feedback association
        if isinstance(result, dict):
            result['agent_id'] = request.agent_id
            result['trace_id'] = langfuse_trace_id  # Use Langfuse's trace ID!
        else:
            result.agent_id = request.agent_id
            result.trace_id = langfuse_trace_id
        
        logger.info(f"Chat request completed: trace_id={langfuse_trace_id}")
        
        # Update span with output before exiting context
        if langfuse_span:
            try:
                answer = result.get('answer', '') if isinstance(result, dict) else result.answer
                langfuse_span.update(
                    output={"answer": answer[:500] if answer else ""},
                    metadata={
                        "success": True,
                        "has_chart": bool(result.get('chart_data') if isinstance(result, dict) else result.chart_data)
                    }
                )
            except Exception as e:
                logger.debug(f"Langfuse span update failed: {e}")
        
        # Exit the context manager (this ends the span properly)
        if langfuse_context_manager:
            try:
                langfuse_context_manager.__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"Langfuse context exit failed: {e}")
        
        # Flush traces
        if langfuse_handler:
            try:
                langfuse_handler.flush()
            except Exception:
                pass
        
        try:
            from backend.core.tracing import get_tracing_manager
            get_tracing_manager().flush()
        except Exception:
            pass
        
        return result
    
    except RequestCancelled:
        logger.info(f"Chat request cancelled by client: session={session_id}, trace_id={langfuse_trace_id}")
        if langfuse_span:
            try:
                langfuse_span.update(output={"error": "Client cancelled"}, level="WARNING")
            except Exception:
                pass
        if langfuse_context_manager:
            try:
                langfuse_context_manager.__exit__(None, None, None)
            except Exception:
                pass
        if langfuse_handler:
            try:
                langfuse_handler.flush()
            except Exception:
                pass
        raise HTTPException(status_code=499, detail="Client closed request")
        
    except Exception as e:
        if langfuse_span:
            try:
                langfuse_span.update(output={"error": str(e)}, level="ERROR")
            except Exception:
                pass
        if langfuse_context_manager:
            try:
                langfuse_context_manager.__exit__(type(e), e, e.__traceback__)
            except Exception:
                pass
        if langfuse_handler:
            try:
                langfuse_handler.flush()
            except Exception:
                pass
        
        logger.error(f"Chat request failed for user={user_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )
