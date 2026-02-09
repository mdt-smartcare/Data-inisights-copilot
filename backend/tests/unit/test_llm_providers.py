"""
Unit tests for backend/services/llm_providers.py and llm_registry.py

Tests LLM provider abstraction, registry management, and provider switching.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


# =============================================================================
# LLMProvider Abstract Base Class Tests
# =============================================================================

class TestLLMProviderInterface:
    """Tests for the LLMProvider interface contract."""
    
    def test_provider_interface_has_required_methods(self):
        """Test that provider interface defines required abstract methods."""
        from backend.services.llm_providers import LLMProvider
        
        # Check abstract methods exist
        assert hasattr(LLMProvider, 'get_langchain_llm')
        assert hasattr(LLMProvider, 'provider_name')
        assert hasattr(LLMProvider, 'model_name')
        assert hasattr(LLMProvider, 'health_check')
        assert hasattr(LLMProvider, 'get_config')
        assert hasattr(LLMProvider, 'chat')
    
    def test_provider_cannot_be_instantiated_directly(self):
        """Test that abstract base class cannot be instantiated."""
        from backend.services.llm_providers import LLMProvider
        
        with pytest.raises(TypeError):
            LLMProvider()


# =============================================================================
# OpenAI Provider Tests
# =============================================================================

class TestOpenAIProvider:
    """Tests for OpenAI provider implementation."""
    
    @patch('backend.services.llm_providers.ChatOpenAI')
    def test_openai_provider_initialization(self, mock_chat):
        """Test OpenAI provider initializes correctly."""
        from backend.services.llm_providers import OpenAIProvider
        
        mock_chat.return_value = MagicMock()
        
        provider = OpenAIProvider(
            model_name="gpt-4o",
            api_key="test-key",
            temperature=0.5,
            max_tokens=2048
        )
        
        assert provider.provider_name == "openai"
        assert provider.model_name == "gpt-4o"
    
    @patch('backend.services.llm_providers.ChatOpenAI')
    def test_openai_provider_get_config(self, mock_chat):
        """Test OpenAI provider config output."""
        from backend.services.llm_providers import OpenAIProvider
        
        mock_chat.return_value = MagicMock()
        
        provider = OpenAIProvider(
            model_name="gpt-4o",
            api_key="test-key",
            temperature=0.7,
            max_tokens=4096
        )
        
        config = provider.get_config()
        
        assert config["provider"] == "openai"
        assert config["model"] == "gpt-4o"
        assert config["temperature"] == 0.7
        assert config["max_tokens"] == 4096
        assert config["api_key_configured"] == True
    
    def test_openai_provider_fails_without_key(self):
        """Test OpenAI provider fails without API key."""
        from backend.services.llm_providers import OpenAIProvider
        
        # Clear env var temporarily
        original_key = os.environ.pop("OPENAI_API_KEY", None)
        
        try:
            with pytest.raises(ValueError, match="API key not provided"):
                OpenAIProvider(model_name="gpt-4o", api_key=None)
        finally:
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key
    
    @patch('backend.services.llm_providers.ChatOpenAI')
    def test_openai_available_models(self, mock_chat):
        """Test OpenAI provider has list of available models."""
        from backend.services.llm_providers import OpenAIProvider
        
        assert "gpt-4o" in OpenAIProvider.AVAILABLE_MODELS
        assert "gpt-4-turbo" in OpenAIProvider.AVAILABLE_MODELS
        assert "gpt-3.5-turbo" in OpenAIProvider.AVAILABLE_MODELS


# =============================================================================
# Anthropic Provider Tests
# =============================================================================

class TestAnthropicProvider:
    """Tests for Anthropic provider implementation."""
    
    @patch('backend.services.llm_providers.ChatAnthropic')
    def test_anthropic_provider_initialization(self, mock_chat):
        """Test Anthropic provider initializes correctly."""
        from backend.services.llm_providers import AnthropicProvider
        
        mock_chat.return_value = MagicMock()
        
        provider = AnthropicProvider(
            model_name="claude-3-5-sonnet-20241022",
            api_key="test-anthropic-key",
            temperature=0.0
        )
        
        assert provider.provider_name == "anthropic"
        assert provider.model_name == "claude-3-5-sonnet-20241022"
    
    def test_anthropic_available_models(self):
        """Test Anthropic provider has list of available models."""
        from backend.services.llm_providers import AnthropicProvider
        
        assert "claude-3-5-sonnet-20241022" in AnthropicProvider.AVAILABLE_MODELS
        assert "claude-3-opus-20240229" in AnthropicProvider.AVAILABLE_MODELS


# =============================================================================
# Ollama Provider Tests
# =============================================================================

class TestOllamaProvider:
    """Tests for Ollama (local) provider implementation."""
    
    @patch('backend.services.llm_providers.ChatOllama')
    def test_ollama_provider_initialization(self, mock_chat):
        """Test Ollama provider initializes correctly."""
        from backend.services.llm_providers import OllamaProvider
        
        mock_chat.return_value = MagicMock()
        
        provider = OllamaProvider(
            model_name="llama3.2",
            base_url="http://localhost:11434"
        )
        
        assert provider.provider_name == "ollama"
        assert provider.model_name == "llama3.2"
    
    @patch('backend.services.llm_providers.ChatOllama')
    def test_ollama_provider_config(self, mock_chat):
        """Test Ollama provider config includes base_url."""
        from backend.services.llm_providers import OllamaProvider
        
        mock_chat.return_value = MagicMock()
        
        provider = OllamaProvider(
            model_name="mistral",
            base_url="http://custom:11434"
        )
        
        config = provider.get_config()
        
        assert config["provider"] == "ollama"
        assert config["base_url"] == "http://custom:11434"
    
    def test_ollama_popular_models_list(self):
        """Test Ollama provider has popular models list."""
        from backend.services.llm_providers import OllamaProvider
        
        assert "llama3.2" in OllamaProvider.POPULAR_MODELS
        assert "mistral" in OllamaProvider.POPULAR_MODELS


# =============================================================================
# HuggingFace Provider Tests
# =============================================================================

class TestHuggingFaceProvider:
    """Tests for HuggingFace provider implementation."""
    
    @patch('backend.services.llm_providers.ChatHuggingFace')
    @patch('backend.services.llm_providers.HuggingFaceEndpoint')
    def test_huggingface_api_mode(self, mock_endpoint, mock_chat):
        """Test HuggingFace provider in API mode."""
        from backend.services.llm_providers import HuggingFaceProvider
        
        mock_endpoint.return_value = MagicMock()
        mock_chat.return_value = MagicMock()
        
        provider = HuggingFaceProvider(
            model_name="meta-llama/Llama-3.2-3B-Instruct",
            api_key="hf-test-key",
            use_api=True
        )
        
        assert provider.provider_name == "huggingface"
        config = provider.get_config()
        assert config["use_api"] == True


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestCreateLLMProvider:
    """Tests for create_llm_provider factory function."""
    
    @patch('backend.services.llm_providers.ChatOpenAI')
    def test_create_openai_provider(self, mock_chat):
        """Test factory creates OpenAI provider."""
        from backend.services.llm_providers import create_llm_provider
        
        mock_chat.return_value = MagicMock()
        
        provider = create_llm_provider("openai", {"api_key": "test"})
        
        assert provider.provider_name == "openai"
    
    def test_create_unknown_provider_raises(self):
        """Test factory raises for unknown provider."""
        from backend.services.llm_providers import create_llm_provider
        
        with pytest.raises(ValueError, match="Unknown provider"):
            create_llm_provider("invalid_provider", {})


# =============================================================================
# LLM Registry Tests
# =============================================================================

class TestLLMRegistry:
    """Tests for LLM Registry singleton."""
    
    @patch('backend.services.llm_registry.get_settings_service')
    @patch('backend.services.llm_registry.create_llm_provider')
    def test_registry_is_singleton(self, mock_create, mock_settings):
        """Test LLMRegistry is a singleton."""
        # Reset singleton for test
        from backend.services import llm_registry
        llm_registry._llm_registry = None
        
        mock_settings.return_value.get_all_settings.return_value = {"llm": {}}
        mock_provider = MagicMock()
        mock_provider.provider_name = "openai"
        mock_provider.model_name = "gpt-4o"
        mock_provider.get_config.return_value = {}
        mock_create.return_value = mock_provider
        
        registry1 = llm_registry.get_llm_registry()
        registry2 = llm_registry.get_llm_registry()
        
        assert registry1 is registry2
    
    def test_registry_has_provider_catalog(self):
        """Test registry has provider catalog."""
        from backend.services.llm_registry import LLMRegistry
        
        assert "openai" in LLMRegistry.PROVIDER_CATALOG
        assert "azure" in LLMRegistry.PROVIDER_CATALOG
        assert "anthropic" in LLMRegistry.PROVIDER_CATALOG
        assert "ollama" in LLMRegistry.PROVIDER_CATALOG
        assert "huggingface" in LLMRegistry.PROVIDER_CATALOG
        assert "local" in LLMRegistry.PROVIDER_CATALOG
    
    def test_provider_catalog_has_required_fields(self):
        """Test each provider in catalog has required fields."""
        from backend.services.llm_registry import LLMRegistry
        
        required_fields = ["class", "display_name", "description", "default_config", "requires_api_key"]
        
        for provider_name, provider_info in LLMRegistry.PROVIDER_CATALOG.items():
            for field in required_fields:
                assert field in provider_info, f"{provider_name} missing {field}"
    
    @patch('backend.services.llm_registry.get_settings_service')
    @patch('backend.services.llm_registry.create_llm_provider')
    def test_registry_list_providers(self, mock_create, mock_settings):
        """Test listing available providers."""
        from backend.services import llm_registry
        llm_registry._llm_registry = None
        
        mock_settings.return_value.get_all_settings.return_value = {"llm": {}}
        mock_provider = MagicMock()
        mock_provider.provider_name = "openai"
        mock_provider.model_name = "gpt-4o"
        mock_provider.get_config.return_value = {}
        mock_create.return_value = mock_provider
        
        registry = llm_registry.get_llm_registry()
        providers = registry.list_providers()
        
        assert len(providers) == 6
        names = [p["name"] for p in providers]
        assert "openai" in names
        assert "ollama" in names


# =============================================================================
# Health Check Tests
# =============================================================================

class TestProviderHealthCheck:
    """Tests for provider health check functionality."""
    
    @patch('backend.services.llm_providers.ChatOpenAI')
    def test_health_check_success(self, mock_chat):
        """Test health check returns success on working provider."""
        from backend.services.llm_providers import OpenAIProvider
        
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "OK"
        mock_llm.invoke.return_value = mock_response
        mock_chat.return_value = mock_llm
        
        provider = OpenAIProvider(api_key="test-key")
        result = provider.health_check()
        
        assert result["healthy"] == True
        assert result["provider"] == "openai"
        assert "latency_ms" in result
    
    @patch('backend.services.llm_providers.ChatOpenAI')
    def test_health_check_failure(self, mock_chat):
        """Test health check returns failure on error."""
        from backend.services.llm_providers import OpenAIProvider
        
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("API Error")
        mock_chat.return_value = mock_llm
        
        provider = OpenAIProvider(api_key="test-key")
        result = provider.health_check()
        
        assert result["healthy"] == False
        assert "error" in result
