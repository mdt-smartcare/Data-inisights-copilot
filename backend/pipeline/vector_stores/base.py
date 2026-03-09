from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseVectorStore(ABC):
    """
    Abstract interface for vector database operations.
    Allows seamlessly swapping between ChromaDB (local/small) and Qdrant (production).
    """

    @abstractmethod
    async def upsert_batch(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        """Upsert a batch of vectors and payloads."""
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
        Should return a standard format:
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
