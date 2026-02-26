"""
Embedding Registry - Dynamic management of embedding providers and active processes.
"""
from typing import Dict, Any, Optional, List
import threading
from functools import lru_cache

from backend.core.logging import get_logger
from backend.services.embedding_providers import create_embedding_provider, EmbeddingProvider

logger = get_logger(__name__)

# =============================================================================
# Provider Registry (for hot-swappable embedding backends)
# =============================================================================

class EmbeddingRegistry:
    """
    Registry for managing available embedding providers and their lifecycle.
    
    This class handles:
    - Registering available provider types
    - Maintaining the active provider singleton
    - Switching providers at runtime (hot-swapping)
    - Persisting provider settings to the database
    """
    _instance = None
    _lock = threading.RLock()
    
    # Static catalog of available providers and their default configs
    PROVIDER_CATALOG = {
        "bge-m3": {
            "display_name": "BGE-M3 (Multilingual)",
            "description": "High-quality multilingual embeddings (local)",
            "requires_api_key": False,
            "default_config": {
                "model_name": "BAAI/bge-m3",
                "model_path": "./models/bge-m3",
                "batch_size": 128
            }
        },
        "openai": {
            "display_name": "OpenAI Embeddings",
            "description": "Cloud-based embeddings from OpenAI (requires API key)",
            "requires_api_key": True,
            "default_config": {
                "model_name": "text-embedding-3-small",
                "batch_size": 100
            }
        },
        "sentence-transformers": {
            "display_name": "SentenceTransformers",
            "description": "Generic HuggingFace models (local)",
            "requires_api_key": False,
            "default_config": {
                "model_name": "all-MiniLM-L6-v2",
                "batch_size": 128
            }
        }
    }
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EmbeddingRegistry, cls).__new__(cls)
                cls._instance._active_provider = None
                cls._instance._active_provider_type = None
                cls._instance._active_config = {}
                cls._instance._initialized = False
            return cls._instance
            
    def _initialize_from_settings(self):
        """Lazy initialization of the active provider from system settings."""
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
            self._load_initial_provider()
            self._initialized = True
            
    def _load_initial_provider(self):
        """Load the initial provider from configuration/settings."""
        try:
            from backend.config import get_settings
            settings = get_settings()
            
            provider_type = settings.embedding_provider
            logger.info(f"Loading initial provider from settings: {provider_type}")
            
            # Map settings to config
            config = {
                "model_name": settings.embedding_model_name,
                "batch_size": settings.embedding_batch_size
            }
            if hasattr(settings, "embedding_model_path"):
                 config["model_path"] = settings.embedding_model_path
            
            self._set_provider(provider_type, config)
        except Exception as e:
            logger.error(f"Failed to load initial embedding provider: {e}. Falling back to sentence-transformers.")
            # Final fallback
            try:
                self._set_provider("sentence-transformers", self.PROVIDER_CATALOG["sentence-transformers"]["default_config"])
            except:
                pass

    def _set_provider(self, provider_type: str, config: Dict[str, Any]):
        """Internal method to instantiate and set the active provider."""
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
        """Get the currently active embedding provider."""
        self._initialize_from_settings()
        if self._active_provider is None:
            raise RuntimeError("No active embedding provider configured")
        return self._active_provider
    
    def set_active_provider(
        self,
        provider_type: str,
        config: Optional[Dict[str, Any]] = None,
        persist: bool = True,
        updated_by: str = "system"
    ) -> Dict[str, Any]:
        """Switch to a different embedding provider (hot-swap)."""
        if provider_type not in self.PROVIDER_CATALOG:
            raise ValueError(f"Unknown provider: {provider_type}")
        
        # Merge with default config
        default_cfg = self.PROVIDER_CATALOG[provider_type]["default_config"].copy()
        if config:
            default_cfg.update(config)
        
        logger.info(f"Switching embedding provider to: {provider_type}")
        self._set_provider(provider_type, default_cfg)
        
        # Persist to settings if requested
        if persist:
            try:
                from backend.services.settings_service import get_settings_service
                settings_svc = get_settings_service()
                settings_svc.update_setting("embedding", "provider", provider_type, updated_by)
                settings_svc.update_setting("embedding", "model_name", default_cfg.get("model_name", ""), updated_by)
                if "model_path" in default_cfg:
                    settings_svc.update_setting("embedding", "model_path", default_cfg.get("model_path", ""), updated_by)
                if "batch_size" in default_cfg:
                    settings_svc.update_setting("embedding", "batch_size", default_cfg.get("batch_size", 128), updated_by)
            except Exception as e:
                logger.error(f"Failed to persist provider settings: {e}")
        
        return {
            "success": True,
            "provider": provider_type,
            "config": self._active_provider.get_config(),
            "requires_reindex": True
        }
    
    def get_active_provider_type(self) -> str:
        """Get the type name of the active provider."""
        self._initialize_from_settings()
        return self._active_provider_type
    
    def get_active_config(self) -> Dict[str, Any]:
        """Get the configuration of the active provider."""
        self._initialize_from_settings()
        if self._active_provider:
            return self._active_provider.get_config()
        return {}
    
    def _list_local_models(self) -> List[str]:
        """List models available in the localized models directory."""
        try:
            from pathlib import Path
            backend_root = Path(__file__).parent.parent
            models_dir = backend_root / "models"
            if not models_dir.exists():
                return []
            models = []
            for item in models_dir.iterdir():
                if item.is_dir() and not item.name.startswith("__"):
                    if (item / "config.json").exists():
                        models.append(item.name)
            return sorted(models)
        except Exception as e:
            logger.warning(f"Failed to list local models: {e}")
            return []

    def list_providers(self) -> List[Dict[str, Any]]:
        """List all available provider types with their metadata."""
        self._initialize_from_settings()
        result = []
        local_models = self._list_local_models()
        for name, info in self.PROVIDER_CATALOG.items():
            provider_info = {
                "name": name,
                "display_name": info["display_name"],
                "description": info["description"],
                "requires_api_key": info["requires_api_key"],
                "is_active": name == self._active_provider_type,
                "default_config": info["default_config"]
            }
            if name == "sentence-transformers":
                provider_info["models"] = local_models
            elif name == "openai":
                provider_info["models"] = ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
            elif name == "bge-m3":
                provider_info["models"] = ["BAAI/bge-m3"]
            else:
                provider_info["models"] = []
            result.append(provider_info)
        return result
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on the active provider."""
        self._initialize_from_settings()
        if not self._active_provider:
            return {"healthy": False, "error": "No active provider"}
        return self._active_provider.health_check()
    
    def test_provider(self, provider_type: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Test a provider configuration without activating it."""
        if provider_type not in self.PROVIDER_CATALOG:
            return {"success": False, "error": f"Unknown provider: {provider_type}"}
        try:
            default_cfg = self.PROVIDER_CATALOG[provider_type]["default_config"].copy()
            if config:
                default_cfg.update(config)
            test_provider = create_embedding_provider(provider_type, default_cfg)
            health = test_provider.health_check()
            return {
                "success": health.get("healthy", False),
                "provider": provider_type,
                "health": health,
                "config": test_provider.get_config()
            }
        except Exception as e:
            logger.error(f"Provider test failed: {e}")
            return {"success": False, "provider": provider_type, "error": str(e)}

def get_embedding_registry() -> EmbeddingRegistry:
    """Get the singleton EmbeddingRegistry instance."""
    return EmbeddingRegistry()


# =============================================================================
# Processor Registry (for tracking active jobs for cancellation)
# =============================================================================

class EmbeddingProcessorRegistry:
    """
    Thread-safe registry for tracking active EmbeddingBatchProcessor instances.
    This allows the API layer to find an active processor by job_id and cancel it.
    """
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(EmbeddingProcessorRegistry, cls).__new__(cls)
                cls._instance._processors = {}
            return cls._instance
            
    def register(self, job_id: str, processor: Any):
        """Register an active processor."""
        with self._lock:
            self._processors[job_id] = processor
            
    def unregister(self, job_id: str):
        """Unregister a processor."""
        with self._lock:
            if job_id in self._processors:
                del self._processors[job_id]
                
    def get_processor(self, job_id: str) -> Optional[Any]:
        """Get an active processor by job_id."""
        with self._lock:
            return self._processors.get(job_id)

def get_embedding_processor_registry() -> EmbeddingProcessorRegistry:
    """Get the singleton embedding processor registry instance."""
    return EmbeddingProcessorRegistry()


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
