"""
Tests for chat API routes.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException


class TestChatRouter:
    """Tests for chat router."""
    
    def test_router_exists(self):
        """Test chat router exists."""
        from backend.api.routes.chat import router
        assert router is not None
    
    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.routes.chat import router
        assert router.prefix == "/chat"
    
    def test_router_tags(self):
        """Test router has tags."""
        from backend.api.routes.chat import router
        assert "Chat" in router.tags


class TestChatEndpoint:
    """Tests for chat endpoint."""
    
    def test_chat_function_exists(self):
        """Test chat function exists."""
        from backend.api.routes.chat import chat
        assert chat is not None
    
    @pytest.mark.asyncio
    async def test_chat_processes_query(self):
        """Test chat endpoint processes query."""
        from backend.api.routes.chat import chat
        from backend.models.schemas import ChatRequest, User
        
        mock_agent_service = MagicMock()
        mock_agent_service.process_query = AsyncMock(return_value={
            "answer": "Test answer",
            "sql_query": "SELECT * FROM test",
            "reasoning_steps": []
        })
        
        with patch('backend.api.routes.chat.get_agent_service', return_value=mock_agent_service):
            request = ChatRequest(query="What is the data?")
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                role="user"
            )
            
            _ = await chat(request, mock_user)
            mock_agent_service.process_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_chat_creates_session_id(self):
        """Test chat creates session ID if not provided."""
        from backend.api.routes.chat import chat
        from backend.models.schemas import ChatRequest, User
        
        mock_agent_service = MagicMock()
        mock_agent_service.process_query = AsyncMock(return_value={
            "answer": "Test answer"
        })
        
        with patch('backend.api.routes.chat.get_agent_service', return_value=mock_agent_service):
            request = ChatRequest(query="Test query", session_id=None)
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                role="user"
            )
            
            await chat(request, mock_user)
            # Verify process_query was called with a session_id
            call_args = mock_agent_service.process_query.call_args
            assert 'session_id' in call_args.kwargs or len(call_args.args) >= 3
    
    @pytest.mark.asyncio
    async def test_chat_uses_provided_session_id(self):
        """Test chat uses provided session ID."""
        from backend.api.routes.chat import chat
        from backend.models.schemas import ChatRequest, User
        
        mock_agent_service = MagicMock()
        mock_agent_service.process_query = AsyncMock(return_value={
            "answer": "Test answer"
        })
        
        with patch('backend.api.routes.chat.get_agent_service', return_value=mock_agent_service):
            request = ChatRequest(query="Test query", session_id="existing-session-123")
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                role="user"
            )
            
            await chat(request, mock_user)
            call_args = mock_agent_service.process_query.call_args
            assert call_args.kwargs.get('session_id') == "existing-session-123"


class TestChatErrorHandling:
    """Tests for chat error handling."""
    
    @pytest.mark.asyncio
    async def test_chat_handles_agent_error(self):
        """Test chat handles agent service errors."""
        from backend.api.routes.chat import chat
        from backend.models.schemas import ChatRequest, User
        
        mock_agent_service = MagicMock()
        mock_agent_service.process_query = AsyncMock(side_effect=Exception("Agent error"))
        
        with patch('backend.api.routes.chat.get_agent_service', return_value=mock_agent_service):
            request = ChatRequest(query="Test query")
            mock_user = User(
                id=1,
                username="testuser",
                email="test@example.com",
                role="user"
            )
            
            with pytest.raises(HTTPException):
                await chat(request, mock_user)


class TestChatImports:
    """Tests for chat module imports."""
    
    def test_get_agent_service_import(self):
        """Test get_agent_service is imported."""
        from backend.api.routes.chat import get_agent_service
        assert get_agent_service is not None
    
    def test_logger_configured(self):
        """Test logger is configured."""
        from backend.api.routes.chat import logger
        assert logger is not None
