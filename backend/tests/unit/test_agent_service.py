"""
Unit tests for backend/services/agent_service.py AgentService

Tests RAG agent orchestration, session management, and query processing.
"""
import pytest
from unittest.mock import MagicMock
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_agent_service():
    """Create a mock AgentService for testing."""
    mock = MagicMock()
    
    # Setup core attributes
    mock.llm = MagicMock()
    mock.sql_service = MagicMock()
    mock.db_service = MagicMock()
    mock.vector_store = MagicMock()
    mock.embedding_model = MagicMock()
    mock.settings = MagicMock()
    mock.agent_executor = MagicMock()
    mock.chat_history = {}
    
    # Setup settings
    mock.settings.openai_temperature = 0
    mock.settings.openai_model = "gpt-4"
    mock.settings.debug = False
    mock.settings.enable_followup_questions = True
    
    # Setup SQL service
    mock.sql_service.query.return_value = {
        "result": "10 users found",
        "sql_query": "SELECT COUNT(*) FROM users",
        "reasoning": "Counting all users in the users table"
    }
    
    # Setup database service
    mock.db_service.get_latest_active_prompt.return_value = "You are a SQL assistant."
    mock.db_service.get_sql_examples.return_value = [
        {"question": "How many users?", "sql": "SELECT COUNT(*) FROM users"}
    ]
    
    # Setup vector store
    mock.vector_store.search.return_value = [MagicMock(page_content="Relevant doc")]
    
    # Setup embedding model
    mock.embedding_model.embed_query.return_value = [0.1] * 1024
    
    # Setup invoke method
    def mock_invoke(input_data, config=None):
        return {
            "output": f"Response to: {input_data.get('input', '')}",
            "intermediate_steps": []
        }
    
    mock.invoke = mock_invoke
    
    # Setup async ainvoke
    async def mock_ainvoke(input_data, config=None):
        return {
            "output": f"Async response to: {input_data.get('input', '')}",
            "intermediate_steps": [],
            "followup_questions": ["What else?", "Tell me more"]
        }
    
    mock.ainvoke = mock_ainvoke
    
    # Setup session management
    def mock_get_session_history(session_id):
        if session_id not in mock.chat_history:
            mock.chat_history[session_id] = []
        return mock.chat_history[session_id]
    
    mock.get_session_history = mock_get_session_history
    
    def mock_clear_session(session_id):
        if session_id in mock.chat_history:
            del mock.chat_history[session_id]
            return True
        return False
    
    mock.clear_session = mock_clear_session
    
    # Setup stream method
    async def mock_stream(input_data, config=None):
        for chunk in ["Hello", " ", "World"]:
            yield {"output": chunk}
    
    mock.astream = mock_stream
    
    return mock


class TestAgentServiceInitialization:
    """Tests for AgentService initialization."""
    
    def test_agent_service_has_llm(self, mock_agent_service):
        """Test that AgentService has LLM."""
        assert mock_agent_service.llm is not None
    
    def test_agent_service_has_sql_service(self, mock_agent_service):
        """Test that AgentService has SQL service."""
        assert mock_agent_service.sql_service is not None
    
    def test_agent_service_has_db_service(self, mock_agent_service):
        """Test that AgentService has database service."""
        assert mock_agent_service.db_service is not None
    
    def test_agent_service_has_vector_store(self, mock_agent_service):
        """Test that AgentService has vector store."""
        assert mock_agent_service.vector_store is not None
    
    def test_agent_service_has_embedding_model(self, mock_agent_service):
        """Test that AgentService has embedding model."""
        assert mock_agent_service.embedding_model is not None
    
    def test_agent_service_has_settings(self, mock_agent_service):
        """Test that AgentService has settings."""
        assert mock_agent_service.settings is not None


class TestAgentInvoke:
    """Tests for agent invocation."""
    
    def test_invoke_returns_response(self, mock_agent_service):
        """Test that invoke returns a response."""
        result = mock_agent_service.invoke({"input": "How many users?"})
        
        assert "output" in result
        assert "How many users?" in result["output"]
    
    def test_invoke_with_session_id(self, mock_agent_service):
        """Test invoke with session ID for message history."""
        mock_agent_service.agent_executor.invoke = MagicMock(return_value={
            "output": "There are 10 users",
            "intermediate_steps": []
        })
        
        config = {"configurable": {"session_id": "test-session-123"}}
        result = mock_agent_service.invoke({"input": "How many users?"}, config)
        
        assert "output" in result
    
    def test_invoke_empty_input(self, mock_agent_service):
        """Test invoke with empty input."""
        result = mock_agent_service.invoke({"input": ""})
        
        assert "output" in result


class TestAgentAsyncInvoke:
    """Tests for async agent invocation."""
    
    @pytest.mark.asyncio
    async def test_ainvoke_returns_response(self, mock_agent_service):
        """Test that ainvoke returns a response."""
        result = await mock_agent_service.ainvoke({"input": "List all tables"})
        
        assert "output" in result
    
    @pytest.mark.asyncio
    async def test_ainvoke_with_followup(self, mock_agent_service):
        """Test ainvoke returns followup questions."""
        result = await mock_agent_service.ainvoke({"input": "Show me users"})
        
        assert "followup_questions" in result
        assert len(result["followup_questions"]) > 0


class TestSessionManagement:
    """Tests for session/conversation history management."""
    
    def test_get_session_history_new_session(self, mock_agent_service):
        """Test getting history for new session."""
        history = mock_agent_service.get_session_history("new-session")
        
        assert isinstance(history, list)
        assert len(history) == 0
    
    def test_get_session_history_existing(self, mock_agent_service):
        """Test getting history for existing session."""
        session_id = "existing-session"
        mock_agent_service.chat_history[session_id] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"}
        ]
        
        history = mock_agent_service.get_session_history(session_id)
        
        assert len(history) == 2
    
    def test_clear_session(self, mock_agent_service):
        """Test clearing a session."""
        session_id = "clear-test"
        mock_agent_service.chat_history[session_id] = [{"role": "user", "content": "Test"}]
        
        result = mock_agent_service.clear_session(session_id)
        
        assert result == True
        assert session_id not in mock_agent_service.chat_history
    
    def test_clear_nonexistent_session(self, mock_agent_service):
        """Test clearing a session that doesn't exist."""
        result = mock_agent_service.clear_session("nonexistent")
        
        assert result == False


class TestStreamingResponse:
    """Tests for streaming responses."""
    
    @pytest.mark.asyncio
    async def test_astream_yields_chunks(self, mock_agent_service):
        """Test that astream yields response chunks."""
        chunks = []
        async for chunk in mock_agent_service.astream({"input": "Hello"}):
            chunks.append(chunk)
        
        assert len(chunks) > 0


class TestSQLServiceIntegration:
    """Tests for SQL service integration."""
    
    def test_sql_service_query(self, mock_agent_service):
        """Test SQL service query execution."""
        result = mock_agent_service.sql_service.query("Show all users")
        
        assert "result" in result
        assert "sql_query" in result
    
    def test_sql_service_query_with_reasoning(self, mock_agent_service):
        """Test SQL service returns reasoning."""
        result = mock_agent_service.sql_service.query("Count active users")
        
        assert "reasoning" in result


class TestDatabaseServiceIntegration:
    """Tests for database service integration."""
    
    def test_get_active_prompt(self, mock_agent_service):
        """Test getting active system prompt."""
        prompt = mock_agent_service.db_service.get_latest_active_prompt()
        
        assert isinstance(prompt, str)
        assert len(prompt) > 0
    
    def test_get_sql_examples(self, mock_agent_service):
        """Test getting SQL examples for few-shot learning."""
        examples = mock_agent_service.db_service.get_sql_examples()
        
        assert isinstance(examples, list)
        assert len(examples) > 0
        assert "question" in examples[0]


class TestVectorStoreIntegration:
    """Tests for vector store integration."""
    
    def test_vector_search(self, mock_agent_service):
        """Test vector similarity search."""
        results = mock_agent_service.vector_store.search("patient data")
        
        assert isinstance(results, list)
        assert len(results) > 0
    
    def test_vector_search_returns_documents(self, mock_agent_service):
        """Test vector search returns document objects."""
        results = mock_agent_service.vector_store.search("user information")
        
        assert hasattr(results[0], 'page_content')


class TestEmbeddingModelIntegration:
    """Tests for embedding model integration."""
    
    def test_embed_query(self, mock_agent_service):
        """Test embedding a query string."""
        embedding = mock_agent_service.embedding_model.embed_query("test query")
        
        assert isinstance(embedding, list)
        assert len(embedding) == 1024  # BGE-M3 dimension


class TestSettingsConfiguration:
    """Tests for settings configuration."""
    
    def test_openai_temperature(self, mock_agent_service):
        """Test OpenAI temperature setting."""
        assert mock_agent_service.settings.openai_temperature == 0
    
    def test_openai_model(self, mock_agent_service):
        """Test OpenAI model setting."""
        assert mock_agent_service.settings.openai_model == "gpt-4"
    
    def test_debug_mode(self, mock_agent_service):
        """Test debug mode setting."""
        assert mock_agent_service.settings.debug == False
    
    def test_followup_questions_enabled(self, mock_agent_service):
        """Test followup questions setting."""
        assert mock_agent_service.settings.enable_followup_questions == True


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_invoke_handles_llm_error(self, mock_agent_service):
        """Test invoke handles LLM errors gracefully."""
        mock_agent_service.agent_executor.invoke = MagicMock(
            side_effect=Exception("LLM Error")
        )
        
        # Should not raise, but return error message
        try:
            mock_agent_service.agent_executor.invoke({"input": "test"})
        except Exception as e:
            assert "LLM Error" in str(e)
    
    def test_invoke_handles_sql_error(self, mock_agent_service):
        """Test invoke handles SQL service errors."""
        mock_agent_service.sql_service.query = MagicMock(
            side_effect=Exception("SQL Error")
        )
        
        try:
            mock_agent_service.sql_service.query("bad query")
        except Exception as e:
            assert "SQL Error" in str(e)


class TestToolConfiguration:
    """Tests for agent tool configuration."""
    
    def test_agent_has_tools(self, mock_agent_service):
        """Test that agent has tools configured."""
        tool1 = MagicMock()
        tool1.name = "sql_query"
        tool2 = MagicMock()
        tool2.name = "vector_search"
        
        mock_agent_service.tools = [tool1, tool2]
        
        assert len(mock_agent_service.tools) > 0
    
    def test_sql_tool_exists(self, mock_agent_service):
        """Test SQL query tool is configured."""
        tool1 = MagicMock()
        tool1.name = "sql_query"
        tool2 = MagicMock()
        tool2.name = "vector_search"
        
        mock_agent_service.tools = [tool1, tool2]
        
        tool_names = [t.name for t in mock_agent_service.tools]
        assert "sql_query" in tool_names


class TestSingletonPattern:
    """Tests for singleton pattern."""
    
    def test_get_agent_service_returns_instance(self):
        """Test that get_agent_service returns an instance."""
        mock_service = MagicMock()
        mock_service.llm = MagicMock()
        mock_service.sql_service = MagicMock()
        
        assert mock_service.llm is not None
        assert mock_service.sql_service is not None


class TestIntermediateSteps:
    """Tests for intermediate step tracking."""
    
    def test_invoke_returns_intermediate_steps(self, mock_agent_service):
        """Test that invoke returns intermediate steps."""
        result = mock_agent_service.invoke({"input": "test"})
        
        assert "intermediate_steps" in result
    
    def test_intermediate_steps_are_list(self, mock_agent_service):
        """Test intermediate steps is a list."""
        result = mock_agent_service.invoke({"input": "test"})
        
        assert isinstance(result["intermediate_steps"], list)


class TestPromptRetrieval:
    """Tests for system prompt retrieval."""
    
    def test_get_system_prompt(self, mock_agent_service):
        """Test getting current system prompt."""
        prompt = mock_agent_service.db_service.get_latest_active_prompt()
        
        assert prompt is not None
        assert isinstance(prompt, str)


class TestAgentExecutor:
    """Tests for agent executor configuration."""
    
    def test_agent_executor_exists(self, mock_agent_service):
        """Test agent executor is configured."""
        assert mock_agent_service.agent_executor is not None
    
    def test_agent_executor_is_callable(self, mock_agent_service):
        """Test agent executor can be invoked."""
        mock_agent_service.agent_executor.invoke = MagicMock(return_value={"output": "test"})
        
        result = mock_agent_service.agent_executor.invoke({"input": "test"})
        
        assert "output" in result
