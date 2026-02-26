"""
Embedding Providers - Abstraction layer for multiple embedding backends.
Provides a unified interface for different embedding services (BGE, OpenAI, SentenceTransformers).
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
import asyncio
import time

from backend.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Abstract Base Class
# =============================================================================

class EmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    
    All embedding providers must implement:
    - embed_documents: Embed multiple texts (sync)
    - embed_query: Embed a single query (sync)
    - dimension: Return embedding dimension
    - provider_name: Return provider identifier
    
    Optional async methods:
    - aembed_documents: Async embed multiple texts
    - aembed_query: Async embed a single query
    - supports_async: Whether provider has native async support
    """
    
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents.
        
        Args:
            texts: List of text documents to embed
            
        Returns:
            List of embedding vectors
        """
        pass
    
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query text.
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Get the embedding dimension."""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider identifier (e.g., 'bge-m3', 'openai', 'sentence-transformers')."""
        pass
    
    @property
    def supports_async(self) -> bool:
        """
        Check if provider supports native async operations.
        
        Override in subclasses that have native async support.
        Default is False (will use run_in_executor fallback).
        """
        return False
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Async embed a list of documents.
        
        Default implementation wraps sync method in executor.
        Override in subclasses with native async support (e.g., OpenAI).
        
        Args:
            texts: List of text documents to embed
            
        Returns:
            List of embedding vectors
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        Async embed a single query text.
        
        Default implementation wraps sync method in executor.
        Override in subclasses with native async support.
        
        Args:
            text: Query text to embed
            
        Returns:
            Embedding vector
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the provider.
        
        Returns:
            Dict with 'healthy' bool and optional 'error' message
        """
        try:
            start = time.time()
            # Attempt a simple embedding
            test_embedding = self.embed_query("health check test")
            latency_ms = (time.time() - start) * 1000
            
            return {
                "healthy": True,
                "provider": self.provider_name,
                "dimension": self.dimension,
                "latency_ms": round(latency_ms, 2),
                "test_embedding_length": len(test_embedding),
                "supports_async": self.supports_async
            }
        except Exception as e:
            logger.error(f"Health check failed for {self.provider_name}: {e}")
            return {
                "healthy": False,
                "provider": self.provider_name,
                "error": str(e)
            }
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the current provider configuration.
        Override in subclasses for provider-specific config.
        """
        return {
            "provider": self.provider_name,
            "dimension": self.dimension,
            "supports_async": self.supports_async
        }


# =============================================================================
# BGE Provider (Local SentenceTransformer)
# =============================================================================

class BGEProvider(EmbeddingProvider):
    """
    BGE-M3 embedding provider using SentenceTransformers.
    
    Provides high-quality multilingual embeddings locally without API calls.
    Default model: BAAI/bge-m3 (1024 dimensions)
    
    Note: Does not support native async (uses executor fallback).
    """
    
    def __init__(
        self,
        model_path: str = "./models/bge-m3",
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 128,
        normalize: bool = True,
        **kwargs: Any
    ):
        """
        Initialize BGE provider.
        
        Args:
            model_path: Local path to model files (preferred)
            model_name: HuggingFace model name for download fallback
            batch_size: Batch size for document embedding
            normalize: Whether to L2-normalize embeddings
            **kwargs: Additional configuration (ignored)
        """
        self._model_path = model_path
        self._model_name = model_name
        self._batch_size = batch_size
        self._normalize = normalize
        self._model = None
        self._dimension = None
        
        # Lazy load model
        self._load_model()
    
    def _load_model(self):
        """Load the SentenceTransformer model."""
        if self._model is not None:
            return
            
        from sentence_transformers import SentenceTransformer
        
        logger.info(f"Loading BGE model from {self._model_path}")
        
        # Resolve relative path
        resolved_path = Path(self._model_path)
        if not resolved_path.is_absolute() and self._model_path.startswith('./'):
            backend_root = Path(__file__).parent.parent
            resolved_path = (backend_root / self._model_path.lstrip('./')).resolve()
            logger.info(f"Resolved model path to: {resolved_path}")
        
        # Try local path first, fallback to model name for download
        try:
            if resolved_path.exists():
                self._model = SentenceTransformer(str(resolved_path))
            else:
                logger.warning(f"Local path {resolved_path} not found, downloading {self._model_name}")
                self._model = SentenceTransformer(self._model_name)
        except Exception as e:
            logger.error(f"Failed to load BGE model: {e}")
            raise
            
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(f"BGE model loaded. Dimension: {self._dimension}")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents."""
        if not texts:
            return []
            
        logger.debug(f"BGE embedding {len(texts)} documents")
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=self._normalize,
            show_progress_bar=len(texts) > 500,
            batch_size=self._batch_size
        )
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        logger.debug(f"BGE embedding query: {text[:100]}...")
        embedding = self._model.encode(text, normalize_embeddings=self._normalize)
        return embedding.tolist()
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension or 1024  # BGE-M3 default
    
    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "bge-m3"
    
    @property
    def supports_async(self) -> bool:
        """BGE/SentenceTransformers doesn't have native async support."""
        return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "provider": self.provider_name,
            "model_path": self._model_path,
            "model_name": self._model_name,
            "batch_size": self._batch_size,
            "dimension": self.dimension,
            "normalize": self._normalize
        }


# =============================================================================
# OpenAI Embedding Provider
# =============================================================================

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI embedding provider using text-embedding-3-small/large or ada-002.
    
    Requires OPENAI_API_KEY environment variable or explicit api_key.
    
    Supports native async via AsyncOpenAI client.
    """
    
    # Model dimensions
    MODEL_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536
    }
    
    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        batch_size: int = 100,
        **kwargs: Any
    ):
        """
        Initialize OpenAI provider.
        
        Args:
            model_name: OpenAI embedding model name
            api_key: Optional API key (falls back to env var)
            batch_size: Batch size for document embedding
            **kwargs: Additional configuration (ignored)
        """
        self._model_name = model_name
        self._api_key = api_key
        self._batch_size = batch_size
        self._client = None
        self._async_client = None
        
        # Initialize clients
        self._init_client()
    
    def _init_client(self):
        """Initialize OpenAI sync and async clients."""
        try:
            from openai import OpenAI, AsyncOpenAI
            import os
            
            key = self._api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("OpenAI API key not provided")
            
            # Sync client
            self._client = OpenAI(api_key=key)
            
            # Async client for native async support
            self._async_client = AsyncOpenAI(api_key=key)
            
            logger.info(f"OpenAI embedding client initialized with model: {self._model_name} (async enabled)")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise
    
    @property
    def supports_async(self) -> bool:
        """OpenAI supports native async."""
        return True
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents (sync)."""
        if not texts:
            return []
            
        logger.debug(f"OpenAI embedding {len(texts)} documents (sync)")
        
        all_embeddings = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            response = self._client.embeddings.create(
                model=self._model_name,
                input=batch
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query (sync)."""
        logger.debug(f"OpenAI embedding query (sync): {text[:100]}...")
        response = self._client.embeddings.create(
            model=self._model_name,
            input=text
        )
        return response.data[0].embedding
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Native async document embedding.
        
        Uses AsyncOpenAI client for true async I/O without blocking.
        """
        if not texts:
            return []
            
        logger.debug(f"OpenAI embedding {len(texts)} documents (async-native)")
        
        all_embeddings = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            response = await self._async_client.embeddings.create(
                model=self._model_name,
                input=batch
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            
        return all_embeddings
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        Native async query embedding.
        """
        logger.debug(f"OpenAI embedding query (async-native): {text[:100]}...")
        response = await self._async_client.embeddings.create(
            model=self._model_name,
            input=text
        )
        return response.data[0].embedding
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self.MODEL_DIMENSIONS.get(self._model_name, 1536)
    
    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "openai"
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration (without API key)."""
        return {
            "provider": self.provider_name,
            "model_name": self._model_name,
            "batch_size": self._batch_size,
            "dimension": self.dimension,
            "api_key_configured": bool(self._api_key or True),
            "supports_async": self.supports_async
        }


# =============================================================================
# SentenceTransformer Provider (Generic HuggingFace models)
# =============================================================================

class SentenceTransformerProvider(EmbeddingProvider):
    """
    Generic SentenceTransformer provider for any HuggingFace model.
    
    Supports models like:
    - all-MiniLM-L6-v2 (384 dims, fast)
    - all-mpnet-base-v2 (768 dims, balanced)
    - instructor-xl (768 dims, instruction-tuned)
    
    Note: Does not support native async (uses executor fallback).
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        batch_size: int = 128,
        normalize: bool = True,
        models_dir: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize SentenceTransformer provider.
        
        Args:
            model_name: HuggingFace model name
            batch_size: Batch size for document embedding
            normalize: Whether to L2-normalize embeddings
            models_dir: Directory to store models (default: ./models)
            **kwargs: Additional configuration (ignored)
        """
        self._model_name = model_name
        self._batch_size = batch_size
        self._normalize = normalize
        self._models_dir = models_dir
        self._model = None
        self._dimension = None
        self._local_path = None
        
        self._load_model()
    
    def _load_model(self):
        """Load the SentenceTransformer model from local path or download and save."""
        if self._model is not None:
            return
            
        from sentence_transformers import SentenceTransformer
        
        logger.info(f"Loading SentenceTransformer model: {self._model_name}")
        
        # Determine models directory
        models_dir = self._models_dir
        if models_dir is None:
            # Default to backend/models/
            backend_root = Path(__file__).parent.parent
            models_dir = str(backend_root / "models")
        elif models_dir.startswith('./'):
            # Resolve relative path
            backend_root = Path(__file__).parent.parent
            models_dir = str((backend_root / models_dir.lstrip('./')).resolve())
        
        # Create a clean folder name from the model name
        # "sentence-transformers/all-MiniLM-L6-v2" -> "all-MiniLM-L6-v2"
        # "intfloat/e5-large-v2" -> "e5-large-v2"
        model_folder_name = self._model_name.split('/')[-1]
        local_model_path = Path(models_dir) / model_folder_name
        self._local_path = str(local_model_path)
        
        try:
            # Check if model already exists locally
            if local_model_path.exists() and (local_model_path / "config.json").exists():
                logger.info(f"Loading model from local path: {local_model_path}")
                self._model = SentenceTransformer(str(local_model_path))
            else:
                # Download from HuggingFace and save locally
                logger.info(f"Downloading model {self._model_name} to {local_model_path}")
                self._model = SentenceTransformer(self._model_name)
                
                # Save to local path in flat structure
                local_model_path.mkdir(parents=True, exist_ok=True)
                self._model.save(str(local_model_path))
                logger.info(f"Model saved to: {local_model_path}")
            
            self._dimension = self._model.get_sentence_embedding_dimension()
            logger.info(f"Model loaded. Dimension: {self._dimension}")
        except Exception as e:
            logger.error(f"Failed to load model {self._model_name}: {e}")
            raise
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents."""
        if not texts:
            return []
            
        logger.debug(f"SentenceTransformer embedding {len(texts)} documents")
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
            batch_size=self._batch_size # Fixed: was hardcoded to 32
        )
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        logger.debug(f"SentenceTransformer embedding query: {text[:100]}...")
        embedding = self._model.encode(text, normalize_embeddings=self._normalize)
        return embedding.tolist()
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension or 384  # MiniLM default
    
    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "sentence-transformers"
    
    @property
    def supports_async(self) -> bool:
        """SentenceTransformers doesn't have native async support."""
        return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "provider": self.provider_name,
            "model_name": self._model_name,
            "batch_size": self._batch_size,
            "dimension": self.dimension,
            "normalize": self._normalize,
            "local_path": self._local_path
        }


# =============================================================================
# Factory Function
# =============================================================================

def create_embedding_provider(
    provider_type: str,
    config: Optional[Dict[str, Any]] = None
) -> EmbeddingProvider:
    """
    Factory function to create embedding providers.
    
    Args:
        provider_type: One of 'bge-m3', 'openai', 'sentence-transformers'
        config: Provider-specific configuration
        
    Returns:
        Configured EmbeddingProvider instance
    """
    config = config or {}
    
    providers = {
        "bge-m3": BGEProvider,
        "openai": OpenAIEmbeddingProvider,
        "sentence-transformers": SentenceTransformerProvider
    }
    
    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    
    logger.info(f"Creating embedding provider: {provider_type} with config: {config}")
    return providers[provider_type](**config)
