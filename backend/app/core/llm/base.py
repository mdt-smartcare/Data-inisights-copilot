"""
Abstract base class for LLM providers.

Defines the interface that all LLM providers must implement.
Includes automatic PHI (Protected Health Information) redaction
before sending messages to external LLM APIs.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, AsyncIterator, Tuple

from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.core.utils.logging import get_logger
from app.core.utils.phi_redactor import PHIRedactor, get_phi_redactor

logger = get_logger(__name__)


class PHIRedactingChatModel(BaseChatModel):
    """
    A wrapper around any LangChain BaseChatModel that automatically applies
    PHI (Protected Health Information) redaction before sending to the LLM.
    
    This ensures ALL calls to .invoke(), .ainvoke(), .stream(), etc. are protected,
    regardless of whether calling code uses the provider's chat() method.
    
    Usage:
        raw_llm = ChatOpenAI(...)
        protected_llm = PHIRedactingChatModel(wrapped_llm=raw_llm)
        # Now all calls go through PHI redaction
        response = protected_llm.invoke([HumanMessage(content="patient SSN is 123-45-6789")])
    """
    
    # Pydantic field for the wrapped model - use Any to avoid strict validation
    wrapped_llm: Any = None
    
    # Pydantic v2 config
    model_config = {"arbitrary_types_allowed": True}
    
    @property
    def _llm_type(self) -> str:
        """Return the type of the wrapped LLM."""
        wrapped_type = getattr(self.wrapped_llm, '_llm_type', 'unknown')
        return f"phi_redacting_{wrapped_type}"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return identifying params of wrapped LLM."""
        wrapped_params = getattr(self.wrapped_llm, '_identifying_params', {})
        return {
            "wrapped_llm": wrapped_params,
            "phi_redaction": True,
        }
    
    def _get_redactor(self) -> PHIRedactor:
        """Get the PHI redactor instance."""
        return get_phi_redactor()
    
    def _redact_messages(
        self,
        messages: List[BaseMessage]
    ) -> Tuple[List[BaseMessage], Dict[str, str]]:
        """
        Redact PHI from all messages before sending to LLM.
        
        Returns:
            Tuple of (redacted messages, PHI mapping for restoration)
        """
        redactor = self._get_redactor()
        if not redactor.enabled:
            return messages, {}
        
        combined_mapping = {}
        redacted_messages = []
        
        for msg in messages:
            content = msg.content if hasattr(msg, 'content') else str(msg)
            if content:
                result = redactor.redact(content)
                combined_mapping.update(result.mapping)
                
                # Create new message with redacted content, preserving type
                if isinstance(msg, HumanMessage):
                    redacted_messages.append(HumanMessage(content=result.redacted_text))
                elif isinstance(msg, SystemMessage):
                    redacted_messages.append(SystemMessage(content=result.redacted_text))
                elif isinstance(msg, AIMessage):
                    redacted_messages.append(AIMessage(content=result.redacted_text))
                else:
                    redacted_messages.append(type(msg)(content=result.redacted_text))
            else:
                redacted_messages.append(msg)
        
        if combined_mapping:
            logger.debug(f"PHI redacted: {len(combined_mapping)} items before LLM call")
        
        return redacted_messages, combined_mapping
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate with PHI redaction applied."""
        redacted_messages, mapping = self._redact_messages(messages)
        
        # Call the underlying model
        result = self.wrapped_llm._generate(
            redacted_messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs
        )
        
        return result
    
    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Async generate with PHI redaction applied."""
        redacted_messages, mapping = self._redact_messages(messages)
        
        # Call the underlying model
        result = await self.wrapped_llm._agenerate(
            redacted_messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs
        )
        
        return result
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream with PHI redaction applied."""
        redacted_messages, mapping = self._redact_messages(messages)
        
        yield from self.wrapped_llm._stream(
            redacted_messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs
        )
    
    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Async stream with PHI redaction applied."""
        redacted_messages, mapping = self._redact_messages(messages)
        
        async for chunk in self.wrapped_llm._astream(
            redacted_messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs
        ):
            yield chunk


def wrap_llm_with_phi_protection(llm: BaseChatModel) -> BaseChatModel:
    """
    Wrap a LangChain LLM with automatic PHI redaction.
    
    Args:
        llm: Any LangChain BaseChatModel
        
    Returns:
        PHI-protected wrapper (or original if already wrapped or redaction disabled)
    """
    # Don't double-wrap
    if isinstance(llm, PHIRedactingChatModel):
        return llm
    
    # Check if redaction is enabled
    redactor = get_phi_redactor()
    if not redactor.enabled:
        logger.debug("PHI redaction disabled, returning unwrapped LLM")
        return llm
    
    logger.info(f"Wrapping LLM with PHI protection: {llm._llm_type}")
    return PHIRedactingChatModel(wrapped_llm=llm)


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
    
    PHI Protection:
    - Automatically redacts PHI from messages before LLM calls
    - Can optionally restore PHI placeholders in responses
    """
    
    # PHI Redactor instance (shared across providers)
    _phi_redactor: Optional[PHIRedactor] = None
    
    @classmethod
    def _get_phi_redactor(cls) -> PHIRedactor:
        """Get the PHI redactor instance (lazy initialization)."""
        if cls._phi_redactor is None:
            cls._phi_redactor = get_phi_redactor()
        return cls._phi_redactor
    
    def _redact_messages(
        self,
        messages: List[BaseMessage]
    ) -> Tuple[List[BaseMessage], Dict[str, str]]:
        """
        Redact PHI from all messages before sending to LLM.
        
        Args:
            messages: List of LangChain messages
            
        Returns:
            Tuple of (redacted messages, PHI mapping for restoration)
        """
        redactor = self._get_phi_redactor()
        if not redactor.enabled:
            return messages, {}
        
        combined_mapping = {}
        redacted_messages = []
        
        for msg in messages:
            content = msg.content if hasattr(msg, 'content') else str(msg)
            if content:
                result = redactor.redact(content)
                combined_mapping.update(result.mapping)
                
                # Create new message with redacted content
                if isinstance(msg, HumanMessage):
                    redacted_messages.append(HumanMessage(content=result.redacted_text))
                elif isinstance(msg, SystemMessage):
                    redacted_messages.append(SystemMessage(content=result.redacted_text))
                elif isinstance(msg, AIMessage):
                    redacted_messages.append(AIMessage(content=result.redacted_text))
                else:
                    # For other message types, try to preserve type
                    redacted_messages.append(type(msg)(content=result.redacted_text))
            else:
                redacted_messages.append(msg)
        
        if combined_mapping:
            logger.debug(f"PHI redacted from {len(combined_mapping)} items before LLM call")
        
        return redacted_messages, combined_mapping
    
    def _restore_phi_in_response(
        self,
        response: str,
        mapping: Dict[str, str]
    ) -> str:
        """
        Optionally restore PHI placeholders in LLM response.
        
        WARNING: Only use when necessary, as this re-introduces PHI.
        
        Args:
            response: LLM response text
            mapping: PHI placeholder -> original value mapping
            
        Returns:
            Response with PHI restored (if enabled) or original response
        """
        if not mapping:
            return response
        
        try:
            from app.core.config import get_settings
            settings = get_settings()
            if not getattr(settings, 'phi_restore_in_response', False):
                return response
        except Exception:
            return response
        
        redactor = self._get_phi_redactor()
        return redactor.restore(response, mapping)
    
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
        
        Automatically applies PHI redaction before sending to LLM.
        Default uses LangChain's ainvoke method.
        """
        # Redact PHI before LLM call
        redacted_messages, phi_mapping = self._redact_messages(messages)
        
        llm = self.get_langchain_llm()
        response = await llm.ainvoke(redacted_messages, **kwargs)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Optionally restore PHI in response
        return self._restore_phi_in_response(response_text, phi_mapping)
    
    def invoke(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        Synchronous chat - for backward compatibility.
        
        Automatically applies PHI redaction before sending to LLM.
        Use chat() for async code.
        """
        # Redact PHI before LLM call
        redacted_messages, phi_mapping = self._redact_messages(messages)
        
        llm = self.get_langchain_llm()
        response = llm.invoke(redacted_messages, **kwargs)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Optionally restore PHI in response
        return self._restore_phi_in_response(response_text, phi_mapping)
    
    async def stream(
        self,
        messages: List[BaseMessage],
        **kwargs: Any
    ) -> AsyncIterator[str]:
        """
        Stream responses from the LLM.
        
        Automatically applies PHI redaction before sending to LLM.
        Note: PHI restoration is not supported in streaming mode.
        """
        # Redact PHI before LLM call
        redacted_messages, _ = self._redact_messages(messages)
        
        llm = self.get_langchain_llm()
        async for chunk in llm.astream(redacted_messages, **kwargs):
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
