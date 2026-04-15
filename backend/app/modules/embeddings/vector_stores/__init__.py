"""
Vector Store Abstraction Layer.

Supports Qdrant (primary) and ChromaDB (fallback) for production-ready,
horizontally scalable vector operations.
"""
from app.modules.embeddings.vector_stores.base import BaseVectorStore
from app.modules.embeddings.vector_stores.factory import VectorStoreFactory

__all__ = ["BaseVectorStore", "VectorStoreFactory"]
