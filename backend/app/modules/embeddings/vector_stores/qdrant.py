"""
Qdrant Vector Store Implementation.

Production-ready vector storage with horizontal scalability.
Recommended for production workloads.
"""
import os
from typing import List, Dict, Any, Optional

from app.core.utils.logging import get_logger
from app.modules.embeddings.vector_stores.base import BaseVectorStore

logger = get_logger(__name__)


class VectorDimensionMismatchError(Exception):
    """Raised when vector dimensions don't match the collection configuration."""
    pass


class QdrantStore(BaseVectorStore):
    """
    Qdrant implementation of BaseVectorStore.
    
    Best for:
    - Production workloads
    - Large datasets (1M+ vectors)
    - Horizontal scaling
    - High availability requirements
    
    Requires Qdrant server running (docker or cloud).
    Set QDRANT_URL environment variable (default: http://localhost:6333)
    """
    
    def __init__(
        self, 
        collection_name: str, 
        url: Optional[str] = None,
        auto_recreate_on_dimension_mismatch: bool = True
    ):
        from qdrant_client import AsyncQdrantClient
        
        self.collection_name = collection_name
        self.url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        self.auto_recreate_on_dimension_mismatch = auto_recreate_on_dimension_mismatch
        
        # Initialize async client
        self.client = AsyncQdrantClient(url=self.url)
        
        # Track whether collection has been validated
        self._collection_checked = False
        self._validated_dimension: Optional[int] = None
        
        logger.info(f"QdrantStore initialized for collection '{collection_name}' at {self.url}")
    
    async def _get_collection_dimension(self) -> Optional[int]:
        """Get the vector dimension of an existing collection."""
        from qdrant_client.models import VectorParams
        
        try:
            collection_info = await self.client.get_collection(self.collection_name)
            vectors_config = collection_info.config.params.vectors
            
            # Handle both single vector and named vectors config
            if isinstance(vectors_config, VectorParams):
                return vectors_config.size
            elif isinstance(vectors_config, dict):
                # Named vectors - get the default or first one
                if "" in vectors_config:
                    return vectors_config[""].size
                elif vectors_config:
                    return next(iter(vectors_config.values())).size
            return None
        except Exception as e:
            logger.warning(f"Could not get collection dimension: {e}")
            return None
    
    async def _ensure_collection(self, vector_size: int = 1024):
        """Ensure collection exists with the correct vector dimension."""
        from qdrant_client import models
        
        # Skip if already validated with the same dimension
        if self._collection_checked and self._validated_dimension == vector_size:
            return
        
        try:
            exists = await self.client.collection_exists(self.collection_name)
            
            if exists:
                # Check if existing collection has matching dimension
                existing_dim = await self._get_collection_dimension()
                
                if existing_dim is not None and existing_dim != vector_size:
                    logger.warning(
                        f"Vector dimension mismatch for collection '{self.collection_name}': "
                        f"existing={existing_dim}, required={vector_size}"
                    )
                    
                    if self.auto_recreate_on_dimension_mismatch:
                        logger.info(
                            f"Auto-recreating collection '{self.collection_name}' with new dimension {vector_size}. "
                            f"Old dimension was {existing_dim}. All existing vectors will be deleted."
                        )
                        await self.client.delete_collection(self.collection_name)
                        exists = False  # Will create below
                    else:
                        raise VectorDimensionMismatchError(
                            f"Collection '{self.collection_name}' has dimension {existing_dim} "
                            f"but embeddings have dimension {vector_size}. "
                            f"Delete the collection or enable auto_recreate_on_dimension_mismatch."
                        )
                else:
                    logger.debug(f"Collection '{self.collection_name}' exists with matching dimension {existing_dim}")
            
            if not exists:
                logger.info(f"Creating Qdrant collection '{self.collection_name}' (dim={vector_size})")
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
            self._validated_dimension = vector_size
            
        except VectorDimensionMismatchError:
            raise
        except Exception as e:
            logger.error(f"Failed to ensure collection '{self.collection_name}': {e}")
            raise
    
    async def upsert_batch(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> None:
        """Upsert a batch of vectors to Qdrant."""
        from qdrant_client import models
        import uuid
        
        if not embeddings:
            return
        
        vector_size = len(embeddings[0])
        await self._ensure_collection(vector_size)
        
        # Build points for Qdrant
        points = []
        for i, (doc_id, doc, emb, meta) in enumerate(zip(ids, documents, embeddings, metadatas)):
            # Qdrant requires UUID or int IDs - we'll use UUID and store original ID in payload
            try:
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))
            except Exception:
                point_id = str(uuid.uuid4())
            
            # Store original ID and document in payload
            payload = {
                "_original_id": doc_id,
                "_document": doc,
                **meta
            }
            
            points.append(models.PointStruct(
                id=point_id,
                vector=emb,
                payload=payload
            ))
        
        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            await self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True
            )
        
        logger.debug(f"Upserted {len(points)} points to collection '{self.collection_name}'")
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for nearest neighbors in Qdrant."""
        from qdrant_client import models
        
        await self._ensure_collection(vector_size=len(query_embedding))
        
        # Build filter conditions
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
            document = payload.get("_document", "")
            
            # Remove internal fields from metadata
            metadata = {k: v for k, v in payload.items() if not k.startswith("_")}
            
            normalized_results.append({
                "id": orig_id,
                "score": hit.score,
                "metadata": metadata,
                "document": document
            })
        
        return normalized_results
    
    async def delete_collection(self) -> None:
        """Delete the collection if it exists."""
        try:
            exists = await self.client.collection_exists(self.collection_name)
            if exists:
                await self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted Qdrant collection '{self.collection_name}'")
            self._collection_checked = False
            self._validated_dimension = None
        except Exception as e:
            logger.warning(f"Failed to delete collection '{self.collection_name}': {e}")
    
    async def delete_by_source_ids(self, source_ids: List[str]) -> None:
        """Delete chunks by source IDs."""
        from qdrant_client import models
        
        if not source_ids:
            return
        
        try:
            # Delete points where _original_id matches any of the source_ids
            for source_id in source_ids:
                await self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="_original_id",
                                    match=models.MatchValue(value=source_id)
                                )
                            ]
                        )
                    )
                )
            logger.debug(f"Deleted {len(source_ids)} source IDs from collection '{self.collection_name}'")
        except Exception as e:
            logger.warning(f"Failed to delete by source IDs: {e}")
    
    async def get_collection_count(self) -> int:
        """Get the number of vectors in the collection."""
        try:
            exists = await self.client.collection_exists(self.collection_name)
            if not exists:
                return 0
            
            collection_info = await self.client.get_collection(self.collection_name)
            return collection_info.points_count or 0
        except Exception as e:
            logger.warning(f"Failed to get collection count: {e}")
            return 0
    
    async def collection_exists(self) -> bool:
        """Check if the collection exists."""
        try:
            return await self.client.collection_exists(self.collection_name)
        except Exception as e:
            logger.warning(f"Failed to check collection existence: {e}")
            return False
