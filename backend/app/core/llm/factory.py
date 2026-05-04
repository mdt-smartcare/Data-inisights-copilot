"""
LLM Provider Factory.

Creates provider instances based on configuration.
Supports dynamic provider selection at runtime.
"""
from typing import Any, Dict, List, Optional, Type

from app.core.utils.logging import get_logger
from app.core.llm.base import LLMProvider

logger = get_logger(__name__)

# Provider registry - lazy loaded
_PROVIDER_REGISTRY: Dict[str, Type[LLMProvider]] = {}
_registry_initialized = False


def _ensure_registry() -> None:
    """Populate the provider registry on first access."""
    global _PROVIDER_REGISTRY, _registry_initialized
    
    if _registry_initialized:
        return
    
    from app.core.llm.openai_provider import OpenAIProvider
    from app.core.llm.azure_provider import AzureOpenAIProvider
    from app.core.llm.anthropic_provider import AnthropicProvider
    from app.core.llm.ollama_provider import OllamaProvider
    from app.core.llm.huggingface_local_provider import HuggingFaceLocalProvider
    
    _PROVIDER_REGISTRY = {
        "openai": OpenAIProvider,
        "azure": AzureOpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
        "huggingface": HuggingFaceLocalProvider,
    }
    _registry_initialized = True


def get_available_providers() -> List[str]:
    """Get list of available provider names."""
    _ensure_registry()
    return list(_PROVIDER_REGISTRY.keys())


def create_llm_provider(
    provider_type: str,
    config: Optional[Dict[str, Any]] = None,
) -> LLMProvider:
    """
    Factory function to create LLM provider instances.
    
    Args:
        provider_type: Provider identifier ('openai', 'azure', 'anthropic', 'ollama')
        config: Provider-specific configuration dictionary
        
    Returns:
        Configured LLMProvider instance
        
    Raises:
        ValueError: If provider_type is not recognized
        
    Example:
        >>> from app.core.llm import create_llm_provider
        >>> provider = create_llm_provider("openai", {"model": "gpt-4", "temperature": 0.7})
        >>> response = await provider.chat([HumanMessage(content="Hello")])
    """
    _ensure_registry()
    
    config = config or {}
    provider_type = provider_type.lower()
    
    if provider_type not in _PROVIDER_REGISTRY:
        available = list(_PROVIDER_REGISTRY.keys())
        raise ValueError(f"Unknown provider: '{provider_type}'. Available: {available}")
    
    provider_class = _PROVIDER_REGISTRY[provider_type]
    
    logger.info(f"Creating LLM provider: {provider_type}", config_keys=list(config.keys()))
    
    try:
        return provider_class(**config)
    except Exception as e:
        logger.error(f"Failed to create {provider_type} provider: {e}")
        raise
