"""
Chat API routes.

Provides:
- POST /chat - Process a chat query
- POST /chat/feedback - Submit feedback for a chat response
- GET /chat/status - Get chat service status
"""
import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.permissions import get_current_user
from app.core.database.session import get_db_session as get_db
from app.core.models.common import BaseResponse
from app.core.utils.logging import get_logger
from app.modules.users.schemas import User

from app.modules.chat.service import ChatService
from app.modules.chat.tracing import get_langfuse_client
from app.modules.chat.schemas import (
    ChatRequest, ChatResponse, ChatServiceStatus,
    FeedbackRequest, FeedbackResponse
)

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


def get_chat_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    """Dependency injection for ChatService."""
    return ChatService(db)


@router.post("", response_model=BaseResponse[ChatResponse])
async def chat(
    chat_request: ChatRequest,
    fastapi_request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: ChatService = Depends(get_chat_service),
) -> BaseResponse[ChatResponse]:
    """
    Process a chat query using RAG pipeline with intent routing.
    
    Flow:
    1. Classify intent (SQL/Vector/Hybrid)
    2. Route to appropriate handler
    3. Generate response with LLM
    4. Return with sources and follow-up questions
    
    Args:
        chat_request: Chat request with query and optional agent_id
        
    Returns:
        ChatResponse with answer, sources, reasoning steps, and metadata
    """
    logger.info(
        "Chat request received",
        user_id=str(current_user.id),
        agent_id=str(chat_request.agent_id) if chat_request.agent_id else None,
        query_length=len(chat_request.query),
    )
    
    response = await service.process_query(
        request=chat_request,
        user_id=current_user.id,
        fastapi_request=fastapi_request,
    )
    
    return BaseResponse.ok(data=response)


@router.get("/status", response_model=BaseResponse[ChatServiceStatus])
async def get_chat_status(
    current_user: Annotated[User, Depends(get_current_user)],
    service: ChatService = Depends(get_chat_service),
) -> BaseResponse[ChatServiceStatus]:
    """
    Get chat service health status.
    
    Returns:
        ChatServiceStatus with health information
    """
    status_info = await service.get_service_status()
    
    return BaseResponse.ok(data=ChatServiceStatus(**status_info))


@router.post("/feedback", response_model=BaseResponse[FeedbackResponse])
async def submit_feedback(
    feedback: FeedbackRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> BaseResponse[FeedbackResponse]:
    """
    Submit feedback for a chat response.
    
    Feedback is stored in Langfuse as a score attached to the original trace.
    
    Rating values:
    - -1: Negative (thumbs down)
    -  0: Neutral
    -  1: Positive (thumbs up)
    
    Args:
        feedback: Feedback request with trace_id and rating
        
    Returns:
        FeedbackResponse with submission status
    """
    logger.info(
        "Feedback received",
        user_id=str(current_user.id),
        trace_id=feedback.trace_id,
        rating=feedback.rating,
    )
    
    feedback_id = str(uuid.uuid4().hex)
    
    # Push feedback to Langfuse as a score
    langfuse = get_langfuse_client()
    if langfuse:
        try:
            # Create score on the existing trace
            langfuse.score(
                trace_id=feedback.trace_id,
                name="user_feedback",
                value=feedback.rating,
                comment=feedback.comment,
                data_type="NUMERIC",
            )
            
            # Log additional metadata as event if comment provided
            if feedback.comment or feedback.selected_suggestion:
                langfuse.event(
                    trace_id=feedback.trace_id,
                    name="feedback_details",
                    metadata={
                        "feedback_id": feedback_id,
                        "query": feedback.query,
                        "selected_suggestion": feedback.selected_suggestion,
                        "comment": feedback.comment,
                        "user_id": str(current_user.id),
                    }
                )
            
            # Flush to ensure data is sent
            langfuse.flush()
            
            logger.info(
                "Feedback submitted to Langfuse",
                feedback_id=feedback_id,
                trace_id=feedback.trace_id,
            )
            
            return BaseResponse.ok(
                data=FeedbackResponse(
                    status="success",
                    message="Feedback recorded successfully",
                    feedback_id=feedback_id,
                )
            )
            
        except Exception as e:
            logger.error(f"Failed to submit feedback to Langfuse: {e}")
            return BaseResponse.ok(
                data=FeedbackResponse(
                    status="partial",
                    message="Feedback received but Langfuse storage failed",
                    feedback_id=feedback_id,
                )
            )
    else:
        # Langfuse not configured - just acknowledge receipt
        logger.warning("Langfuse not configured, feedback not persisted")
        return BaseResponse.ok(
            data=FeedbackResponse(
                status="success",
                message="Feedback received (observability not configured)",
                feedback_id=feedback_id,
            )
        )


@router.post("/sql-examples/load", response_model=BaseResponse[dict])
async def load_sql_examples(
    current_user: Annotated[User, Depends(get_current_user)],
) -> BaseResponse[dict]:
    """
    Load SQL training examples into the vector store for few-shot learning.
    
    Loads examples from the training_examples.json file.
    
    Returns:
        Count of loaded examples
    """
    import json
    from pathlib import Path
    from app.modules.sql_examples.store import get_sql_examples_store
    
    # Path to training examples
    examples_file = Path(__file__).parent.parent / "sql_examples" / "training_examples.json"
    
    if not examples_file.exists():
        return BaseResponse.ok(data={
            "error": f"Training examples file not found: {examples_file}",
            "loaded": 0
        })
    
    try:
        with open(examples_file, "r") as f:
            data = json.load(f)
        
        examples = data.get("examples", [])
        if not examples:
            return BaseResponse.ok(data={"error": "No examples found in file", "loaded": 0})
        
        logger.info(f"Loading {len(examples)} SQL examples into vector store")
        
        store = get_sql_examples_store()
        count = await store.add_examples_batch(examples)
        total = await store.get_example_count()
        
        logger.info(f"Successfully loaded {count} SQL examples, total in store: {total}")
        
        return BaseResponse.ok(data={
            "loaded": count,
            "total": total,
            "message": f"Successfully loaded {count} SQL examples"
        })
        
    except Exception as e:
        logger.error(f"Failed to load SQL examples: {e}", exc_info=True)
        return BaseResponse.ok(data={"error": str(e), "loaded": 0})


@router.get("/sql-examples/status", response_model=BaseResponse[dict])
async def get_sql_examples_status(
    current_user: Annotated[User, Depends(get_current_user)],
) -> BaseResponse[dict]:
    """
    Get status of SQL examples vector store.
    
    Returns:
        Health check information including example count
    """
    from app.modules.sql_examples.store import get_sql_examples_store
    
    try:
        store = get_sql_examples_store()
        health = await store.health_check()
        return BaseResponse.ok(data=health)
    except Exception as e:
        logger.error(f"Failed to check SQL examples status: {e}")
        return BaseResponse.ok(data={"healthy": False, "error": str(e)})
