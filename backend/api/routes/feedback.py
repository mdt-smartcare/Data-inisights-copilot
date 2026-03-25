"""
Feedback endpoint for logging user feedback on suggestions.
Feedback is stored in Langfuse as scores attached to traces.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.schemas import FeedbackRequest, FeedbackResponse, User
from backend.api.deps import get_current_user
from backend.core.logging import get_logger
from backend.config import get_settings
from backend.core.tracing import get_tracing_manager

router = APIRouter(prefix="/feedback", tags=["Feedback"])
logger = get_logger(__name__)
settings = get_settings()


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Submit feedback on chatbot responses and suggestions.
    
    Feedback is stored as a score in Langfuse, attached to the trace
    identified by trace_id. This enables filtering traces by user feedback
    to identify problematic responses.
    
    - **trace_id**: Trace ID from the chat response
    - **query**: Original user query
    - **selected_suggestion**: The suggestion the user selected (optional)
    - **rating**: 1 for positive, -1 for negative
    - **comment**: Optional text comment
    
    **Authentication Required:** Bearer token in Authorization header.
    """
    feedback_id = str(uuid.uuid4())
    
    logger.info(
        f"Feedback submission: trace_id={request.trace_id}, rating={request.rating}, user={current_user.username}",
        extra={"user_id": current_user.username, "trace_id": request.trace_id}
    )
    
    try:
        # Push feedback score to Langfuse trace
        await _push_feedback_to_langfuse(request, current_user.username, feedback_id)
        
        logger.info(f"Feedback logged successfully: {feedback_id}")
        
        return FeedbackResponse(
            status="success",
            message=f"Feedback recorded with rating: {request.rating}",
            feedback_id=feedback_id
        )
        
    except Exception as e:
        logger.error(f"Failed to log feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to log feedback: {str(e)}"
        )


async def _push_feedback_to_langfuse(
    request: FeedbackRequest, 
    username: str, 
    feedback_id: str
) -> None:
    """
    Push user feedback score to Langfuse trace.
    
    Attaches the feedback score to the existing trace created during query processing.
    Does NOT create a new trace - just adds the score to the existing one.
    
    Args:
        request: The feedback request containing trace_id and rating
        username: Username of the user providing feedback
        feedback_id: Unique feedback record ID
    """
    tracing_manager = get_tracing_manager()
    
    if not tracing_manager.langfuse_enabled or not tracing_manager.langfuse:
        logger.warning("Langfuse not enabled - feedback will not be persisted")
        return
    
    # Convert rating to score (1 for positive, 0 for negative)
    score_value = 1.0 if request.rating > 0 else 0.0
    
    # Build comment string with metadata
    comment = f"User: {username}, Rating: {'👍 Positive' if request.rating > 0 else '👎 Negative'}"
    if request.comment:
        comment += f", Comment: {request.comment}"
    if request.selected_suggestion:
        comment += f", Selected: {request.selected_suggestion}"
    
    # Create the score attached to the existing trace
    tracing_manager.langfuse.create_score(
        name="user_feedback",
        value=score_value,
        trace_id=request.trace_id,
        comment=comment
    )
    
    # Flush to ensure score is sent immediately
    tracing_manager.flush()
    
    logger.info(
        f"Successfully pushed feedback score to Langfuse: "
        f"trace_id={request.trace_id}, score={score_value}, feedback_id={feedback_id}"
    )
