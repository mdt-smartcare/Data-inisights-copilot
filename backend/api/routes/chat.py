"""
Chat endpoint for RAG chatbot queries.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.schemas import ChatRequest, ChatResponse, User, ErrorResponse
from backend.services.agent_service import get_agent_service
from backend.core.permissions import require_user, get_current_user
from backend.core.logging import get_logger

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = get_logger(__name__)


@router.post("", response_model=ChatResponse, responses={
    401: {"model": ErrorResponse, "description": "Unauthorized"},
    500: {"model": ErrorResponse, "description": "Internal Server Error"}
})
async def chat(
    request: ChatRequest,
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
    
    logger.info(
        f"Chat request from user={user_id}, query_length={len(request.query)}",
        extra={"user_id": user_id}
    )
    
    try:
        # Get agent service and process query
        agent_service = get_agent_service()
        result = await agent_service.process_query(
            query=request.query,
            user_id=user_id
        )
        
        return result
        
    except Exception as e:
        logger.error(
            f"Chat request failed for user={user_id}: {str(e)}",
            exc_info=True,
            extra={"user_id": user_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )
