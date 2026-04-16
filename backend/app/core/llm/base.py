"""
Abstract base class for LLM providers.

Defines the interface that all LLM providers must implement.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncIterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All providers must implement:
    - get_langchain_llm() - Returns LangChain-compatible LLM
    - provider_name - Provider identifier
    - model_name - Model identifier
    - get_config() - Configuration dictionary
    
    Optional overrides:
    - chat() - Direct chat method (default uses LangChain)
    - stream() - Streaming response
    - health_check() - Verify provider is operational
    """
    
    @abstractmethod
    def get_langchain_llm(self) -> BaseChatModel:
        """
        Get a LangChain-compatible LLM instance.
        
        Returns:
            BaseChatModel instance for use with LangChain chains
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'openai', 'anthropic')."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier (e.g., 'gpt-4', 'claude-3-opus')."""
        pass
    
    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """
        Get provider configuration (excluding secrets).
        
        Returns:
            Dict with provider settings
        """
        pass
    
    async def chat(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        Send messages and get a response.
        
        Default uses LangChain's ainvoke method.
        """
        llm = self.get_langchain_llm()
        response = await llm.ainvoke(messages, **kwargs)
        return response.content if hasattr(response, 'content') else str(response)
    
    def invoke(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        Synchronous chat - for backward compatibility.
        
        Use chat() for async code.
        """
        llm = self.get_langchain_llm()
        response = llm.invoke(messages, **kwargs)
        return response.content if hasattr(response, 'content') else str(response)
    
    async def stream(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """
        Stream responses from the LLM.
        """
        llm = self.get_langchain_llm()
        async for chunk in llm.astream(messages, **kwargs):
            if hasattr(chunk, 'content') and chunk.content:
                yield chunk.content
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the provider is operational.
        """
        try:
            test_messages = [HumanMessage(content="Hello")]
            response = await self.chat(test_messages)
            
            return {
                "healthy": bool(response),
                "provider": self.provider_name,
                "model": self.model_name,
                "message": "Provider operational"
            }
        except Exception as e:
            logger.error(f"Health check failed for {self.provider_name}: {e}")
            return {
                "healthy": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "message": str(e)
            }
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider_name}, model={self.model_name})"
