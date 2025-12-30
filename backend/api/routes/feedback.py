"""
Feedback endpoint for logging user feedback on suggestions.
"""
import os
import uuid
from pathlib import Path
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.schemas import FeedbackRequest, FeedbackResponse, User
from backend.api.deps import get_current_user
from backend.core.logging import get_logger
from backend.config import get_settings

router = APIRouter(prefix="/feedback", tags=["Feedback"])
logger = get_logger(__name__)
settings = get_settings()

FEEDBACK_LOG_FILE = "feedback_log.csv"


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Submit feedback on chatbot responses and suggestions.
    
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
        # Prepare feedback data
        feedback_data = {
            "feedback_id": [feedback_id],
            "timestamp": [pd.Timestamp.now()],
            "user": [current_user.username],
            "trace_id": [request.trace_id],
            "query": [request.query],
            "selected_suggestion": [request.selected_suggestion or ""],
            "rating": [request.rating],
            "comment": [request.comment or ""]
        }
        
        df = pd.DataFrame(feedback_data)
        
        # Append to CSV file
        file_exists = os.path.isfile(FEEDBACK_LOG_FILE)
        df.to_csv(FEEDBACK_LOG_FILE, mode='a', header=not file_exists, index=False)
        
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
