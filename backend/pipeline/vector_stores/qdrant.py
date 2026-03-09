import os
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient, models

from backend.core.logging import get_logger
from backend.pipeline.vector_stores.base import BaseVectorStore

logger = get_logger(__name__)

class QdrantStore(BaseVectorStore):
    def __init__(self, collection_name: str, url: Optional[str] = None):
        self.collection_name = collection_name
        # Allow override via env for Celery/Docker
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.client = AsyncQdrantClient(url=self.url)
        self._collection_checked = False

    async def _ensure_collection(self, vector_size: int = 1024):
        if self._collection_checked:
            return
            
        try:
            exists = await self.client.collection_exists(self.collection_name)
            if not exists:
                logger.info(f"Creating Qdrant collection {self.collection_name} (dim={vector_size})")
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    ),
                    # Optimization for Memmap storage 
                    optimizers_config=models.OptimizersConfigDiff(
                        memmap_threshold=10000
                    )
                )
            self._collection_checked = True
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collection: {e}")
            raise

    async def upsert_batch(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        if not embeddings:
            return
            
        await self._ensure_collection(vector_size=len(embeddings[0]))
        
        # Qdrant expects payload to contain everything else.
        payloads = []
        for doc, meta in zip(documents, metadatas):
            payload = meta.copy()
            payload["document_content"] = doc # Store document in payload
            payloads.append(payload)
            
        # Qdrant requires UUID or integer. If our IDs are string hashes, we pass them directly,
        # but Qdrant accepts string UUIDs. If they are not valid UUIDs, we might need an adapter.
        # But Qdrant string IDs require standard UUID format.
        import uuid
        qdrant_ids = []
        id_map = {}
        for original_id in ids:
            try:
                qdrant_id = str(uuid.UUID(original_id))
            except ValueError:
                # If it's not a UUID, hash it to a UUID
                import hashlib
                hash_val = hashlib.md5(original_id.encode()).hexdigest()
                qdrant_id = str(uuid.UUID(hash_val))
            qdrant_ids.append(qdrant_id)
            id_map[qdrant_id] = original_id
            
        # Also store original ID in payload just in case
        for payload, orig_id in zip(payloads, ids):
            payload["_original_id"] = orig_id
            
        points = [
            models.PointStruct(
                id=q_id,
                vector=emb,
                payload=pay
            )
            for q_id, emb, pay in zip(qdrant_ids, embeddings, payloads)
        ]
        
        await self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        await self._ensure_collection(vector_size=len(query_embedding))
        
        # Build filter conditions (simple term matching for now)
        qdrant_filter = None
        if filter_dict:
            must_conditions = [
                models.FieldCondition(
                    key=k, match=models.MatchValue(value=v)
                )
                for k, v in filter_dict.items()
            ]
            qdrant_filter = models.Filter(must=must_conditions)
            
        results_obj = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True
        )
        results = results_obj.points
        
        normalized_results = []
        for hit in results:
            payload = hit.payload or {}
            orig_id = payload.get("_original_id", str(hit.id))
            doc_content = payload.pop("document_content", "")
            
            normalized_results.append({
                "id": orig_id,
                "score": hit.score,
                "metadata": payload,
                "document": doc_content
            })
            
        return normalized_results

    async def delete_collection(self) -> None:
        try:
            await self.client.delete_collection(self.collection_name)
            self._collection_checked = False
        except Exception:
            pass

    async def delete_by_source_ids(self, source_ids: List[str]) -> None:
        if not source_ids:
            return
        await self._ensure_collection()
        
        # Delete points matching payload condition manually in batches
        for i in range(0, len(source_ids), 100):
            batch = source_ids[i:i+100]
            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_id",
                            match=models.MatchAny(any=batch)
                        )
                    ]
                )
            )
