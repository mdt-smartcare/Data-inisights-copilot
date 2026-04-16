"""
Anthropic Claude LLM Provider.

Supports Claude models: claude-3-opus, claude-3-sonnet, claude-3-haiku, etc.
"""
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from app.core.config import get_settings
from app.core.llm.base import LLMProvider

logger = get_logger(__name__)


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude LLM provider using ChatAnthropic from LangChain.
    """
    
    def __init__(
        self,
        model: str = "claude-3-sonnet-20240229",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any
    ):
        """
        Initialize Anthropic provider.
        
        Args:
            model: Model name (e.g., 'claude-3-opus-20240229')
            api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env var)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
        """
        self._model_name = model
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_kwargs = kwargs
        self._llm: Optional[BaseChatModel] = None
        
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize the ChatAnthropic instance."""
        try:
            from langchain_anthropic import ChatAnthropic
            
            settings = get_settings()
            api_key = self._api_key or getattr(settings, 'anthropic_api_key', None)
            
            if not api_key:
                raise ValueError("Anthropic API key not provided")
            
            self._llm = ChatAnthropic(
                model=self._model_name,
                api_key=api_key,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                **self._extra_kwargs
            )
            
            logger.info(f"Anthropic provider initialized: model={self._model_name}")
            
        except ImportError:
            raise ImportError(
                "langchain-anthropic package required. "
                "Install with: pip install langchain-anthropic"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._init_llm()
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
            "api_key_configured": bool(self._api_key or getattr(get_settings(), 'anthropic_api_key', None)),
        }
