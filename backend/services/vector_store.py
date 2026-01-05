"""
Vector store service for semantic search using ChromaDB.
Provides retrieval capabilities for the RAG pipeline.
"""
import sys
import os
from pathlib import Path
from functools import lru_cache
from typing import List, Optional
import yaml

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.rag.retrieve import AdvancedRAGRetriever
from langchain_core.documents import Document

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class VectorStoreService:
    """Service for managing vector store operations."""
    
    def __init__(self):
        """Initialize the vector store with advanced retrieval."""
        logger.info("Initializing vector store service")
        
        # Load RAG configuration - resolve path relative to backend directory
        config_path = Path(settings.rag_config_path)
        if not config_path.is_absolute():
            # If relative, resolve from backend directory
            backend_root = Path(__file__).parent.parent  # backend/services -> backend/
            # Remove leading './' if present
            config_rel_path = str(settings.rag_config_path).lstrip('./')
            config_path = (backend_root / config_rel_path).resolve()
        
        logger.info(f"Looking for RAG config at: {config_path}")
        
        if not config_path.exists():
            raise FileNotFoundError(f"RAG config not found at {config_path}")
        
        logger.info(f"Loading RAG config from {config_path}")
        
        with open(config_path, 'r') as f:
            self.rag_config = yaml.safe_load(f)
        
        logger.info("Loaded RAG config successfully")
        
        # Initialize advanced retriever
        self.retriever = AdvancedRAGRetriever(config=self.rag_config)
        logger.info("Vector store initialized successfully")
    
    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        """
        Perform semantic search on the vector store.
        
        Args:
            query: Search query text
            top_k: Number of results to return (defaults to settings)
        
        Returns:
            List of relevant documents
        """
        k = top_k or settings.rag_top_k
        logger.info(f"Searching vector store for query: '{query[:100]}...' (top_k={k})")
        
        try:
            # Use the advanced retriever's invoke method
            result = self.retriever.invoke(query)
            
            # Handle different return types
            if isinstance(result, str):
                # If retriever returns string, wrap in document
                docs = [Document(page_content=result, metadata={"source": "rag"})]
            elif isinstance(result, list):
                docs = result
            else:
                docs = [Document(page_content=str(result), metadata={"source": "rag"})]
            
            logger.info(f"Retrieved {len(docs)} documents from vector store")
            return docs
            
        except Exception as e:
            logger.error(f"Vector store search failed: {e}", exc_info=True)
            raise
    
    def search_with_scores(self, query: str, top_k: Optional[int] = None) -> List[tuple]:
        """
        Perform semantic search with relevance scores.
        
        Args:
            query: Search query text
            top_k: Number of results to return
        
        Returns:
            List of (document, score) tuples
        """
        k = top_k or settings.rag_top_k
        logger.info(f"Searching with scores for: '{query[:100]}...'")
        
        try:
            # Check if retriever has reranking with scores method
            if hasattr(self.retriever, 'retrieve_and_rerank_with_scores'):
                results = self.retriever.retrieve_and_rerank_with_scores(query)
                logger.info(f"Retrieved {len(results)} documents with reranking scores")
                return results
            else:
                # Fallback to regular search
                docs = self.search(query, top_k=k)
                # Return with dummy scores
                return [(doc, 1.0) for doc in docs]
                
        except Exception as e:
            logger.error(f"Vector store search with scores failed: {e}", exc_info=True)
            raise
    
    def health_check(self) -> bool:
        """
        Check if vector store is accessible.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Perform a simple test query
            test_results = self.search("test health check", top_k=1)
            return len(test_results) >= 0  # Even 0 results means DB is accessible
        except Exception as e:
            logger.error(f"Vector store health check failed: {e}")
            return False


@lru_cache()
def get_vector_store() -> VectorStoreService:
    """
    Get cached vector store service instance.
    Singleton pattern to avoid reloading the vector database.
    
    Returns:
        Cached vector store service
    """
    return VectorStoreService()
