"""
Vector Store Factory.

Provides unified interface to create vector store instances based on configuration.
Supports Qdrant (primary/production) and ChromaDB (fallback/development).
"""
import os
import threading
from typing import Dict, Optional

from app.core.utils.logging import get_logger
from app.modules.embeddings.vector_stores.base import BaseVectorStore

logger = get_logger(__name__)


def get_vector_store_type() -> str:
    """
    Get the configured vector store type from environment.
    
    Returns:
        'qdrant' or 'chroma'
    """
    return os.getenv("VECTOR_STORE_TYPE", "qdrant").lower().strip()


class VectorStoreFactory:
    """
    Factory to initialize the appropriate vector database client based on configuration.
    
    Usage:
        # Get a vector store for a collection
        store = VectorStoreFactory.get_provider("qdrant", collection_name="my_collection")
        
        # Or use the default provider from environment
        store = VectorStoreFactory.get_provider(get_vector_store_type(), collection_name="my_collection")
    """
    
    @staticmethod
    def get_provider(provider_type: str, collection_name: str) -> BaseVectorStore:
        """
        Get a vector store instance.
        
        Args:
            provider_type: 'qdrant' or 'chroma'
            collection_name: Name of the collection
            
        Returns:
            BaseVectorStore instance
        """
        provider_type = provider_type.lower().strip()
        
        if provider_type == "chroma":
            from app.modules.embeddings.vector_stores.chroma import ChromaStore
            logger.debug(f"Initializing ChromaDB Vector Store for collection '{collection_name}'")
            return ChromaStore(collection_name=collection_name)
        
        elif provider_type == "qdrant":
            from app.modules.embeddings.vector_stores.qdrant import QdrantStore
            logger.debug(f"Initializing Qdrant Vector Store for collection '{collection_name}'")
            return QdrantStore(collection_name=collection_name)
        
        else:
            logger.warning(f"Unknown vector DB provider '{provider_type}'. Defaulting to Qdrant.")
            from app.modules.embeddings.vector_stores.qdrant import QdrantStore
            return QdrantStore(collection_name=collection_name)


class VectorStoreManager:
    """
    Singleton manager for vector store instances.
    
    Caches vector store instances to avoid creating multiple clients
    for the same collection.
    """
    _instances: Dict[str, BaseVectorStore] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_store(
        cls, 
        collection_name: str, 
        provider_type: Optional[str] = None
    ) -> BaseVectorStore:
        """
        Get or create a vector store instance for the given collection.
        
        Args:
            collection_name: Name of the collection
            provider_type: Optional override for provider type (qdrant/chroma)
            
        Returns:
            BaseVectorStore instance
        """
        if provider_type is None:
            provider_type = get_vector_store_type()
        
        cache_key = f"{provider_type}:{collection_name}"
        
        with cls._lock:
            if cache_key not in cls._instances:
                logger.info(f"Creating new {provider_type} vector store for collection: {collection_name}")
                cls._instances[cache_key] = VectorStoreFactory.get_provider(
                    provider_type,
                    collection_name=collection_name
                )
            return cls._instances[cache_key]
    
    @classmethod
    def clear_cache(cls):
        """Clear all cached vector store instances."""
        with cls._lock:
            cls._instances.clear()
            logger.info("Cleared vector store cache")


def get_vector_store(
    collection_name: str, 
    provider_type: Optional[str] = None
) -> BaseVectorStore:
    """
    Convenience function to get a vector store instance.
    
    Args:
        collection_name: Name of the collection
        provider_type: Optional override (qdrant/chroma). Defaults to env setting.
        
    Returns:
        BaseVectorStore instance
    """
    return VectorStoreManager.get_store(collection_name, provider_type)
