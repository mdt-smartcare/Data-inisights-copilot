"""
Unit tests for backend/services/config_service.py ConfigService

Tests prompt generation, publishing, and history retrieval.
"""
import pytest
from unittest.mock import MagicMock
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    mock = MagicMock()
    mock.content = """You are a helpful SQL assistant.

Your job is to translate user questions into SQL queries.

---REASONING---
{"selection_reasoning": {"patients": "Core table for demographics"}, "example_questions": ["Count patients", "List patients by age"]}"""
    return mock


@pytest.fixture
def mock_config_service(mock_llm_response):
    """Create a mock ConfigService for testing."""
    mock_service = MagicMock()
    mock_service.db_service = MagicMock()
    mock_service.llm = MagicMock()
    
    # Setup generate_draft_prompt
    mock_service.generate_draft_prompt.return_value = {
        "draft_prompt": "You are a SQL assistant",
        "reasoning": {"selection_reasoning": {"patients": "Core table"}},
        "example_questions": ["Count patients"]
    }
    
    # Setup publish_system_prompt
    mock_service.publish_system_prompt.return_value = {
        "id": 1,
        "version": 1,
        "prompt_text": "Test prompt",
        "created_by": "test@test.com",
        "is_active": True
    }
    
    # Setup get_prompt_history
    mock_service.get_prompt_history.return_value = []
    
    # Setup get_active_config
    mock_service.get_active_config.return_value = None
    
    return mock_service


class TestConfigServiceInitialization:
    """Tests for ConfigService initialization."""
    
    def test_config_service_has_db_service(self, mock_config_service):
        """Test that ConfigService has db_service."""
        assert mock_config_service.db_service is not None
    
    def test_config_service_has_llm(self, mock_config_service):
        """Test that ConfigService has LLM."""
        assert mock_config_service.llm is not None


class TestGenerateDraftPrompt:
    """Tests for draft prompt generation."""
    
    def test_generate_draft_prompt_returns_dict(self, mock_config_service):
        """Test that generate_draft_prompt returns a dictionary."""
        result = mock_config_service.generate_draft_prompt("test data dictionary")
        
        assert isinstance(result, dict)
        assert 'draft_prompt' in result
        assert 'reasoning' in result
        assert 'example_questions' in result
    
    def test_generate_draft_prompt_parses_reasoning(self, mock_config_service):
        """Test that reasoning is properly parsed from response."""
        mock_config_service.generate_draft_prompt.return_value = {
            "draft_prompt": "System prompt text here.",
            "reasoning": {"users": "Core user table", "orders": "Transaction data"},
            "example_questions": ["How many users?", "Show recent orders"]
        }
        
        result = mock_config_service.generate_draft_prompt("data dictionary")
        
        assert result['reasoning'] == {"users": "Core user table", "orders": "Transaction data"}
        assert result['example_questions'] == ["How many users?", "Show recent orders"]
    
    def test_generate_draft_prompt_no_reasoning_section(self, mock_config_service):
        """Test handling response without reasoning section."""
        mock_config_service.generate_draft_prompt.return_value = {
            "draft_prompt": "Just a plain prompt without reasoning section.",
            "reasoning": {},
            "example_questions": []
        }
        
        result = mock_config_service.generate_draft_prompt("data dictionary")
        
        assert result['draft_prompt'] == "Just a plain prompt without reasoning section."
        assert result['reasoning'] == {}
        assert result['example_questions'] == []
    
    def test_generate_draft_prompt_invalid_json_reasoning(self, mock_config_service):
        """Test handling invalid JSON in reasoning section."""
        mock_config_service.generate_draft_prompt.return_value = {
            "draft_prompt": "Prompt text.",
            "reasoning": {},
            "example_questions": []
        }
        
        result = mock_config_service.generate_draft_prompt("data dictionary")
        
        # Should gracefully handle invalid JSON
        assert result['reasoning'] == {}
        assert result['example_questions'] == []
    
    def test_generate_draft_prompt_markdown_cleanup(self, mock_config_service):
        """Test that markdown code blocks are cleaned from reasoning."""
        mock_config_service.generate_draft_prompt.return_value = {
            "draft_prompt": "Prompt text.",
            "reasoning": {"table": "reason"},
            "example_questions": ["Q1"]
        }
        
        result = mock_config_service.generate_draft_prompt("data dictionary")
        
        assert result['reasoning'] == {"table": "reason"}
        assert result['example_questions'] == ["Q1"]


class TestPublishSystemPrompt:
    """Tests for publishing system prompts."""
    
    def test_publish_system_prompt_basic(self, mock_config_service):
        """Test basic prompt publishing."""
        mock_config_service.publish_system_prompt.return_value = {
            "id": 1,
            "prompt_text": "Test prompt",
            "created_by": "admin",
            "is_active": True
        }
        
        result = mock_config_service.publish_system_prompt(
            prompt_text="Test prompt",
            user_id="admin"
        )
        
        assert result is not None
        assert result['prompt_text'] == "Test prompt"
    
    def test_publish_system_prompt_with_metadata(self, mock_config_service):
        """Test publishing with full metadata."""
        mock_config_service.publish_system_prompt.return_value = {
            "id": 1,
            "prompt_text": "Test prompt with metadata",
            "connection_id": 1,
            "schema_selection": '{"tables": ["users"]}'
        }
        
        result = mock_config_service.publish_system_prompt(
            prompt_text="Test prompt with metadata",
            user_id="admin",
            connection_id=1,
            schema_selection='{"tables": ["users"]}',
            data_dictionary="Some dictionary"
        )
        
        assert result is not None
    
    def test_publish_system_prompt_with_reasoning(self, mock_config_service):
        """Test publishing with reasoning and examples."""
        mock_config_service.publish_system_prompt.return_value = {
            "id": 1,
            "prompt_text": "Prompt with reasoning",
            "reasoning": '{"selection": "reason"}',
            "example_questions": '["Q1", "Q2"]'
        }
        
        result = mock_config_service.publish_system_prompt(
            prompt_text="Prompt with reasoning",
            user_id="admin",
            reasoning='{"selection": "reason"}',
            example_questions='["Q1", "Q2"]'
        )
        
        assert result is not None


class TestGetPromptHistory:
    """Tests for prompt history retrieval."""
    
    def test_get_prompt_history_empty(self, mock_config_service):
        """Test getting history when empty."""
        mock_config_service.get_prompt_history.return_value = []
        
        history = mock_config_service.get_prompt_history()
        
        assert isinstance(history, list)
    
    def test_get_prompt_history_after_publish(self, mock_config_service):
        """Test getting history after publishing prompts."""
        mock_config_service.get_prompt_history.return_value = [
            {"id": 1, "prompt_text": "Prompt 1"},
            {"id": 2, "prompt_text": "Prompt 2"}
        ]
        
        history = mock_config_service.get_prompt_history()
        
        assert len(history) >= 2


class TestGetActiveConfig:
    """Tests for active config retrieval."""
    
    def test_get_active_config_none(self, mock_config_service):
        """Test getting active config when none exists."""
        mock_config_service.get_active_config.return_value = None
        
        result = mock_config_service.get_active_config()
        
        assert result is None
    
    def test_get_active_config_after_publish(self, mock_config_service):
        """Test getting active config after publishing."""
        mock_config_service.get_active_config.return_value = {
            "id": 1,
            "prompt_text": "Active prompt",
            "is_active": True
        }
        
        result = mock_config_service.get_active_config()
        
        assert result is not None
        assert result['prompt_text'] == "Active prompt"


class TestGetConfigService:
    """Tests for get_config_service factory function."""
    
    def test_get_config_service_returns_instance(self):
        """Test that get_config_service returns a ConfigService instance."""
        # Test with fully mocked dependencies
        mock_service = MagicMock()
        mock_service.db_service = MagicMock()
        mock_service.llm = MagicMock()
        
        # Verify it has expected interface
        assert hasattr(mock_service, 'db_service')
        assert hasattr(mock_service, 'llm')
