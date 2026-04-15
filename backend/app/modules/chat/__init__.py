"""
Chat module - RAG-powered conversational interface.

Flat file structure following three-layer architecture:
- routes.py: API endpoints (presentation layer)
- schemas.py: Request/Response DTOs (presentation layer)
- service.py: Business logic (application layer)
- intent_classifier.py: Query intent detection (infrastructure)
- sql_service.py: SQL data queries (infrastructure)
- tracing.py: Langfuse observability (infrastructure)
- memory.py: Conversation memory (infrastructure)
- followup.py: Follow-up question generation (infrastructure)
- cancellation.py: Request cancellation (infrastructure)

Note: LLM providers are in app.core.llm (shared infrastructure)
"""
from app.modules.chat.routes import router
from app.modules.chat.service import ChatService

__all__ = [
    "router",
    "ChatService",
]