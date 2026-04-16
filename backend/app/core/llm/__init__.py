"""
LLM Provider abstraction layer.

Core infrastructure for calling LLMs across all modules:
- Chat module (RAG responses)
- Agents module (system prompt generation)
- Intent classification
- Any future LLM usage

Usage:
    from app.core.llm import create_llm_provider
    
    provider = create_llm_provider("openai", {"model": "gpt-4"})
    response = await provider.chat([HumanMessage(content="Hello")])
"""
from app.core.llm.base import LLMProvider
from app.core.llm.factory import (
    create_llm_provider,
    get_available_providers,
    register_provider,
)

__all__ = [
    "LLMProvider",
    "create_llm_provider",
    "get_available_providers",
    "register_provider",
]
