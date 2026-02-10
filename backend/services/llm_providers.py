"""
LLM Providers - Abstraction layer for multiple LLM backends.
Provides a unified interface for different LLM services (OpenAI, Azure, Anthropic, Ollama, HuggingFace, Local).
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
import time
import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage

from backend.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Abstract Base Class
# =============================================================================

class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All LLM providers must implement:
    - get_langchain_llm: Return a LangChain-compatible chat model
    - provider_name: Return provider identifier
    - model_name: Return current model name
    """
    
    @abstractmethod
    def get_langchain_llm(self) -> BaseChatModel:
        """
        Get a LangChain-compatible chat model instance.
        
        Returns:
            BaseChatModel instance for use with LangChain agents
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider identifier (e.g., 'openai', 'anthropic', 'ollama')."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the current model name."""
        pass
    
    def chat(self, messages: List[BaseMessage]) -> str:
        """
        Send messages and get a response.
        
        Args:
            messages: List of LangChain message objects
            
        Returns:
            String response from the LLM
        """
        llm = self.get_langchain_llm()
        response = llm.invoke(messages)
        return response.content
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the provider.
        
        Returns:
            Dict with 'healthy' bool and optional 'error' message
        """
        try:
            start = time.time()
            # Attempt a simple completion
            test_response = self.chat([HumanMessage(content="Say 'OK' and nothing else.")])
            latency_ms = (time.time() - start) * 1000
            
            return {
                "healthy": True,
                "provider": self.provider_name,
                "model": self.model_name,
                "latency_ms": round(latency_ms, 2),
                "test_response": test_response[:50]
            }
        except Exception as e:
            logger.error(f"Health check failed for {self.provider_name}: {e}")
            return {
                "healthy": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "error": str(e)
            }
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the current provider configuration.
        Override in subclasses for provider-specific config.
        """
        return {
            "provider": self.provider_name,
            "model": self.model_name
        }


# =============================================================================
# OpenAI Provider
# =============================================================================

class OpenAIProvider(LLMProvider):
    """
    OpenAI LLM provider using GPT-4o, GPT-4, GPT-3.5-turbo, etc.
    
    Requires OPENAI_API_KEY environment variable or explicit api_key.
    """
    
    AVAILABLE_MODELS = [
        "gpt-4o",
        "gpt-4o-mini", 
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1-preview",
        "o1-mini"
    ]
    
    def __init__(
        self,
        model_name: str = "gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any
    ):
        """
        Initialize OpenAI provider.
        
        Args:
            model_name: OpenAI model name
            api_key: Optional API key (falls back to env var)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._llm = None
        
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the LangChain ChatOpenAI instance."""
        try:
            from langchain_openai import ChatOpenAI
            
            if not self._api_key:
                raise ValueError("OpenAI API key not provided")
            
            # Add Langfuse callback if enabled
            from backend.core.tracing import get_tracing_manager
            tracer = get_tracing_manager()
            langfuse_handler = tracer.get_langchain_callback()
            callbacks = [langfuse_handler] if langfuse_handler else []

            self._llm = ChatOpenAI(
                model=self._model_name,
                api_key=self._api_key,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                callbacks=callbacks
            )
            logger.info(f"OpenAI provider initialized with model: {self._model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        """Get the LangChain ChatOpenAI instance."""
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model_name,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "api_key_configured": bool(self._api_key)
        }


# =============================================================================
# Azure OpenAI Provider
# =============================================================================

class AzureOpenAIProvider(LLMProvider):
    """
    Azure OpenAI LLM provider.
    
    Requires AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT environment variables.
    """
    
    def __init__(
        self,
        deployment_name: str,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: str = "2024-02-01",
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any
    ):
        """
        Initialize Azure OpenAI provider.
        
        Args:
            deployment_name: Azure deployment name
            api_key: Optional API key (falls back to env var)
            azure_endpoint: Azure OpenAI endpoint URL
            api_version: API version
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self._deployment_name = deployment_name
        self._api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self._azure_endpoint = azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self._api_version = api_version
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._llm = None
        
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the LangChain AzureChatOpenAI instance."""
        try:
            from langchain_openai import AzureChatOpenAI
            
            if not self._api_key:
                raise ValueError("Azure OpenAI API key not provided")
            if not self._azure_endpoint:
                raise ValueError("Azure OpenAI endpoint not provided")
            
            # Add Langfuse callback if enabled
            from backend.core.tracing import get_tracing_manager
            tracer = get_tracing_manager()
            langfuse_handler = tracer.get_langchain_callback()
            callbacks = [langfuse_handler] if langfuse_handler else []

            self._llm = AzureChatOpenAI(
                azure_deployment=self._deployment_name,
                api_key=self._api_key,
                azure_endpoint=self._azure_endpoint,
                api_version=self._api_version,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                callbacks=callbacks
            )
            logger.info(f"Azure OpenAI provider initialized with deployment: {self._deployment_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "azure"
    
    @property
    def model_name(self) -> str:
        return self._deployment_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "deployment_name": self._deployment_name,
            "azure_endpoint": self._azure_endpoint,
            "api_version": self._api_version,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "api_key_configured": bool(self._api_key)
        }


# =============================================================================
# Anthropic Provider
# =============================================================================

class AnthropicProvider(LLMProvider):
    """
    Anthropic LLM provider using Claude models.
    
    Requires ANTHROPIC_API_KEY environment variable or explicit api_key.
    """
    
    AVAILABLE_MODELS = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307"
    ]
    
    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any
    ):
        """
        Initialize Anthropic provider.
        
        Args:
            model_name: Claude model name
            api_key: Optional API key (falls back to env var)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._llm = None
        
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the LangChain ChatAnthropic instance."""
        try:
            from langchain_anthropic import ChatAnthropic
            
            if not self._api_key:
                raise ValueError("Anthropic API key not provided")
            
            # Add Langfuse callback if enabled
            from backend.core.tracing import get_tracing_manager
            tracer = get_tracing_manager()
            langfuse_handler = tracer.get_langchain_callback()
            callbacks = [langfuse_handler] if langfuse_handler else []

            self._llm = ChatAnthropic(
                model=self._model_name,
                api_key=self._api_key,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                callbacks=callbacks
            )
            logger.info(f"Anthropic provider initialized with model: {self._model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model_name,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "api_key_configured": bool(self._api_key)
        }


# =============================================================================
# Ollama Provider (Local)
# =============================================================================

class OllamaProvider(LLMProvider):
    """
    Ollama LLM provider for running local models.
    
    Requires Ollama to be running locally (default: http://localhost:11434).
    """
    
    POPULAR_MODELS = [
        "llama3.2",
        "llama3.1",
        "mistral",
        "mixtral",
        "codellama",
        "phi3",
        "gemma2",
        "qwen2.5"
    ]
    
    def __init__(
        self,
        model_name: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.0,
        **kwargs: Any
    ):
        """
        Initialize Ollama provider.
        
        Args:
            model_name: Ollama model name (must be pulled first)
            base_url: Ollama server URL
            temperature: Sampling temperature
        """
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature
        self._llm = None
        
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the LangChain ChatOllama instance."""
        try:
            from langchain_ollama import ChatOllama
            
            self._llm = ChatOllama(
                model=self._model_name,
                base_url=self._base_url,
                temperature=self._temperature
            )
            logger.info(f"Ollama provider initialized with model: {self._model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Ollama provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model_name,
            "base_url": self._base_url,
            "temperature": self._temperature
        }


# =============================================================================
# HuggingFace Provider
# =============================================================================

class HuggingFaceProvider(LLMProvider):
    """
    HuggingFace LLM provider.
    
    Supports both HuggingFace Inference API and local model loading.
    Requires HUGGINGFACEHUB_API_TOKEN for API mode.
    """
    
    POPULAR_MODELS = [
        "meta-llama/Llama-3.2-3B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "microsoft/Phi-3-mini-4k-instruct",
        "google/gemma-2-2b-it",
        "Qwen/Qwen2.5-7B-Instruct"
    ]
    
    def __init__(
        self,
        model_name: str = "meta-llama/Llama-3.2-3B-Instruct",
        api_key: Optional[str] = None,
        use_api: bool = True,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        **kwargs: Any
    ):
        """
        Initialize HuggingFace provider.
        
        Args:
            model_name: HuggingFace model ID
            api_key: Optional API token (falls back to env var)
            use_api: If True, use HF Inference API; if False, load locally
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self._model_name = model_name
        self._api_key = api_key or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        self._use_api = use_api
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._llm = None
        
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the HuggingFace LLM instance."""
        try:
            if self._use_api:
                from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
                
                if not self._api_key:
                    raise ValueError("HuggingFace API token not provided")
                
                llm = HuggingFaceEndpoint(
                    repo_id=self._model_name,
                    huggingfacehub_api_token=self._api_key,
                    temperature=self._temperature,
                    max_new_tokens=self._max_tokens
                )
                self._llm = ChatHuggingFace(llm=llm)
                logger.info(f"HuggingFace API provider initialized with model: {self._model_name}")
            else:
                from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline
                
                llm = HuggingFacePipeline.from_model_id(
                    model_id=self._model_name,
                    task="text-generation",
                    pipeline_kwargs={
                        "temperature": self._temperature,
                        "max_new_tokens": self._max_tokens
                    }
                )
                self._llm = ChatHuggingFace(llm=llm)
                logger.info(f"HuggingFace local provider initialized with model: {self._model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize HuggingFace provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "huggingface"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model_name,
            "use_api": self._use_api,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "api_key_configured": bool(self._api_key) if self._use_api else "N/A"
        }


# =============================================================================
# Local LLM Provider (LlamaCpp for GGUF models)
# =============================================================================

class LocalLLMProvider(LLMProvider):
    """
    Local LLM provider using LlamaCpp for GGUF models.
    
    Fully offline - loads quantized GGUF models from local disk.
    """
    
    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = 0,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any
    ):
        """
        Initialize Local LLM provider with LlamaCpp.
        
        Args:
            model_path: Path to GGUF model file
            n_ctx: Context window size
            n_gpu_layers: Number of layers to offload to GPU (0 = CPU only)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._llm = None
        self._model_name_extracted = self._extract_model_name()
        
        self._init_llm()
    
    def _extract_model_name(self) -> str:
        """Extract model name from path."""
        from pathlib import Path
        return Path(self._model_path).stem
    
    def _init_llm(self):
        """Initialize the LlamaCpp LLM instance."""
        try:
            from langchain_community.llms import LlamaCpp
            from langchain_community.chat_models import ChatLlamaCpp
            
            # Use ChatLlamaCpp for chat interface
            self._llm = ChatLlamaCpp(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_gpu_layers=self._n_gpu_layers,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                verbose=False
            )
            logger.info(f"Local LLM provider initialized with model: {self._model_name_extracted}")
        except ImportError:
            # Fallback to standard LlamaCpp if ChatLlamaCpp not available
            try:
                from langchain_community.llms import LlamaCpp
                
                self._llm = LlamaCpp(
                    model_path=self._model_path,
                    n_ctx=self._n_ctx,
                    n_gpu_layers=self._n_gpu_layers,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    verbose=False
                )
                logger.info(f"Local LLM provider initialized (base) with model: {self._model_name_extracted}")
            except Exception as e:
                logger.error(f"Failed to initialize Local LLM provider: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to initialize Local LLM provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "local"
    
    @property
    def model_name(self) -> str:
        return self._model_name_extracted
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model_name_extracted,
            "model_path": self._model_path,
            "n_ctx": self._n_ctx,
            "n_gpu_layers": self._n_gpu_layers,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens
        }


# =============================================================================
# Factory Function
# =============================================================================

def create_llm_provider(
    provider_type: str,
    config: Optional[Dict[str, Any]] = None
) -> LLMProvider:
    """
    Factory function to create LLM providers.
    
    Args:
        provider_type: One of 'openai', 'azure', 'anthropic', 'ollama', 'huggingface', 'local'
        config: Provider-specific configuration
        
    Returns:
        Configured LLMProvider instance
    """
    config = config or {}
    
    providers = {
        "openai": OpenAIProvider,
        "azure": AzureOpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "huggingface": HuggingFaceProvider,
        "local": LocalLLMProvider
    }
    
    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    
    logger.info(f"Creating LLM provider: {provider_type}")
    return providers[provider_type](**config)
