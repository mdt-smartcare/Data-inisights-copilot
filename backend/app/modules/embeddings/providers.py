"""
Embedding Providers - Abstraction layer for multiple embedding backends.

Provides a unified interface for different embedding services (BGE, OpenAI, SentenceTransformers).
Ported from old backend with performance optimizations.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import OrderedDict
import asyncio
import time
import os

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Query Embedding Cache
# =============================================================================
# embed_query() is deterministic: same text → same embedding.
# Queries repeat frequently (follow-ups, retries, similar phrasing).
# 512 entries ≈ 2MB for 1024-dim embeddings.
_QUERY_EMBEDDING_CACHE: OrderedDict[str, List[float]] = OrderedDict()
_QUERY_CACHE_MAX = 512


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
        """Embed a list of documents."""
        pass
    
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        pass
    
    def embed_query_cached(self, text: str) -> List[float]:
        """
        Embed a query with LRU caching.
        
        Caching avoids re-computing embeddings (~50-200ms per query).
        512 entries ≈ 2MB for 1024-dim vectors.
        """
        cache_key = text.strip()
        
        if cache_key in _QUERY_EMBEDDING_CACHE:
            _QUERY_EMBEDDING_CACHE.move_to_end(cache_key)
            logger.debug("Query embedding cache HIT")
            return _QUERY_EMBEDDING_CACHE[cache_key]
        
        # Cache miss — compute embedding
        embedding = self.embed_query(text)
        
        _QUERY_EMBEDDING_CACHE[cache_key] = embedding
        if len(_QUERY_EMBEDDING_CACHE) > _QUERY_CACHE_MAX:
            _QUERY_EMBEDDING_CACHE.popitem(last=False)  # Remove oldest
        
        return embedding
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Get the embedding dimension."""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider identifier."""
        pass
    
    @property
    def supports_async(self) -> bool:
        """Check if provider supports native async operations."""
        return False
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Async embed documents (default wraps sync in executor)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)
    
    async def aembed_query(self, text: str) -> List[float]:
        """Async embed query (default wraps sync in executor)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)
    
    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the provider."""
        try:
            start = time.time()
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
        """Get the current provider configuration."""
        return {
            "provider": self.provider_name,
            "dimension": self.dimension,
            "supports_async": self.supports_async
        }


# =============================================================================
# BGE Provider (Local SentenceTransformer with MPS/CUDA support)
# =============================================================================

class BGEProvider(EmbeddingProvider):
    """
    BGE-M3 embedding provider using SentenceTransformers.
    
    Provides high-quality multilingual embeddings locally without API calls.
    Default model: BAAI/bge-base-en-v1.5 (1024 dimensions)
    
    Includes:
    - Auto-detection of MPS (Apple Metal) / CUDA
    - MPS memory leak mitigation via periodic cache clearing
    - Multi-threaded tokenization
    """
    
    MPS_CACHE_CLEAR_INTERVAL = 50
    
    def __init__(
        self,
        model_path: str = "./models/bge-base-en-v1.5",
        model_name: str = "BAAI/bge-base-en-v1.5",
        batch_size: int = 128,
        normalize: bool = True,
        device: str = "auto",
        tokenizer_parallelism: bool = True,
        mps_cache_clear_interval: int = 50,
        **kwargs: Any
    ):
        self._model_path = model_path
        self._model_name = model_name
        self._batch_size = batch_size
        self._normalize = normalize
        self._device = device
        self._tokenizer_parallelism = tokenizer_parallelism
        self._mps_cache_clear_interval = mps_cache_clear_interval
        self._model = None
        self._dimension = None
        self._actual_device = None
        self._embed_call_count = 0
        self._total_cache_clears = 0
        
        self._configure_tokenizer_parallelism()
        self._load_model()
    
    def _configure_tokenizer_parallelism(self):
        """Configure environment for optimal tokenization performance."""
        if self._tokenizer_parallelism:
            os.environ["TOKENIZERS_PARALLELISM"] = "true"
            logger.info("Tokenizer parallelism enabled")
        else:
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    def _get_best_device(self) -> str:
        """Determine the best available device for inference."""
        import torch
        
        if self._device != "auto":
            return self._device
        
        if torch.cuda.is_available():
            logger.info("CUDA detected, using GPU")
            return "cuda"
        
        if torch.backends.mps.is_available():
            try:
                test_tensor = torch.zeros(1, device="mps")
                del test_tensor
                logger.info("MPS (Apple Metal) detected, using GPU acceleration")
                return "mps"
            except Exception as e:
                logger.warning(f"MPS available but not functional: {e}")
        
        logger.info("No GPU detected, using CPU")
        return "cpu"
    
    def _clear_gpu_cache(self, force: bool = False):
        """Clear GPU memory cache to prevent memory leaks (especially on MPS)."""
        import torch
        
        self._embed_call_count += 1
        should_clear = force or (self._embed_call_count % self._mps_cache_clear_interval == 0)
        
        if not should_clear:
            return
        
        try:
            if self._actual_device == "mps":
                if hasattr(torch.mps, 'empty_cache'):
                    torch.mps.empty_cache()
                    self._total_cache_clears += 1
                    if hasattr(torch.mps, 'synchronize'):
                        torch.mps.synchronize()
                    logger.debug(f"MPS cache cleared (call #{self._embed_call_count})")
            elif self._actual_device == "cuda":
                torch.cuda.empty_cache()
                self._total_cache_clears += 1
                logger.debug(f"CUDA cache cleared (call #{self._embed_call_count})")
        except Exception as e:
            logger.warning(f"Failed to clear GPU cache: {e}")
    
    def _load_model(self):
        """Load the SentenceTransformer model with optimal device."""
        if self._model is not None:
            return
        
        from sentence_transformers import SentenceTransformer
        
        self._actual_device = self._get_best_device()
        logger.info(f"Loading BGE model from {self._model_path} on device: {self._actual_device}")
        
        resolved_path = Path(self._model_path)
        if not resolved_path.is_absolute() and self._model_path.startswith('./'):
            from app.core.config import get_settings
            settings = get_settings()
            resolved_path = settings.data_dir / self._model_path.lstrip('./')
        
        try:
            if resolved_path.exists():
                self._model = SentenceTransformer(str(resolved_path), device=self._actual_device)
            else:
                logger.warning(f"Local path {resolved_path} not found, downloading {self._model_name}")
                self._model = SentenceTransformer(self._model_name, device=self._actual_device)
        except Exception as e:
            logger.error(f"Failed to load BGE model: {e}")
            raise
        
        self._dimension = self._model.get_sentence_embedding_dimension()
        logger.info(f"BGE model loaded on {self._actual_device}. Dimension: {self._dimension}")
        
        if self._actual_device == "mps":
            logger.info(f"MPS memory leak mitigation enabled: cache cleared every {self._mps_cache_clear_interval} batches")
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents with optimized GPU utilization."""
        if not texts:
            return []
        
        num_texts = len(texts)
        logger.debug(f"BGE embedding {num_texts} documents on device: {self._actual_device}")
        
        encode_kwargs = {
            "normalize_embeddings": self._normalize,
            "show_progress_bar": num_texts > 500,
            "batch_size": self._batch_size,
            "convert_to_numpy": True,
        }
        
        embeddings = self._model.encode(texts, **encode_kwargs)
        self._clear_gpu_cache()
        
        if hasattr(embeddings, 'tolist'):
            return embeddings.tolist()
        return [list(e) for e in embeddings]
    
    def embed_documents_as_numpy(self, texts: List[str]):
        """Embed documents and return as numpy array (no list conversion)."""
        if not texts:
            import numpy as np
            return np.array([])
        
        encode_kwargs = {
            "normalize_embeddings": self._normalize,
            "show_progress_bar": len(texts) > 500,
            "batch_size": self._batch_size,
            "convert_to_numpy": True,
        }
        
        embeddings = self._model.encode(texts, **encode_kwargs)
        self._clear_gpu_cache()
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        logger.debug(f"BGE embedding query on {self._actual_device}: {text[:100]}...")
        embedding = self._model.encode(text, normalize_embeddings=self._normalize)
        return embedding.tolist()
    
    def force_clear_cache(self):
        """Force clear GPU cache immediately."""
        self._clear_gpu_cache(force=True)
        logger.info(f"Forced GPU cache clear (total clears: {self._total_cache_clears})")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get GPU memory statistics (if available)."""
        import torch
        
        stats = {
            "device": self._actual_device,
            "embed_calls": self._embed_call_count,
            "cache_clears": self._total_cache_clears,
            "cache_clear_interval": self._mps_cache_clear_interval,
        }
        
        try:
            if self._actual_device == "mps":
                if hasattr(torch.mps, 'current_allocated_memory'):
                    stats["mps_allocated_mb"] = torch.mps.current_allocated_memory() / (1024 * 1024)
            elif self._actual_device == "cuda":
                stats["cuda_allocated_mb"] = torch.cuda.memory_allocated() / (1024 * 1024)
                stats["cuda_cached_mb"] = torch.cuda.memory_reserved() / (1024 * 1024)
        except Exception as e:
            stats["memory_error"] = str(e)
        
        return stats
    
    @property
    def dimension(self) -> int:
        return self._dimension or 1024
    
    @property
    def provider_name(self) -> str:
        return "bge-base-en-v1.5"
    
    @property
    def supports_async(self) -> bool:
        return False
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model_path": self._model_path,
            "model_name": self._model_name,
            "batch_size": self._batch_size,
            "dimension": self.dimension,
            "normalize": self._normalize,
            "device": self._actual_device or self._device,
            "tokenizer_parallelism": self._tokenizer_parallelism,
            "mps_cache_clear_interval": self._mps_cache_clear_interval,
            "total_cache_clears": self._total_cache_clears,
        }
    
    def __del__(self):
        try:
            self._clear_gpu_cache(force=True)
        except:
            pass


# =============================================================================
# OpenAI Embedding Provider
# =============================================================================

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI embedding provider using text-embedding-3-small/large or ada-002.
    Supports native async via AsyncOpenAI client.
    """
    
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
        self._model_name = model_name
        self._api_key = api_key
        self._batch_size = batch_size
        self._client = None
        self._async_client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize OpenAI sync and async clients."""
        try:
            from openai import OpenAI, AsyncOpenAI
            
            key = self._api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError("OpenAI API key not provided")
            
            self._client = OpenAI(api_key=key)
            self._async_client = AsyncOpenAI(api_key=key)
            logger.info(f"OpenAI embedding client initialized with model: {self._model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise
    
    @property
    def supports_async(self) -> bool:
        return True
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents (sync)."""
        if not texts:
            return []
        
        logger.debug(f"OpenAI embedding {len(texts)} documents (sync)")
        
        all_embeddings = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            response = self._client.embeddings.create(model=self._model_name, input=batch)
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query (sync)."""
        logger.debug(f"OpenAI embedding query (sync): {text[:100]}...")
        response = self._client.embeddings.create(model=self._model_name, input=text)
        return response.data[0].embedding
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Native async document embedding."""
        if not texts:
            return []
        
        logger.debug(f"OpenAI embedding {len(texts)} documents (async-native)")
        
        all_embeddings = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            response = await self._async_client.embeddings.create(model=self._model_name, input=batch)
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    async def aembed_query(self, text: str) -> List[float]:
        """Native async query embedding."""
        logger.debug(f"OpenAI embedding query (async-native): {text[:100]}...")
        response = await self._async_client.embeddings.create(model=self._model_name, input=text)
        return response.data[0].embedding
    
    @property
    def dimension(self) -> int:
        return self.MODEL_DIMENSIONS.get(self._model_name, 1536)
    
    @property
    def provider_name(self) -> str:
        return "openai"
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model_name": self._model_name,
            "batch_size": self._batch_size,
            "dimension": self.dimension,
            "api_key_configured": bool(self._api_key or os.environ.get("OPENAI_API_KEY")),
            "supports_async": self.supports_async
        }


# =============================================================================
# SentenceTransformer Provider (Generic HuggingFace models)
# =============================================================================

class SentenceTransformerProvider(EmbeddingProvider):
    """
    Generic SentenceTransformer provider for any HuggingFace model.
    
    Supports models like:
    - BAAI/bge-base-en-v1.5 (1024 dims, multilingual)
    - all-mpnet-base-v2 (768 dims, balanced)
    - instructor-xl (768 dims, instruction-tuned)
    """
    
    def __init__(
        self,
        model_name: str = "BAAI/bge-base-en-v1.5",
        batch_size: int = 128,
        normalize: bool = True,
        models_dir: Optional[str] = None,
        **kwargs: Any
    ):
        self._model_name = model_name
        self._batch_size = batch_size
        self._normalize = normalize
        self._models_dir = models_dir
        self._model = None
        self._dimension = None
        self._local_path = None
        self._load_model()
    
    def _load_model(self):
        """Load the SentenceTransformer model from local path or download."""
        if self._model is not None:
            return
        
        from sentence_transformers import SentenceTransformer
        
        logger.info(f"Loading SentenceTransformer model: {self._model_name}")
        
        models_dir = self._models_dir
        if models_dir is None:
            from app.core.config import get_settings
            settings = get_settings()
            models_dir = str(settings.data_dir / "models")
        elif models_dir.startswith('./'):
            from app.core.config import get_settings
            settings = get_settings()
            models_dir = str(settings.data_dir / models_dir.lstrip('./'))
        
        model_folder_name = self._model_name.split('/')[-1]
        local_model_path = Path(models_dir) / model_folder_name
        self._local_path = str(local_model_path)
        
        try:
            if local_model_path.exists() and (local_model_path / "config.json").exists():
                logger.info(f"Loading model from local path: {local_model_path}")
                self._model = SentenceTransformer(str(local_model_path))
            else:
                logger.info(f"Downloading model {self._model_name} to {local_model_path}")
                self._model = SentenceTransformer(self._model_name)
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
            batch_size=self._batch_size
        )
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        logger.debug(f"SentenceTransformer embedding query: {text[:100]}...")
        embedding = self._model.encode(text, normalize_embeddings=self._normalize)
        return embedding.tolist()
    
    @property
    def dimension(self) -> int:
        return self._dimension or 384
    
    @property
    def provider_name(self) -> str:
        return "sentence-transformers"
    
    @property
    def supports_async(self) -> bool:
        return False
    
    def get_config(self) -> Dict[str, Any]:
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
        provider_type: One of 'bge-base-en-v1.5', 'openai', 'sentence-transformers'
        config: Provider-specific configuration
        
    Returns:
        Configured EmbeddingProvider instance
    """
    config = config or {}
    
    providers = {
        "bge-base-en-v1.5": BGEProvider,
        "bge": BGEProvider,
        "openai": OpenAIEmbeddingProvider,
        "sentence-transformers": SentenceTransformerProvider,
        "huggingface": SentenceTransformerProvider,
    }
    
    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    
    logger.info(f"Creating embedding provider: {provider_type} with config: {config}")
    return providers[provider_type](**config)
