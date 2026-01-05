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


class LocalHuggingFaceEmbeddings(Embeddings):
    """
    Custom wrapper for SentenceTransformer to comply with LangChain Embeddings interface.
    Provides semantic embedding generation using BGE-M3 model.
    """
    
    def __init__(self, model_path: str):
        """
        Initialize the embedding model.
        
        Args:
            model_path: Path to the local model directory or HuggingFace model ID
        """
        logger.info(f"Loading embedding model from {model_path}")
        
        # Resolve relative paths to absolute paths
        resolved_path = Path(model_path)
        if not resolved_path.is_absolute() and model_path.startswith('./'):
            # Get the backend directory (go up from services to backend)
            backend_root = Path(__file__).parent.parent
            resolved_path = (backend_root / model_path.lstrip('./')).resolve()
            logger.info(f"Resolved model path to: {resolved_path}")
            model_path = str(resolved_path)
        
        self.model = SentenceTransformer(model_path)
        logger.info(f"Embedding model loaded successfully. Dimension: {self.model.get_sentence_embedding_dimension()}")
    
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
        embeddings = self.model.encode(texts, show_progress_bar=False)
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
        embedding = self.model.encode(text)
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
    return LocalHuggingFaceEmbeddings(model_path=settings.embedding_model_path)
