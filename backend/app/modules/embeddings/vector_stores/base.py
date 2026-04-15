"""
Abstract base class for vector database operations.

Allows seamlessly swapping between ChromaDB (local/small) and Qdrant (production).
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseVectorStore(ABC):
    """
    Abstract interface for vector database operations.
    
    All vector store implementations must implement these methods
    to ensure consistent behavior across different backends.
    """

    @abstractmethod
    async def upsert_batch(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        """
        Upsert a batch of vectors and payloads.
        
        Args:
            ids: Unique identifiers for each document
            documents: Text content of each document
            embeddings: Vector embeddings for each document
            metadatas: Metadata dictionaries for each document
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for nearest neighbors.
        
        Args:
            query_embedding: Vector to search for
            top_k: Number of results to return
            filter_dict: Optional metadata filters
            
        Returns:
            List of results in standard format:
            [
                {"id": str, "score": float, "metadata": dict, "document": str},
                ...
            ]
        """
        pass

    @abstractmethod
    async def delete_collection(self) -> None:
        """Delete the collection if it exists."""
        pass

    @abstractmethod
    async def delete_by_source_ids(self, source_ids: List[str]) -> None:
        """Delete chunks associated with the given source_ids."""
        pass
    
    @abstractmethod
    async def get_collection_count(self) -> int:
        """Get the number of vectors in the collection."""
        pass
    
    @abstractmethod
    async def collection_exists(self) -> bool:
        """Check if the collection exists."""
        pass
