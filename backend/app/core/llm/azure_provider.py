"""
Azure OpenAI LLM Provider.

Supports Azure's deployment of OpenAI models with custom endpoints.
"""
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from app.core.config import get_settings
from app.core.llm.base import LLMProvider

logger = get_logger(__name__)


class AzureOpenAIProvider(LLMProvider):
    """
    Azure OpenAI LLM provider using AzureChatOpenAI from LangChain.
    """
    
    def __init__(
        self,
        deployment_name: str,
        azure_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        api_version: str = "2024-02-15-preview",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        **kwargs: Any
    ):
        """
        Initialize Azure OpenAI provider.
        
        Args:
            deployment_name: Azure deployment name
            azure_endpoint: Azure endpoint URL
            api_key: Azure API key
            api_version: API version string
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self._deployment_name = deployment_name
        self._azure_endpoint = azure_endpoint
        self._api_key = api_key
        self._api_version = api_version
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._extra_kwargs = kwargs
        self._llm: Optional[BaseChatModel] = None
        
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize the AzureChatOpenAI instance."""
        try:
            from langchain_openai import AzureChatOpenAI
            
            settings = get_settings()
            api_key = self._api_key or getattr(settings, 'azure_openai_api_key', None)
            endpoint = self._azure_endpoint or getattr(settings, 'azure_openai_endpoint', None)
            
            if not api_key:
                raise ValueError("Azure OpenAI API key not provided")
            if not endpoint:
                raise ValueError("Azure OpenAI endpoint not provided")
            
            self._llm = AzureChatOpenAI(
                deployment_name=self._deployment_name,
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version=self._api_version,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                **self._extra_kwargs
            )
            
            logger.info(f"Azure OpenAI provider initialized: deployment={self._deployment_name}")
            
        except ImportError:
            raise ImportError(
                "langchain-openai package required. "
                "Install with: pip install langchain-openai"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._init_llm()
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
            "deployment": self._deployment_name,
            "api_version": self._api_version,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "endpoint_configured": bool(self._azure_endpoint),
            "api_key_configured": bool(self._api_key),
        }
