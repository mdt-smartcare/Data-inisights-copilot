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
    
    _PROVIDER_REGISTRY = {
        "openai": OpenAIProvider,
        "azure": AzureOpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
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


def register_provider(name: str, provider_class: Type[LLMProvider]) -> None:
    """
    Register a custom LLM provider at runtime.
    
    Args:
        name: Provider identifier (lowercase)
        provider_class: LLMProvider subclass
        
    Example:
        >>> class MyProvider(LLMProvider):
        ...     ...
        >>> register_provider("custom", MyProvider)
    """
    _ensure_registry()
    
    if not issubclass(provider_class, LLMProvider):
        raise TypeError(f"{provider_class} must be a subclass of LLMProvider")
    
    _PROVIDER_REGISTRY[name.lower()] = provider_class
    logger.info(f"Registered custom LLM provider: {name}")


def create_provider_from_ai_model(
    ai_model,
    api_key: Optional[str] = None,
    **override_kwargs: Any
) -> LLMProvider:
    """
    Create an LLM provider from an AIModel database record.
    
    This is a convenience function for creating providers from the
    ai_models registry table.
    
    Args:
        ai_model: AIModel instance from database
        api_key: Optional API key override
        **override_kwargs: Additional provider-specific overrides
        
    Returns:
        Configured LLMProvider instance
    """
    provider_name = ai_model.provider_name.lower()
    
    # Extract model name from model_id format "provider/model"
    model_id = ai_model.model_id
    if "/" in model_id:
        model_name = model_id.split("/", 1)[1]
    else:
        model_name = model_id
    
    config = {
        "model": model_name,
        **override_kwargs
    }
    
    if api_key:
        config["api_key"] = api_key
    
    if ai_model.api_base_url:
        config["base_url"] = ai_model.api_base_url
    
    # Handle Azure specifically
    if provider_name == "azure":
        config["deployment_name"] = model_name
        if ai_model.api_base_url:
            config["azure_endpoint"] = ai_model.api_base_url
        config.pop("model", None)
        config.pop("base_url", None)
    
    return create_llm_provider(provider_name, config)
