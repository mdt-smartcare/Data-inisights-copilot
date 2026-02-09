"""
LLM Registry - Manages LLM providers with hot-swap capability.
Provides a singleton registry for dynamic provider switching without restarts.
"""
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path

from backend.services.llm_providers import (
    LLMProvider,
    OpenAIProvider,
    AzureOpenAIProvider,
    AnthropicProvider,
    OllamaProvider,
    HuggingFaceProvider,
    LocalLLMProvider,
    create_llm_provider
)
from backend.core.logging import get_logger

logger = get_logger(__name__)


class LLMRegistry:
    """
    Singleton registry for managing LLM providers.
    
    Supports:
    - Hot-swap between providers at runtime
    - Provider registration and discovery
    - Thread-safe provider switching
    - Configuration persistence via SettingsService
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Available provider types and their default configs
    PROVIDER_CATALOG = {
        "openai": {
            "class": OpenAIProvider,
            "display_name": "OpenAI",
            "description": "OpenAI GPT models (GPT-4o, GPT-4, GPT-3.5-turbo)",
            "default_config": {
                "model_name": "gpt-4o",
                "temperature": 0.0,
                "max_tokens": 4096
            },
            "requires_api_key": True,
            "models": [
                "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", 
                "gpt-4", "gpt-3.5-turbo", "o1-preview", "o1-mini"
            ]
        },
        "azure": {
            "class": AzureOpenAIProvider,
            "display_name": "Azure OpenAI",
            "description": "Azure-hosted OpenAI models",
            "default_config": {
                "deployment_name": "",
                "api_version": "2024-02-01",
                "temperature": 0.0,
                "max_tokens": 4096
            },
            "requires_api_key": True,
            "requires_endpoint": True,
            "models": []  # User specifies deployment name
        },
        "anthropic": {
            "class": AnthropicProvider,
            "display_name": "Anthropic Claude",
            "description": "Anthropic Claude models (Claude 3.5, Claude 3)",
            "default_config": {
                "model_name": "claude-3-5-sonnet-20241022",
                "temperature": 0.0,
                "max_tokens": 4096
            },
            "requires_api_key": True,
            "models": [
                "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"
            ]
        },
        "ollama": {
            "class": OllamaProvider,
            "display_name": "Ollama (Local)",
            "description": "Local models via Ollama (Llama, Mistral, etc.)",
            "default_config": {
                "model_name": "llama3.2",
                "base_url": "http://localhost:11434",
                "temperature": 0.0
            },
            "requires_api_key": False,
            "models": [
                "llama3.2", "llama3.1", "mistral", "mixtral",
                "codellama", "phi3", "gemma2", "qwen2.5"
            ]
        },
        "huggingface": {
            "class": HuggingFaceProvider,
            "display_name": "HuggingFace",
            "description": "HuggingFace models (API or local inference)",
            "default_config": {
                "model_name": "meta-llama/Llama-3.2-3B-Instruct",
                "use_api": True,
                "temperature": 0.0,
                "max_tokens": 4096
            },
            "requires_api_key": True,  # For API mode
            "models": [
                "meta-llama/Llama-3.2-3B-Instruct",
                "mistralai/Mistral-7B-Instruct-v0.3",
                "microsoft/Phi-3-mini-4k-instruct",
                "google/gemma-2-2b-it",
                "Qwen/Qwen2.5-7B-Instruct"
            ]
        },
        "local": {
            "class": LocalLLMProvider,
            "display_name": "Local LLM (GGUF)",
            "description": "Local GGUF models via LlamaCpp (fully offline)",
            "default_config": {
                "model_path": "",
                "n_ctx": 4096,
                "n_gpu_layers": 0,
                "temperature": 0.0,
                "max_tokens": 2048
            },
            "requires_api_key": False,
            "models": []  # Scanned from local directory
        }
    }
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._active_provider: Optional[LLMProvider] = None
        self._active_provider_type: str = "openai"  # Default
        self._active_config: Dict[str, Any] = {}
        
        # Load initial provider
        self._load_initial_provider()
        self._initialized = True
    
    def _load_initial_provider(self):
        """Load the initial provider based on settings."""
        import os
        try:
            # Try to load from settings service
            from backend.services.settings_service import get_settings_service
            settings_svc = get_settings_service()
            all_settings = settings_svc.get_all_settings()
            llm_settings = all_settings.get("llm", {})
            
            provider_type = llm_settings.get("provider", "openai")
            
            # Build config from settings
            config = {
                "model_name": llm_settings.get("model_name", "gpt-4o"),
                "temperature": float(llm_settings.get("temperature", 0.0)),
                "max_tokens": int(llm_settings.get("max_tokens", 4096))
            }
            
            # Get API key from settings or env (settings may be masked)
            api_key = llm_settings.get("api_key", "")
            if api_key and api_key != "***MASKED***":
                config["api_key"] = api_key
            else:
                # Fallback to environment variables based on provider type
                if provider_type == "openai":
                    config["api_key"] = os.getenv("OPENAI_API_KEY", "")
                elif provider_type == "anthropic":
                    config["api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
                elif provider_type == "huggingface":
                    config["api_key"] = os.getenv("HUGGINGFACE_API_KEY", "")
                elif provider_type == "azure":
                    config["api_key"] = os.getenv("AZURE_OPENAI_API_KEY", "")
                    config["endpoint"] = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            
            logger.info(f"Loading initial LLM provider from settings: {provider_type}")
            self._set_provider(provider_type, config)
            
        except Exception as e:
            logger.warning(f"Could not load from settings, using default OpenAI: {e}")
            # Fall back to environment-based OpenAI
            try:
                default_config = self.PROVIDER_CATALOG["openai"]["default_config"].copy()
                default_config["api_key"] = os.getenv("OPENAI_API_KEY", "")
                self._set_provider("openai", default_config)
            except Exception as e2:
                logger.error(f"Failed to initialize default OpenAI provider: {e2}")
                self._active_provider = None
    
    def _set_provider(self, provider_type: str, config: Dict[str, Any]):
        """Internal method to set the active provider."""
        if provider_type not in self.PROVIDER_CATALOG:
            raise ValueError(f"Unknown provider: {provider_type}")
        
        with self._lock:
            # Create new provider
            provider = create_llm_provider(provider_type, config)
            
            # Store old provider for cleanup hint
            old_provider = self._active_provider
            
            # Switch
            self._active_provider = provider
            self._active_provider_type = provider_type
            self._active_config = config.copy()
            
            logger.info(f"Active LLM provider set to: {provider_type} ({provider.model_name})")
            
            # Hint for old provider cleanup (Python GC will handle it)
            if old_provider and old_provider is not provider:
                logger.debug("Previous provider will be garbage collected")
    
    def get_active_provider(self) -> LLMProvider:
        """
        Get the currently active LLM provider.
        
        Returns:
            The active LLMProvider instance
        """
        if self._active_provider is None:
            raise RuntimeError("No active LLM provider configured")
        return self._active_provider
    
    def get_langchain_llm(self):
        """
        Convenience method to get LangChain-compatible LLM from active provider.
        
        Returns:
            LangChain BaseChatModel instance
        """
        return self.get_active_provider().get_langchain_llm()
    
    def set_active_provider(
        self,
        provider_type: str,
        config: Optional[Dict[str, Any]] = None,
        persist: bool = True,
        updated_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Switch to a different LLM provider (hot-swap).
        
        Args:
            provider_type: One of the registered provider types
            config: Optional provider-specific configuration
            persist: Whether to persist the change to settings DB
            updated_by: Username making the change
            
        Returns:
            Dict with success status and provider info
        """
        if provider_type not in self.PROVIDER_CATALOG:
            raise ValueError(
                f"Unknown provider: {provider_type}. "
                f"Available: {list(self.PROVIDER_CATALOG.keys())}"
            )
        
        # Merge with default config
        default_cfg = self.PROVIDER_CATALOG[provider_type]["default_config"].copy()
        if config:
            default_cfg.update(config)
        
        logger.info(f"Switching LLM provider to: {provider_type}")
        
        # Set the new provider
        self._set_provider(provider_type, default_cfg)
        
        # Persist to settings if requested
        if persist:
            try:
                from backend.services.settings_service import get_settings_service
                settings_svc = get_settings_service()
                
                # Map to settings format
                settings_svc.update_setting("llm", "provider", provider_type, updated_by)
                settings_svc.update_setting("llm", "model_name", default_cfg.get("model_name", ""), updated_by)
                settings_svc.update_setting("llm", "temperature", default_cfg.get("temperature", 0.0), updated_by)
                settings_svc.update_setting("llm", "max_tokens", default_cfg.get("max_tokens", 4096), updated_by)
                
                # Only persist API key if explicitly provided and not empty
                if "api_key" in default_cfg and default_cfg["api_key"]:
                    settings_svc.update_setting("llm", "api_key", default_cfg["api_key"], updated_by)
                    
                logger.info("LLM provider settings persisted to database")
            except Exception as e:
                logger.error(f"Failed to persist LLM provider settings: {e}")
        
        return {
            "success": True,
            "provider": provider_type,
            "config": self._active_provider.get_config()
        }
    
    def get_active_provider_type(self) -> str:
        """Get the type name of the active provider."""
        return self._active_provider_type
    
    def get_active_config(self) -> Dict[str, Any]:
        """Get the configuration of the active provider."""
        if self._active_provider:
            return self._active_provider.get_config()
        return {}
    
    def _list_local_models(self) -> List[str]:
        """List GGUF models available in the local models directory."""
        try:
            backend_root = Path(__file__).parent.parent
            models_dir = backend_root / "models"
            
            if not models_dir.exists():
                return []
            
            # Find all .gguf files
            gguf_files = []
            for item in models_dir.rglob("*.gguf"):
                gguf_files.append(str(item.relative_to(models_dir)))
            
            return sorted(gguf_files)
        except Exception as e:
            logger.warning(f"Failed to list local GGUF models: {e}")
            return []
    
    def list_providers(self) -> List[Dict[str, Any]]:
        """
        List all available provider types with their metadata.
        
        Returns:
            List of provider info dicts
        """
        result = []
        local_models = self._list_local_models()
        
        for name, info in self.PROVIDER_CATALOG.items():
            provider_info = {
                "name": name,
                "display_name": info["display_name"],
                "description": info["description"],
                "requires_api_key": info.get("requires_api_key", False),
                "requires_endpoint": info.get("requires_endpoint", False),
                "is_active": name == self._active_provider_type,
                "default_config": info["default_config"],
                "models": info.get("models", [])
            }
            
            # Attach local GGUF models for local provider
            if name == "local":
                provider_info["models"] = local_models
                
            result.append(provider_info)
        return result
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the active provider.
        
        Returns:
            Health check results
        """
        if not self._active_provider:
            return {"healthy": False, "error": "No active provider"}
        return self._active_provider.health_check()
    
    def test_provider(
        self,
        provider_type: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Test a provider configuration without activating it.
        
        Args:
            provider_type: Provider type to test
            config: Provider configuration
            
        Returns:
            Test results with health status
        """
        if provider_type not in self.PROVIDER_CATALOG:
            return {"success": False, "error": f"Unknown provider: {provider_type}"}
        
        try:
            # Merge with defaults
            default_cfg = self.PROVIDER_CATALOG[provider_type]["default_config"].copy()
            if config:
                default_cfg.update(config)
            
            # Create temporary provider
            test_provider = create_llm_provider(provider_type, default_cfg)
            
            # Run health check
            health = test_provider.health_check()
            
            return {
                "success": health.get("healthy", False),
                "provider": provider_type,
                "health": health,
                "config": test_provider.get_config()
            }
        except Exception as e:
            logger.error(f"LLM provider test failed: {e}")
            return {
                "success": False,
                "provider": provider_type,
                "error": str(e)
            }


# =============================================================================
# Singleton accessor
# =============================================================================

_llm_registry: Optional[LLMRegistry] = None
_registry_lock = threading.Lock()


def get_llm_registry() -> LLMRegistry:
    """Get the singleton LLMRegistry instance."""
    global _llm_registry
    if _llm_registry is None:
        with _registry_lock:
            if _llm_registry is None:
                _llm_registry = LLMRegistry()
    return _llm_registry
