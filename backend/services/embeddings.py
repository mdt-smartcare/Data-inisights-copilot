"""
Embedding service - Unified embedding interface with provider registry.

This module provides backward-compatible functions while delegating to the
dynamic EmbeddingRegistry system for hot-swappable provider management.

Legacy classes are kept for backward compatibility with existing code.
New code should use `get_embedding_model()` or the EmbeddingRegistry directly.
"""
from typing import List
from pathlib import Path
from functools import lru_cache
from langchain_core.embeddings import Embeddings

# Langfuse imports - v3.x uses direct imports from langfuse
from langfuse import observe
try:
    from langfuse import langfuse_context
except ImportError:
    langfuse_context = None

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


# =============================================================================
# Legacy Classes (kept for backward compatibility)
# =============================================================================

class _EmbeddingService:
    """
    Legacy singleton service to manage the embedding model.
    
    DEPRECATED: Use EmbeddingRegistry.get_active_provider() instead.
    Kept for backward compatibility with existing code.
    """
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(_EmbeddingService, cls).__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        """Load the SentenceTransformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            
            model_path = settings.embedding_model_path
            logger.info(f"Loading embedding model from {model_path}")
            
            resolved_path = Path(model_path)
            if not resolved_path.is_absolute() and model_path.startswith('./'):
                backend_root = Path(__file__).parent.parent
                resolved_path = (backend_root / model_path.lstrip('./')).resolve()
                logger.info(f"Resolved model path to: {resolved_path}")
                model_path = str(resolved_path)
            
            self._model = SentenceTransformer(model_path)
            logger.info(f"Embedding model loaded successfully. Dimension: {self._model.get_sentence_embedding_dimension()}")

    def get_model(self):
        """Get the loaded embedding model."""
        if self._model is None:
            logger.error("Embedding model was requested before it was loaded.")
            raise RuntimeError("Embedding model not loaded.")
        return self._model


class LocalHuggingFaceEmbeddings(Embeddings):
    """
    LangChain-compatible embedding wrapper using the active provider from registry.
    
    This class now delegates to the EmbeddingRegistry system for dynamic
    provider switching while maintaining the same interface for backward compatibility.
    """
    
    def __init__(self):
        """
        Initialize the embedding model wrapper.
        Now uses EmbeddingRegistry for provider management.
        """
        # Use the registry for dynamic provider access
        try:
            from backend.services.embedding_registry import get_embedding_registry
            self._registry = get_embedding_registry()
            self._use_registry = True
            logger.debug("LocalHuggingFaceEmbeddings using EmbeddingRegistry")
        except Exception as e:
            # Fallback to legacy behavior if registry fails
            logger.warning(f"Falling back to legacy embedding: {e}")
            self.model = _EmbeddingService().get_model()
            self._use_registry = False
    
    def _get_provider(self):
        """Get the active provider from registry or legacy model."""
        if self._use_registry:
            return self._registry.get_active_provider()
        return None
    
    @observe(as_type="generation")
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents.
        
        Args:
            texts: List of text documents to embed
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        logger.debug(f"Embedding {len(texts)} documents")
        
        # Add metadata to trace
        try:
            if langfuse_context:
                langfuse_context.update_current_observation(
                    model=self._get_provider().model_name if self._use_registry else "sentence-transformers",
                    metadata={"batch_size": len(texts)}
                )
        except:
            pass
        
        if self._use_registry:
            return self._get_provider().embed_documents(texts)
        else:
            embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
            return embeddings.tolist()
    
    @observe(as_type="generation")
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query text.
        
        Args:
            text: Query text to embed
        
        Returns:
            Embedding vector
        """
        logger.debug(f"Embedding query: {text[:100]}...")
        
        if self._use_registry:
            return self._get_provider().embed_query(text)
        else:
            embedding = self.model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._use_registry:
            return self._get_provider().dimension
        return self.model.get_sentence_embedding_dimension()


# =============================================================================
# Public API Functions
# =============================================================================

@lru_cache()
def get_embedding_model() -> LocalHuggingFaceEmbeddings:
    """
    Get cached embedding model instance.
    
    This function returns a LangChain-compatible embeddings object that
    uses the dynamic EmbeddingRegistry behind the scenes.
    
    Returns:
        Cached embedding model with registry support
    """
    return LocalHuggingFaceEmbeddings()


def preload_embedding_model():
    """
    Preloads the embedding model by initializing the provider registry.
    
    This ensures the embedding model is ready for use at application startup.
    Uses the EmbeddingRegistry to load the configured provider.
    """
    logger.info("Preloading embedding model...")
    
    try:
        # Use registry to preload the active provider
        from backend.services.embedding_registry import get_embedding_registry
        registry = get_embedding_registry()
        provider = registry.get_active_provider()
        logger.info(f"Embedding model preloaded via registry. Provider: {provider.provider_name}, Dimension: {provider.dimension}")
    except Exception as e:
        # Fallback to legacy preload
        logger.warning(f"Registry preload failed, using legacy: {e}")
        _EmbeddingService()
        logger.info("Embedding model preloaded via legacy service.")


# =============================================================================
# Registry Re-exports (for convenience)
# =============================================================================

def get_active_embedding_provider():
    """
    Get the active embedding provider from the registry.
    
    Convenience function for accessing the provider directly.
    """
    from backend.services.embedding_registry import get_embedding_registry
    return get_embedding_registry().get_active_provider()


def switch_embedding_provider(provider_type: str, config: dict = None, persist: bool = True):
    """
    Switch to a different embedding provider.
    
    Args:
        provider_type: One of 'bge-m3', 'openai', 'sentence-transformers'
        config: Provider-specific configuration
        persist: Whether to save to settings DB
        
    Returns:
        Switch result dict with success status
    """
    from backend.services.embedding_registry import get_embedding_registry
    return get_embedding_registry().set_active_provider(provider_type, config, persist)
