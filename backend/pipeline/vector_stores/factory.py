import os
from backend.core.logging import get_logger
from backend.pipeline.vector_stores.base import BaseVectorStore
from backend.pipeline.vector_stores.chroma import ChromaStore
from backend.pipeline.vector_stores.qdrant import QdrantStore

logger = get_logger(__name__)

class VectorStoreFactory:
    """Factory correctly initializes the appropriate Vector Database client based on Configuration."""
    
    @staticmethod
    def get_provider(provider_type: str, collection_name: str) -> BaseVectorStore:
        provider_type = provider_type.lower().strip()
        
        if provider_type == "chroma":
            logger.debug(f"Initializing Chroma Vector Store for collection {collection_name}")
            return ChromaStore(collection_name=collection_name)
            
        elif provider_type == "qdrant":
            logger.debug(f"Initializing Qdrant Vector Store for collection {collection_name}")
            return QdrantStore(collection_name=collection_name)
            
        else:
            logger.warning(f"Unknown vector DB provider '{provider_type}'. Defaulting to Qdrant.")
            return QdrantStore(collection_name=collection_name)
