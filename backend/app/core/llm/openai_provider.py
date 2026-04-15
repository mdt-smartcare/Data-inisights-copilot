"""
OpenAI LLM Provider.

Supports OpenAI API models: gpt-4, gpt-4-turbo, gpt-3.5-turbo, etc.
"""
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from app.core.config import get_settings
from app.core.llm.base import LLMProvider

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """
    OpenAI LLM provider using ChatOpenAI from LangChain.
    """
    
    def __init__(
        self,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any
    ):
        """
        Initialize OpenAI provider.
        
        Args:
            model: Model name (e.g., 'gpt-4', 'gpt-4-turbo')
            api_key: OpenAI API key (falls back to OPENAI_API_KEY env var)
            base_url: Optional custom API base URL
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
        """
        self._model_name = model
        self._api_key = api_key
        self._base_url = base_url
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_kwargs = kwargs
        self._llm: Optional[BaseChatModel] = None
        
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize the ChatOpenAI instance."""
        try:
            from langchain_openai import ChatOpenAI
            
            settings = get_settings()
            api_key = self._api_key or settings.openai_api_key
            
            if not api_key:
                raise ValueError("OpenAI API key not provided")
            
            llm_kwargs = {
                "model": self._model_name,
                "api_key": api_key,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                **self._extra_kwargs
            }
            
            if self._base_url:
                llm_kwargs["base_url"] = self._base_url
            
            self._llm = ChatOpenAI(**llm_kwargs)
            
            logger.info(f"OpenAI provider initialized: model={self._model_name}")
            
        except ImportError:
            raise ImportError(
                "langchain-openai package required. "
                "Install with: pip install langchain-openai"
            )
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._init_llm()
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
            "base_url": self._base_url,
            "api_key_configured": bool(self._api_key or get_settings().openai_api_key),
        }
