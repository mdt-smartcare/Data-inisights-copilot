"""
Chat infrastructure layer.

Provides:
- Intent classification
- SQL service for data queries
- Tracing integration
- Conversation memory
- Follow-up generation
- Request cancellation
"""
from app.modules.chat.infrastructure.intent_classifier import (
    IntentClassifier, IntentClassification, QueryIntent,
    get_intent_classifier
)
from app.modules.chat.infrastructure.sql_service import (
    SQLService, SQLServiceFactory
)
from app.modules.chat.infrastructure.tracing import (
    TracingContext, trace_chat_request, generate_trace_id
)
from app.modules.chat.infrastructure.memory import (
    ConversationMemory, get_conversation_memory,
    rewrite_query_with_context
)
from app.modules.chat.infrastructure.followup import (
    FollowupService, get_followup_service,
    generate_followups_background
)
from app.modules.chat.infrastructure.cancellation import (
    RequestCancelled, check_cancelled
)

__all__ = [
    # Intent
    "IntentClassifier",
    "IntentClassification", 
    "QueryIntent",
    "get_intent_classifier",
    # SQL
    "SQLService",
    "SQLServiceFactory",
    # Tracing
    "TracingContext",
    "trace_chat_request",
    "generate_trace_id",
    # Memory
    "ConversationMemory",
    "get_conversation_memory",
    "rewrite_query_with_context",
    # Followup
    "FollowupService",
    "get_followup_service",
    "generate_followups_background",
    # Cancellation
    "RequestCancelled",
    "check_cancelled",
]