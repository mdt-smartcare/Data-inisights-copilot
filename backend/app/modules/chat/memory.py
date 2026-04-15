"""
Conversation memory for multi-turn chat sessions.

Stores chat history per session to enable contextual follow-up questions.
"""
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict
from threading import Lock

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# Session memory configuration
SESSION_TTL_SECONDS = 3600  # 1 hour
MAX_SESSIONS = 1000
MAX_MESSAGES_PER_SESSION = 50


@dataclass
class ChatMessage:
    """A single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationSession:
    """A chat session with history."""
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation."""
        self.messages.append(ChatMessage(role=role, content=content))
        self.last_activity = time.time()
        
        # Trim old messages if too many
        if len(self.messages) > MAX_MESSAGES_PER_SESSION:
            self.messages = self.messages[-MAX_MESSAGES_PER_SESSION:]
    
    def get_history(self, max_messages: int = 10) -> List[ChatMessage]:
        """Get recent conversation history."""
        return self.messages[-max_messages:]
    
    def get_context_string(self, max_messages: int = 5) -> str:
        """Get conversation history as a formatted string for context."""
        history = self.get_history(max_messages)
        if not history:
            return ""
        
        lines = []
        for msg in history:
            prefix = "User: " if msg.role == "user" else "Assistant: "
            # Truncate long messages
            content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
            lines.append(f"{prefix}{content}")
        
        return "\n".join(lines)
    
    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return time.time() - self.last_activity > SESSION_TTL_SECONDS


class ConversationMemory:
    """
    In-memory conversation store with LRU eviction.
    
    Thread-safe storage for chat sessions with automatic cleanup.
    """
    
    def __init__(self):
        self._sessions: OrderedDict[str, ConversationSession] = OrderedDict()
        self._lock = Lock()
    
    def get_session(self, session_id: str) -> ConversationSession:
        """
        Get or create a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            ConversationSession for the given ID
        """
        with self._lock:
            # Check if session exists
            if session_id in self._sessions:
                session = self._sessions[session_id]
                
                # Check expiration
                if session.is_expired():
                    del self._sessions[session_id]
                else:
                    # Move to end (LRU)
                    self._sessions.move_to_end(session_id)
                    return session
            
            # Create new session
            session = ConversationSession(session_id=session_id)
            self._sessions[session_id] = session
            
            # Evict oldest if too many sessions
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)
            
            return session
    
    def add_exchange(
        self, 
        session_id: str, 
        user_message: str, 
        assistant_message: str
    ):
        """
        Add a user-assistant exchange to a session.
        
        Args:
            session_id: Session identifier
            user_message: User's query
            assistant_message: Assistant's response
        """
        session = self.get_session(session_id)
        session.add_message("user", user_message)
        session.add_message("assistant", assistant_message)
    
    def get_context(self, session_id: str, max_messages: int = 5) -> str:
        """
        Get conversation context as a string.
        
        Args:
            session_id: Session identifier
            max_messages: Maximum messages to include
            
        Returns:
            Formatted conversation history
        """
        session = self.get_session(session_id)
        return session.get_context_string(max_messages)
    
    def clear_session(self, session_id: str):
        """Clear a specific session."""
        with self._lock:
            self._sessions.pop(session_id, None)
    
    def cleanup_expired(self):
        """Remove all expired sessions."""
        with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired()
            ]
            for sid in expired:
                del self._sessions[sid]
            
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")
    
    @property
    def session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self._sessions)


# Global conversation memory instance
_memory_instance: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """Get the global conversation memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ConversationMemory()
    return _memory_instance


async def rewrite_query_with_context(
    query: str,
    session_id: Optional[str],
    use_llm: bool = True
) -> str:
    """
    Rewrite a query to include conversation context.
    
    If the query references previous conversation ("it", "that", "the previous"),
    this will expand it to be self-contained.
    
    Args:
        query: Original user query
        session_id: Session ID for conversation history
        use_llm: Whether to use LLM for rewriting
        
    Returns:
        Rewritten query (or original if no context needed)
    """
    if not session_id:
        return query
    
    memory = get_conversation_memory()
    context = memory.get_context(session_id, max_messages=3)
    
    if not context:
        return query
    
    # Check if query likely needs context
    context_indicators = [
        'it', 'that', 'this', 'they', 'them', 'those',
        'the same', 'previous', 'earlier', 'above',
        'more', 'another', 'also', 'too',
    ]
    
    query_lower = query.lower()
    needs_context = any(
        indicator in query_lower.split()  # Word boundary check
        for indicator in context_indicators
    )
    
    if not needs_context:
        return query
    
    if not use_llm:
        # Simple approach: prepend context summary
        return f"(Context: {context[-200:]}...) {query}"
    
    # Use LLM to rewrite
    try:
        from app.core.llm import create_llm_provider
        from langchain_core.prompts import ChatPromptTemplate
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """Rewrite the user's query to be self-contained given the conversation history.
If the query references something from the history (like "it", "that", "the previous"), 
make it explicit. If the query is already self-contained, return it unchanged.

Conversation history:
{context}

Only respond with the rewritten query, nothing else."""),
            ("user", "{query}")
        ])
        
        provider = create_llm_provider("openai", {
            "model": "gpt-4o-mini",
            "temperature": 0,
        })
        llm = provider.get_langchain_llm()
        
        chain = prompt | llm
        result = chain.invoke({"context": context, "query": query})
        
        rewritten = result.content.strip()
        if rewritten and rewritten != query:
            logger.info(f"Query rewritten: '{query[:50]}...' -> '{rewritten[:50]}...'")
            return rewritten
        
        return query
        
    except Exception as e:
        logger.warning(f"Query rewriting failed: {e}")
        return query
