"""
Embedding service using HuggingFace SentenceTransformer.
Wraps the BGE-M3 model for LangChain compatibility.
"""
from typing import List
from pathlib import Path
from functools import lru_cache
from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class _EmbeddingService:
    """
    Singleton service to manage the embedding model.
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

    def get_model(self) -> SentenceTransformer:
        """Get the loaded embedding model."""
        if self._model is None:
            # This should not happen if the app lifecycle is managed correctly
            logger.error("Embedding model was requested before it was loaded.")
            raise RuntimeError("Embedding model not loaded.")
        return self._model

class LocalHuggingFaceEmbeddings(Embeddings):
    """
    Custom wrapper for SentenceTransformer to comply with LangChain Embeddings interface.
    Provides semantic embedding generation using BGE-M3 model.
    """
    
    def __init__(self):
        """
        Initialize the embedding model wrapper.
        The actual model is loaded and managed by the _EmbeddingService singleton.
        """
        self.model = _EmbeddingService().get_model()
    
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
        embeddings = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query text.
        
        Args:
            text: Query text to embed
        
        Returns:
            Embedding vector
        """
        logger.debug(f"Embedding query: {text[:100]}...")
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()


@lru_cache()
def get_embedding_model() -> LocalHuggingFaceEmbeddings:
    """
    Get cached embedding model instance.
    Singleton pattern to avoid loading model multiple times.
    
    Returns:
        Cached embedding model
    """
    return LocalHuggingFaceEmbeddings()

def preload_embedding_model():
    """
    Preloads the embedding model by initializing the singleton service.
    """
    logger.info("Preloading embedding model...")
    _EmbeddingService()
    logger.info("Embedding model preloaded.")
