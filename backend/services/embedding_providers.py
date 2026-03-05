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
    
    Automatically uses MPS (Apple Metal) on Mac for GPU acceleration.
    Uses multi-threaded tokenization to prevent CPU bottleneck on GPU.
    Includes MPS memory leak mitigation via periodic cache clearing.
    
    Note: Does not support native async (uses executor fallback).
    """
    
    # MPS memory management constants
    MPS_CACHE_CLEAR_INTERVAL = 50  # Clear MPS cache every N batches
    
    def __init__(
        self,
        model_path: str = "./models/bge-m3",
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 128,
        normalize: bool = True,
        device: str = "auto",  # "auto", "cpu", "cuda", "mps"
        tokenizer_parallelism: bool = True,  # Enable parallel tokenization
        mps_cache_clear_interval: int = 50,  # Clear MPS cache every N embed_documents calls
        **kwargs: Any
    ):
        """
        Initialize BGE provider.
        
        Args:
            model_path: Local path to model files (preferred)
            model_name: HuggingFace model name for download fallback
            batch_size: Batch size for document embedding
            normalize: Whether to L2-normalize embeddings
            device: Device to use ("auto", "cpu", "cuda", "mps")
            tokenizer_parallelism: Enable multi-threaded tokenization (recommended for GPU)
            mps_cache_clear_interval: Clear MPS memory cache every N batches (prevents memory leak)
            **kwargs: Additional configuration (ignored)
        """
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
        self._pool = None  # Thread pool for tokenization
        self._embed_call_count = 0  # Track calls for MPS cache management
        self._total_cache_clears = 0  # Track how many times we've cleared cache
        
        # Configure tokenizer parallelism environment
        self._configure_tokenizer_parallelism()
        
        # Lazy load model
        self._load_model()
    
    def _configure_tokenizer_parallelism(self):
        """Configure environment for optimal tokenization performance."""
        import os
        
        if self._tokenizer_parallelism:
            # Enable HuggingFace tokenizer parallelism
            os.environ["TOKENIZERS_PARALLELISM"] = "true"
            logger.info("Tokenizer parallelism enabled for faster preprocessing")
        else:
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    def _get_best_device(self) -> str:
        """Determine the best available device for inference."""
        import torch
        
        if self._device != "auto":
            return self._device
        
        # Check for CUDA (NVIDIA GPU)
        if torch.cuda.is_available():
            logger.info("CUDA detected, using GPU")
            return "cuda"
        
        # Check for MPS (Apple Metal on M1/M2/M3 Macs)
        if torch.backends.mps.is_available():
            # Verify MPS is actually functional
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
        """
        Clear GPU memory cache to prevent memory leaks.
        
        MPS MEMORY LEAK FIX:
        There's a known issue in PyTorch's MPS backend where memory usage
        grows steadily over time, eventually causing system swap and severe
        slowdowns (ETA going from 5h to 24h+). This is documented at:
        - https://github.com/pytorch/pytorch/issues/88637
        - https://discuss.huggingface.co/t/mps-memory-leak/
        
        The fix is to periodically call torch.mps.empty_cache() to release
        unused memory back to the system.
        
        Args:
            force: If True, clear cache regardless of interval
        """
        import torch
        
        self._embed_call_count += 1
        
        # Only clear cache at intervals (or if forced) to avoid overhead
        should_clear = force or (self._embed_call_count % self._mps_cache_clear_interval == 0)
        
        if not should_clear:
            return
        
        try:
            if self._actual_device == "mps":
                # MPS-specific cache clearing
                if hasattr(torch.mps, 'empty_cache'):
                    torch.mps.empty_cache()
                    self._total_cache_clears += 1
                    
                    # Synchronize to ensure operations complete
                    if hasattr(torch.mps, 'synchronize'):
                        torch.mps.synchronize()
                    
                    logger.debug(
                        f"MPS cache cleared (call #{self._embed_call_count}, "
                        f"total clears: {self._total_cache_clears})"
                    )
                    
            elif self._actual_device == "cuda":
                # CUDA cache clearing
                torch.cuda.empty_cache()
                self._total_cache_clears += 1
                logger.debug(f"CUDA cache cleared (call #{self._embed_call_count})")
                
        except Exception as e:
            # Don't fail on cache clear errors, just log
            logger.warning(f"Failed to clear GPU cache: {e}")
    
    def _load_model(self):
        """Load the SentenceTransformer model with optimal device."""
        if self._model is not None:
            return
            
        from sentence_transformers import SentenceTransformer
        
        # Determine best device
        self._actual_device = self._get_best_device()
        
        logger.info(f"Loading BGE model from {self._model_path} on device: {self._actual_device}")
        
        # Resolve relative path
        resolved_path = Path(self._model_path)
        if not resolved_path.is_absolute() and self._model_path.startswith('./'):
            backend_root = Path(__file__).parent.parent
            resolved_path = (backend_root / self._model_path.lstrip('./')).resolve()
            logger.info(f"Resolved model path to: {resolved_path}")
        
        # Try local path first, fallback to model name for download
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
        
        # Log MPS memory management info
        if self._actual_device == "mps":
            logger.info(
                f"MPS memory leak mitigation enabled: cache will be cleared every "
                f"{self._mps_cache_clear_interval} batches to prevent memory pressure"
            )
        
        # Start tokenization thread pool for GPU devices (reduces CPU bottleneck)
        if self._actual_device in ("cuda", "mps") and self._tokenizer_parallelism:
            self._init_tokenization_pool()
    
    def _init_tokenization_pool(self):
        """Initialize thread pool for parallel tokenization (CPU) while GPU does inference."""
        try:
            from multiprocessing.pool import ThreadPool
            import os
            
            # Use half of available CPUs for tokenization (leave rest for system)
            num_threads = max(2, (os.cpu_count() or 4) // 2)
            self._pool = ThreadPool(processes=num_threads)
            logger.info(f"Tokenization thread pool initialized with {num_threads} workers")
        except Exception as e:
            logger.warning(f"Failed to initialize tokenization pool: {e}")
            self._pool = None
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple documents with optimized GPU utilization.
        
        MPS/CUDA PERFORMANCE FIX:
        - Avoids per-batch GPU→CPU sync that kills MPS performance
        - Uses convert_to_numpy=True to let SentenceTransformers handle transfer efficiently
        - Defers .tolist() conversion to happen on numpy array (much faster)
        
        Includes MPS memory leak mitigation via periodic cache clearing.
        """
        if not texts:
            return []
        
        num_texts = len(texts)
        logger.debug(f"BGE embedding {num_texts} documents on device: {self._actual_device}")
        
        encode_kwargs = {
            "normalize_embeddings": self._normalize,
            "show_progress_bar": num_texts > 500,
            "batch_size": self._batch_size,
        }
        
        if self._actual_device in ("cuda", "mps"):
            # GPU PERFORMANCE OPTIMIZATION:
            # Use convert_to_numpy=True instead of convert_to_tensor=True
            # This lets SentenceTransformers handle the GPU→CPU transfer efficiently
            # in one operation at the end, rather than forcing sync per-batch
            encode_kwargs["convert_to_numpy"] = True
            # Don't set convert_to_tensor - it causes the mps:0 vs cpu trap
            # where .cpu().numpy() forces a sync on every call
        
        # Get embeddings - will be numpy array on GPU path, or numpy array on CPU path
        embeddings = self._model.encode(texts, **encode_kwargs)
        
        # MPS MEMORY LEAK FIX: Clear cache periodically to prevent memory growth
        self._clear_gpu_cache()
        
        # Convert numpy array to list - this is fast since data is already on CPU
        # Using .tolist() on numpy is much faster than on torch tensors
        if hasattr(embeddings, 'tolist'):
            return embeddings.tolist()
        
        # Fallback for unexpected types
        return [list(e) for e in embeddings]
    
    def embed_documents_as_numpy(self, texts: List[str]):
        """
        Embed documents and return as numpy array (no list conversion).
        
        Use this for maximum performance when the caller can handle numpy arrays.
        Avoids the .tolist() overhead entirely.
        
        Args:
            texts: List of text documents to embed
            
        Returns:
            numpy.ndarray of shape (len(texts), embedding_dim)
        """
        if not texts:
            import numpy as np
            return np.array([])
        
        num_texts = len(texts)
        logger.debug(f"BGE embedding {num_texts} documents as numpy on device: {self._actual_device}")
        
        encode_kwargs = {
            "normalize_embeddings": self._normalize,
            "show_progress_bar": num_texts > 500,
            "batch_size": self._batch_size,
            "convert_to_numpy": True,  # Always return numpy for this method
        }
        
        embeddings = self._model.encode(texts, **encode_kwargs)
        
        # MPS MEMORY LEAK FIX
        self._clear_gpu_cache()
        
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        logger.debug(f"BGE embedding query on {self._actual_device}: {text[:100]}...")
        embedding = self._model.encode(text, normalize_embeddings=self._normalize)
        return embedding.tolist()
    
    def force_clear_cache(self):
        """
        Force clear GPU cache immediately.
        
        Call this manually if you notice memory pressure building up,
        or at strategic points in long-running jobs.
        """
        self._clear_gpu_cache(force=True)
        logger.info(f"Forced GPU cache clear (total clears: {self._total_cache_clears})")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get GPU memory statistics (if available).
        
        Returns:
            Dict with memory info for debugging
        """
        import torch
        
        stats = {
            "device": self._actual_device,
            "embed_calls": self._embed_call_count,
            "cache_clears": self._total_cache_clears,
            "cache_clear_interval": self._mps_cache_clear_interval,
        }
        
        try:
            if self._actual_device == "mps":
                # MPS memory info (limited availability)
                if hasattr(torch.mps, 'current_allocated_memory'):
                    stats["mps_allocated_mb"] = torch.mps.current_allocated_memory() / (1024 * 1024)
                if hasattr(torch.mps, 'driver_allocated_memory'):
                    stats["mps_driver_mb"] = torch.mps.driver_allocated_memory() / (1024 * 1024)
            elif self._actual_device == "cuda":
                stats["cuda_allocated_mb"] = torch.cuda.memory_allocated() / (1024 * 1024)
                stats["cuda_cached_mb"] = torch.cuda.memory_reserved() / (1024 * 1024)
        except Exception as e:
            stats["memory_error"] = str(e)
        
        return stats
    
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
            "normalize": self._normalize,
            "device": self._actual_device or self._device,
            "tokenizer_parallelism": self._tokenizer_parallelism,
            "has_thread_pool": self._pool is not None,
            "mps_cache_clear_interval": self._mps_cache_clear_interval,
            "total_cache_clears": self._total_cache_clears,
        }
    
    def __del__(self):
        """Cleanup thread pool and GPU cache on destruction."""
        # Final cache clear
        try:
            self._clear_gpu_cache(force=True)
        except:
            pass
        
        if self._pool is not None:
            try:
                self._pool.close()
                self._pool.join()
            except:
                pass


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
