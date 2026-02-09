"""
Embedding Registry - Manages embedding providers with hot-swap capability.
Provides a singleton registry for dynamic provider switching without restarts.
"""
import threading
from typing import Dict, Any, Optional, List
from functools import lru_cache

from backend.services.embedding_providers import (
    EmbeddingProvider,
    BGEProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformerProvider,
    create_embedding_provider
)
from backend.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingRegistry:
    """
    Singleton registry for managing embedding providers.
    
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
        "bge-m3": {
            "class": BGEProvider,
            "display_name": "BGE-M3 (Local)",
            "description": "High-quality multilingual embeddings (1024 dims, local)",
            "default_config": {
                "model_path": "./models/bge-m3",
                "model_name": "BAAI/bge-m3",
                "batch_size": 128,
                "normalize": True
            },
            "requires_api_key": False
        },
        "openai": {
            "class": OpenAIEmbeddingProvider,
            "display_name": "OpenAI Embeddings",
            "description": "Cloud-based embeddings via OpenAI API",
            "default_config": {
                "model_name": "text-embedding-3-small",
                "batch_size": 100
            },
            "requires_api_key": True
        },
        "sentence-transformers": {
            "class": SentenceTransformerProvider,
            "display_name": "Sentence Transformers",
            "description": "Generic HuggingFace models (customizable)",
            "default_config": {
                "model_name": "all-MiniLM-L6-v2",
                "batch_size": 128,
                "normalize": True
            },
            "requires_api_key": False
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
            
        self._active_provider: Optional[EmbeddingProvider] = None
        self._active_provider_type: str = "bge-m3"  # Default
        self._active_config: Dict[str, Any] = {}
        self._providers_cache: Dict[str, EmbeddingProvider] = {}
        
        # Load initial provider
        self._load_initial_provider()
        self._initialized = True
    
    def _load_initial_provider(self):
        """Load the initial provider based on settings."""
        try:
            # Try to load from settings service
            from backend.services.settings_service import get_settings_service
            settings_svc = get_settings_service()
            all_settings = settings_svc.get_all_settings()
            embedding_settings = all_settings.get("embedding", {})
            
            provider_type = embedding_settings.get("provider", "bge-m3")
            config = {
                "model_name": embedding_settings.get("model_name", "BAAI/bge-m3"),
                "model_path": embedding_settings.get("model_path", "./models/bge-m3"),
                "batch_size": embedding_settings.get("batch_size", 128)
            }
            
            logger.info(f"Loading initial provider from settings: {provider_type}")
            self._set_provider(provider_type, config)
            
        except Exception as e:
            logger.warning(f"Could not load from settings, using default BGE: {e}")
            self._set_provider("bge-m3", self.PROVIDER_CATALOG["bge-m3"]["default_config"])
    
    def _set_provider(self, provider_type: str, config: Dict[str, Any]):
        """Internal method to set the active provider."""
        if provider_type not in self.PROVIDER_CATALOG:
            raise ValueError(f"Unknown provider: {provider_type}")
        
        with self._lock:
            # Create new provider
            provider = create_embedding_provider(provider_type, config)
            
            # Store old provider for cleanup hint
            old_provider = self._active_provider
            
            # Switch
            self._active_provider = provider
            self._active_provider_type = provider_type
            self._active_config = config.copy()
            
            logger.info(f"Active provider set to: {provider_type}")
            
            # Hint for old provider cleanup (Python GC will handle it)
            if old_provider and old_provider is not provider:
                logger.debug("Previous provider will be garbage collected")
    
    def get_active_provider(self) -> EmbeddingProvider:
        """
        Get the currently active embedding provider.
        
        Returns:
            The active EmbeddingProvider instance
        """
        if self._active_provider is None:
            raise RuntimeError("No active embedding provider configured")
        return self._active_provider
    
    def set_active_provider(
        self,
        provider_type: str,
        config: Optional[Dict[str, Any]] = None,
        persist: bool = True
    ) -> Dict[str, Any]:
        """
        Switch to a different embedding provider (hot-swap).
        
        Args:
            provider_type: One of the registered provider types
            config: Optional provider-specific configuration
            persist: Whether to persist the change to settings DB
            
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
        
        logger.info(f"Switching embedding provider to: {provider_type}")
        
        # Set the new provider
        self._set_provider(provider_type, default_cfg)
        
        # Persist to settings if requested
        if persist:
            try:
                from backend.services.settings_service import get_settings_service
                settings_svc = get_settings_service()
                
                # Map to settings format
                settings_svc.update_setting("embedding", "provider", provider_type)
                settings_svc.update_setting("embedding", "model_name", default_cfg.get("model_name", ""))
                if "model_path" in default_cfg:
                    settings_svc.update_setting("embedding", "model_path", default_cfg.get("model_path", ""))
                if "batch_size" in default_cfg:
                    settings_svc.update_setting("embedding", "batch_size", default_cfg.get("batch_size", 128))
                    
                logger.info("Provider settings persisted to database")
            except Exception as e:
                logger.error(f"Failed to persist provider settings: {e}")
        
        return {
            "success": True,
            "provider": provider_type,
            "config": self._active_provider.get_config(),
            "requires_reindex": True  # Flag that reindex may be needed
        }
    
    def get_active_provider_type(self) -> str:
        """Get the type name of the active provider."""
        return self._active_provider_type
    
    def get_active_config(self) -> Dict[str, Any]:
        """Get the configuration of the active provider."""
        if self._active_provider:
            return self._active_provider.get_config()
        return {}
    
    def list_providers(self) -> List[Dict[str, Any]]:
        """
        List all available provider types with their metadata.
        
        Returns:
            List of provider info dicts
        """
        result = []
        for name, info in self.PROVIDER_CATALOG.items():
            result.append({
                "name": name,
                "display_name": info["display_name"],
                "description": info["description"],
                "requires_api_key": info["requires_api_key"],
                "is_active": name == self._active_provider_type,
                "default_config": info["default_config"]
            })
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
            test_provider = create_embedding_provider(provider_type, default_cfg)
            
            # Run health check
            health = test_provider.health_check()
            
            return {
                "success": health.get("healthy", False),
                "provider": provider_type,
                "health": health,
                "config": test_provider.get_config()
            }
        except Exception as e:
            logger.error(f"Provider test failed: {e}")
            return {
                "success": False,
                "provider": provider_type,
                "error": str(e)
            }


# =============================================================================
# Singleton accessor
# =============================================================================

def get_embedding_registry() -> EmbeddingRegistry:
    """Get the singleton EmbeddingRegistry instance."""
    return EmbeddingRegistry()


# =============================================================================
# LangChain-compatible wrapper
# =============================================================================

from langchain_core.embeddings import Embeddings

class DynamicEmbeddings(Embeddings):
    """
    LangChain-compatible embeddings wrapper that uses the active provider.
    
    This class provides backward compatibility with code expecting
    the old LocalHuggingFaceEmbeddings interface while using the
    dynamic provider registry.
    """
    
    def __init__(self):
        """Initialize with reference to registry."""
        self._registry = get_embedding_registry()
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed documents using active provider."""
        return self._registry.get_active_provider().embed_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """Embed query using active provider."""
        return self._registry.get_active_provider().embed_query(text)
    
    @property
    def dimension(self) -> int:
        """Get dimension from active provider."""
        return self._registry.get_active_provider().dimension


@lru_cache()
def get_dynamic_embeddings() -> DynamicEmbeddings:
    """Get cached DynamicEmbeddings instance for LangChain compatibility."""
    return DynamicEmbeddings()
