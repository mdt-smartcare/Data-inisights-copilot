import os
import asyncio
from typing import List, Dict, Any, Optional

from backend.core.logging import get_logger
from backend.pipeline.vector_stores.base import BaseVectorStore

logger = get_logger(__name__)

class ChromaStore(BaseVectorStore):
    def __init__(self, collection_name: str, path: Optional[str] = None):
        import chromadb
        from chromadb.config import Settings
        
        self.collection_name = collection_name
        self.path = path or os.getenv("CHROMA_PATH", "./data/chroma_db")
        
        # Ensure directory exists
        os.makedirs(self.path, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=self.path,
            settings=Settings(anonymized_telemetry=False)
        )
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    async def upsert_batch(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        if not embeddings:
            return
            
        # Chroma is synchronous, so we wrap it
        loop = asyncio.get_event_loop()
        collection = self._get_collection()
        
        def _sync_upsert():
            # Batch in 1000s roughly limits memory 
            batch_size = 1000
            for i in range(0, len(ids), batch_size):
                collection.upsert(
                    ids=ids[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                    embeddings=embeddings[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
                
        await loop.run_in_executor(None, _sync_upsert)

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        collection = self._get_collection()
        where_clause = filter_dict if filter_dict else None
        
        def _sync_search():
            return collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )
            
        results = await loop.run_in_executor(None, _sync_search)
        
        normalized_results = []
        if not results["ids"] or not results["ids"][0]:
            return []
            
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            # Convert default L2 or internal distance to similarity map
            similarity = 1 - distance
            
            normalized_results.append({
                "id": results["ids"][0][i],
                "score": similarity,
                "metadata": results["metadatas"][0][i],
                "document": results["documents"][0][i]
            })
            
        return normalized_results

    async def delete_collection(self) -> None:
        loop = asyncio.get_event_loop()
        def _sync_delete():
            try:
                self.client.delete_collection(self.collection_name)
                self._collection = None
            except Exception:
                pass
        await loop.run_in_executor(None, _sync_delete)

    async def delete_by_source_ids(self, source_ids: List[str]) -> None:
        if not source_ids:
            return
        loop = asyncio.get_event_loop()
        collection = self._get_collection()
        def _sync_delete():
            for i in range(0, len(source_ids), 100):
                batch = source_ids[i:i+100]
                collection.delete(where={"source_id": {"$in": batch}})
        await loop.run_in_executor(None, _sync_delete)
