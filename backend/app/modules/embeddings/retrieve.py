"""
Advanced RAG Retriever for Chat/Query Pipeline.

Provides:
- Hybrid retrieval (Dense embeddings + BM25 sparse)
- Parent-child document linking (Small-to-Big strategy)
- CrossEncoder reranking with LRU caching
- Dynamic score pruning (cliff detection)
- Medical synonym expansion
- Lazy BM25 loading (faster startup)
- Qdrant/ChromaDB filter conversion

Ported from old backend with performance optimizations.
"""
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
from collections import OrderedDict
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, BaseModel

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Reranker Performance Optimizations
# =============================================================================

# Dedicated thread pool for CPU-bound CrossEncoder inference.
_RERANK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reranker")

# LRU cache for reranker results: cache_key -> List[(doc_index, score)]
_RERANK_CACHE: OrderedDict[str, List[Tuple[int, float]]] = OrderedDict()
_RERANK_CACHE_MAX = 256


def _compute_rerank_cache_key(query: str, doc_contents: List[str]) -> str:
    """Compute a stable cache key from query + document contents."""
    hasher = hashlib.md5()
    hasher.update(query.encode('utf-8'))
    for content in doc_contents:
        hasher.update(content[:200].encode('utf-8'))  # First 200 chars per doc
    return hasher.hexdigest()


def _rerank_with_cache(
    reranker,
    query: str,
    merged_docs: List[Document],
    k_final: int,
) -> List[Document]:
    """
    Rerank with LRU caching.
    
    Caching eliminates re-computation for repeated/similar queries (~200-500ms savings).
    """
    doc_contents = [doc.page_content for doc in merged_docs]
    cache_key = _compute_rerank_cache_key(query, doc_contents)
    
    # Check cache
    if cache_key in _RERANK_CACHE:
        cached_scores = _RERANK_CACHE[cache_key]
        _RERANK_CACHE.move_to_end(cache_key)  # LRU
        logger.debug(f"Reranker cache HIT for query: {query[:50]}...")
        
        result = []
        for idx, score in cached_scores[:k_final]:
            if idx < len(merged_docs):
                result.append(merged_docs[idx])
        return result
    
    # Cache miss — run CrossEncoder
    logger.debug(f"Reranker cache MISS for query: {query[:50]}...")
    pairs = [[query, content] for content in doc_contents]
    scores = reranker.predict(pairs)
    
    # Sort by score descending
    indexed_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    
    # Store in cache
    _RERANK_CACHE[cache_key] = indexed_scores
    if len(_RERANK_CACHE) > _RERANK_CACHE_MAX:
        _RERANK_CACHE.popitem(last=False)  # Remove oldest
    
    return [merged_docs[idx] for idx, _ in indexed_scores[:k_final]]


def _convert_filter_to_qdrant(filter_dict: Optional[Dict[str, Any]], vector_store_type: str) -> Optional[Any]:
    """
    Convert MongoDB-style filter to Qdrant filter format.
    
    Args:
        filter_dict: MongoDB-style filter, e.g., {"patient_id": {"$in": ["123", "456"]}}
        vector_store_type: The type of vector store ("qdrant" or "chroma")
    
    Returns:
        Qdrant Filter object for qdrant, or original dict for chroma
    """
    if filter_dict is None:
        return None
    
    # For ChromaDB, return the filter as-is
    if vector_store_type != "qdrant":
        return filter_dict
    
    # For Qdrant, convert MongoDB-style to Qdrant Filter format
    try:
        from qdrant_client import models
        
        conditions = []
        
        for field, condition in filter_dict.items():
            if isinstance(condition, dict):
                if "$in" in condition:
                    values = condition["$in"]
                    valid_values = [str(v) for v in values if v is not None and str(v).lower() != 'none']
                    if valid_values:
                        conditions.append(
                            models.FieldCondition(
                                key=f"metadata.{field}",
                                match=models.MatchAny(any=valid_values)
                            )
                        )
                elif "$eq" in condition:
                    value = condition["$eq"]
                    if value is not None:
                        conditions.append(
                            models.FieldCondition(
                                key=f"metadata.{field}",
                                match=models.MatchValue(value=str(value))
                            )
                        )
            else:
                if condition is not None:
                    conditions.append(
                        models.FieldCondition(
                            key=f"metadata.{field}",
                            match=models.MatchValue(value=str(condition))
                        )
                    )
        
        if not conditions:
            return None
        
        return models.Filter(must=conditions)
        
    except ImportError:
        logger.warning("qdrant_client not available, returning None filter")
        return None
    except Exception as e:
        logger.error(f"Failed to convert filter to Qdrant format: {e}")
        return None


class AdvancedRAGRetriever(BaseRetriever, BaseModel):
    """
    Production-grade hybrid retriever for RAG pipeline.
    
    Features:
    - Dense retrieval via vector store (Qdrant/ChromaDB)
    - Sparse retrieval via BM25 (lazy-loaded)
    - Parent-child document linking (Small-to-Big)
    - CrossEncoder reranking with caching
    - Dynamic score pruning
    - Medical synonym expansion
    """
    
    config: Dict = Field(default_factory=dict)
    embedding_function: Any = Field(default=None)
    vector_store: Any = Field(default=None)
    docstore: Any = Field(default=None)

    child_chunk_retriever: Any = Field(default=None)
    sparse_retriever: Any = Field(default=None)
    reranker: Any = Field(default=None)
    _bm25_initialized: bool = False
    _vector_store_type: str = "qdrant"
    
    # Medical synonyms for query expansion
    medical_synonyms: Dict[str, List[str]] = Field(default_factory=dict)
    
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, config: Dict, **kwargs):
        """Initialize the hybrid retriever with both dense and sparse components."""
        super().__init__(**kwargs)
        self.config = config
        
        # Get vector store type from environment
        from app.modules.embeddings.vector_stores.factory import get_vector_store_type
        self._vector_store_type = get_vector_store_type()
        logger.info(f"Initializing RAG Retriever with vector store type: {self._vector_store_type}")
        
        # Resolve paths in config
        self._resolve_config_paths()
        
        # Initialize embedding function
        self.embedding_function = self._get_embedding_function()
        
        # Load vector store and docstore
        self.vector_store = self._load_vector_store()
        self.docstore = self._load_docstore()
        
        
        # Initialize retrievers
        self._setup_retrievers()
        
        # Initialize reranker
        reranker_model = self.config.get('retriever', {}).get('reranker_model_name')
        if reranker_model:
            logger.info(f"Initializing reranker: {reranker_model}")
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(reranker_model)
        else:
            logger.warning("No reranker model specified. Reranking will be skipped.")
            self.reranker = None
        
        # Load medical synonyms from config
        self.medical_synonyms = self.config.get('medical_synonyms', {})
        
        logger.info("Advanced RAG Retriever initialized successfully.")

    def _resolve_config_paths(self):
        """Resolve relative paths in config to absolute paths."""
        from app.core.config import get_settings
        settings = get_settings()
        
        # Resolve vector store path
        vs_path = self.config.get('vector_store', {}).get('chroma_path', '')
        if vs_path and vs_path.startswith('./'):
            resolved = settings.data_dir / vs_path.lstrip('./')
            self.config['vector_store']['chroma_path'] = str(resolved)
            logger.info(f"Resolved storage path to: {resolved}")
        
        # Resolve model path
        model_path = self.config.get('embedding', {}).get('model_path', '')
        if model_path and model_path.startswith('./'):
            resolved = settings.data_dir / model_path.lstrip('./')
            self.config['embedding']['model_path'] = str(resolved)
            logger.info(f"Resolved model_path to: {resolved}")

    def _get_embedding_function(self):
        """Get or create embedding function based on config."""
        emb_config = self.config.get('embedding', {})
        provider_type = emb_config.get('provider', 'bge-base-en-v1.5')
        
        from app.modules.embeddings.providers import create_embedding_provider
        return create_embedding_provider(provider_type, emb_config)

    def _setup_retrievers(self):
        """Initialize dense retriever. BM25 (sparse) is lazy-loaded on first query."""
        # Dense retriever (for child chunks from vector store)
        self.child_chunk_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": 50}
        )
        
        # BM25 Sparse Retriever — LAZY LOADED
        # Building BM25 index on 100K+ docs takes 10-30s, so defer to first query.
        self.sparse_retriever = None
        self._bm25_initialized = False
        logger.info("Dense retriever ready. BM25 will be loaded on first query.")

    def _ensure_bm25(self):
        """Lazy-load BM25 index on first query."""
        if self._bm25_initialized:
            return
        
        try:
            all_parent_doc_keys = list(self.docstore.yield_keys())
            logger.info(f"Lazy-loading BM25: {len(all_parent_doc_keys)} parent documents...")
            
            parent_documents = list(self.docstore.mget(all_parent_doc_keys))
            bm25_docs = [doc for doc in parent_documents if doc is not None]
            
            if not bm25_docs:
                logger.error("No parent documents found for BM25.")
                self._bm25_initialized = True
                return
            
            from langchain_community.retrievers.bm25 import BM25Retriever
            self.sparse_retriever = BM25Retriever.from_documents(
                bm25_docs,
                k=self.config.get('retriever', {}).get('top_k_initial', 50)
            )
            logger.info(f"BM25 index built lazily with {len(bm25_docs)} documents.")
        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
        finally:
            self._bm25_initialized = True

    def refresh_bm25(self):
        """Force-rebuild the BM25 index (e.g., after a vector DB update)."""
        logger.info("Refreshing BM25 index...")
        self._bm25_initialized = False
        self._ensure_bm25()

    async def aget_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """Async retrieval not implemented."""
        raise NotImplementedError("Use _get_relevant_documents instead")

    def _expand_query(self, query: str) -> str:
        """Expand query with medical synonyms for better retrieval."""
        query_lower = query.lower()
        expanded_terms = [query]
        
        for term, synonyms in self.medical_synonyms.items():
            if term in query_lower:
                expanded_terms.append(synonyms[0])  # Add most relevant synonym
        
        return " ".join(expanded_terms)

    def _get_relevant_documents(
        self, 
        query: str, 
        *, 
        run_manager: Any = None, 
        filter: dict = None, 
        top_k: Optional[int] = None
    ) -> List[Document]:
        """
        Full retrieval pipeline:
        1. Get PARENT docs from sparse (BM25) retriever
        2. Get PARENT docs from dense (small-to-big) retriever
        3. Merge and de-duplicate the results
        4. Rerank the merged list to get the final, most relevant docs
        """
        logger.info(f"Executing query: {query}")
        
        k_final = top_k or self.config.get('retriever', {}).get('top_k_final', 5)
        expanded_query = self._expand_query(query)
        
        # --- 1. DENSE (small-to-big) RETRIEVAL WITH DYNAMIC SCORE PRUNING ---
        try:
            qdrant_filter = _convert_filter_to_qdrant(filter, self._vector_store_type)
            dense_results = self.vector_store.similarity_search_with_score(
                expanded_query, k=50, filter=qdrant_filter
            )
        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}. Continuing with sparse only.")
            dense_results = []
        
        child_chunks = []
        if dense_results:
            scores = [s for _, s in dense_results]
            cliff_idx = len(dense_results)
            min_candidates = min(5, len(dense_results))
            
            # Dynamic score pruning: find sudden drop in relevance scores
            for i in range(min_candidates, len(dense_results) - 1):
                s1, s2 = scores[i-1], scores[i]
                diff = abs(s1 - s2)
                denom = max(abs(s1), abs(s2), 1e-5)
                relative_drop = diff / denom
                
                if relative_drop > 0.15:  # 15% sudden drop
                    cliff_idx = i
                    logger.info(f"Dynamic Pruning: Found cliff at index {cliff_idx}. Pruning {len(dense_results) - cliff_idx} candidates.")
                    break
            
            child_chunks = [doc for doc, _ in dense_results[:cliff_idx]]
        
        # Get unique parent IDs from child chunks
        parent_ids = list(set([
            doc.metadata['doc_id'] 
            for doc in child_chunks 
            if 'doc_id' in doc.metadata
        ]))
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]
        
        # --- 2. SPARSE (BM25) RETRIEVAL (lazy-loaded) ---
        self._ensure_bm25()
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(
                expanded_query, run_manager=run_manager
            )
        
        # --- 3. MERGE & DE-DUPLICATE ---
        merged_docs_dict = {
            (doc.page_content, doc.metadata.get('source_id', '')): doc 
            for doc in dense_parent_docs
        }
        for doc in sparse_parent_docs:
            key = (doc.page_content, doc.metadata.get('source_id', ''))
            if key not in merged_docs_dict:
                merged_docs_dict[key] = doc
        
        merged_docs = list(merged_docs_dict.values())
        
        # --- 4. RERANK (with caching) ---
        if not self.reranker or not merged_docs:
            logger.info(f"Skipping reranking. Returning {len(merged_docs)} merged docs.")
            return merged_docs[:k_final]
        
        logger.info(f"Reranking {len(merged_docs)} documents for query: '{query}'")
        final_docs = _rerank_with_cache(self.reranker, query, merged_docs, k_final)
        
        logger.info(f"Returning {len(final_docs)} reranked documents.")
        return final_docs

    def _load_vector_store(self):
        """Load the vector store using VectorStoreFactory."""
        collection_name = self.config.get('vector_store', {}).get('collection_name', 'default')
        
        if self._vector_store_type == "qdrant":
            try:
                from langchain_qdrant import QdrantVectorStore
                from qdrant_client import QdrantClient
                
                qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
                logger.info(f"Connecting to Qdrant at {qdrant_url} for collection: {collection_name}")
                
                client = QdrantClient(url=qdrant_url)
                
                # Wrap embedding function for LangChain compatibility
                class EmbeddingWrapper:
                    def __init__(self, provider):
                        self.provider = provider
                    
                    def embed_documents(self, texts):
                        return self.provider.embed_documents(texts)
                    
                    def embed_query(self, text):
                        return self.provider.embed_query_cached(text)
                
                return QdrantVectorStore(
                    client=client,
                    collection_name=collection_name,
                    embedding=EmbeddingWrapper(self.embedding_function)
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant: {e}. Falling back to ChromaDB.")
                self._vector_store_type = "chroma"
        
        # Fallback to ChromaDB
        import chromadb
        from langchain_chroma import Chroma
        
        chroma_path = self.config.get('vector_store', {}).get('chroma_path', './data/indexes/default')
        logger.info(f"Using ChromaDB at {chroma_path} for collection: {collection_name}")
        
        client_settings = chromadb.Settings(anonymized_telemetry=False)
        
        class EmbeddingWrapper:
            def __init__(self, provider):
                self.provider = provider
            
            def embed_documents(self, texts):
                return self.provider.embed_documents(texts)
            
            def embed_query(self, text):
                return self.provider.embed_query_cached(text)
        
        return Chroma(
            persist_directory=chroma_path,
            embedding_function=EmbeddingWrapper(self.embedding_function),
            collection_name=collection_name,
            client_settings=client_settings
        )

    def _load_docstore(self):
        """Load the parent document store."""
        from app.core.config import get_settings
        settings = get_settings()
        
        collection_name = self.config.get('vector_store', {}).get('collection_name', 'default')
        
        # Try SQLite docstore first (new format)
        sqlite_path = settings.data_dir / "docstores" / collection_name / "parent_docs.db"
        if sqlite_path.exists():
            logger.info(f"Loading SQLite docstore from {sqlite_path}")
            from app.modules.embeddings.docstore import SQLiteDocStore
            return SQLiteDocStore(str(sqlite_path))
        
        # Fall back to pickle docstore (old format)
        chroma_path = self.config.get('vector_store', {}).get('chroma_path', '')
        pickle_path = f"{chroma_path}/parent_docstore.pkl" if chroma_path else None
        
        if pickle_path and Path(pickle_path).exists():
            try:
                logger.info(f"Loading pickle docstore from {pickle_path}")
                from app.modules.embeddings.pickle_utils import load_with_remapping
                return load_with_remapping(pickle_path)
            except Exception as e:
                logger.error(f"Failed to load pickle docstore: {e}")
        
        # Create empty in-memory docstore
        logger.warning("No docstore found. Creating empty in-memory store.")
        from app.modules.embeddings.transform import SimpleInMemoryStore
        return SimpleInMemoryStore()

    def retrieve_and_rerank_with_scores(
        self, 
        query: str, 
        top_k: Optional[int] = None, 
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Document, float]]:
        """
        Retrieval method that returns documents AND their reranker scores.
        Useful for embedding explorers and debugging.
        """
        logger.info(f"Executing retrieve_and_rerank_with_scores for: {query}")
        
        k_final = top_k or self.config.get('retriever', {}).get('top_k_final', 5)
        expanded_query = self._expand_query(query)
        
        # Dense retrieval with score pruning
        try:
            dense_results = self.vector_store.similarity_search_with_score(
                expanded_query, 
                k=50, 
                filter=_convert_filter_to_qdrant(filter, self._vector_store_type)
            )
        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}")
            dense_results = []
        
        child_chunks = []
        if dense_results:
            scores = [s for _, s in dense_results]
            cliff_idx = len(dense_results)
            min_candidates = min(5, len(dense_results))
            
            for i in range(min_candidates, len(dense_results) - 1):
                diff = abs(scores[i-1] - scores[i])
                denom = max(abs(scores[i-1]), abs(scores[i]), 1e-5)
                if diff / denom > 0.15:
                    cliff_idx = i
                    break
            
            child_chunks = [doc for doc, _ in dense_results[:cliff_idx]]
        
        parent_ids = list(set([
            doc.metadata['doc_id'] 
            for doc in child_chunks 
            if 'doc_id' in doc.metadata
        ]))
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]
        
        # Sparse retrieval
        self._ensure_bm25()
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(
                expanded_query, run_manager=None
            )
        
        # Merge & de-duplicate
        merged_docs_dict = {
            (doc.page_content, doc.metadata.get('source_id', '')): doc 
            for doc in dense_parent_docs
        }
        for doc in sparse_parent_docs:
            key = (doc.page_content, doc.metadata.get('source_id', ''))
            if key not in merged_docs_dict:
                merged_docs_dict[key] = doc
        
        merged_docs = list(merged_docs_dict.values())
        
        if not merged_docs:
            return []
        
        # Rerank with scores
        if not self.reranker:
            logger.warning("No reranker. Returning merged docs with placeholder scores.")
            return [(doc, 0.0) for doc in merged_docs[:k_final]]
        
        doc_contents = [doc.page_content for doc in merged_docs]
        cache_key = _compute_rerank_cache_key(query, doc_contents)
        
        if cache_key in _RERANK_CACHE:
            _RERANK_CACHE.move_to_end(cache_key)
            indexed_scores = _RERANK_CACHE[cache_key]
        else:
            pairs = [[query, content] for content in doc_contents]
            scores = self.reranker.predict(pairs)
            indexed_scores = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            _RERANK_CACHE[cache_key] = indexed_scores
            if len(_RERANK_CACHE) > _RERANK_CACHE_MAX:
                _RERANK_CACHE.popitem(last=False)
        
        return [
            (merged_docs[idx], float(score))
            for idx, score in indexed_scores[:k_final]
            if idx < len(merged_docs)
        ]


# =============================================================================
# Factory Function
# =============================================================================

def create_retriever(
    collection_name: str,
    config: Optional[Dict[str, Any]] = None
) -> AdvancedRAGRetriever:
    """
    Factory function to create a retriever for a collection.
    
    Args:
        collection_name: Name of the vector store collection
        config: Optional retriever configuration
    
    Returns:
        Configured AdvancedRAGRetriever instance
    """
    default_config = {
        'vector_store': {
            'collection_name': collection_name,
        },
        'retriever': {
            'top_k_initial': 50,
            'top_k_final': 5,
            'reranker_model_name': 'cross-encoder/ms-marco-MiniLM-L-6-v2',
        },
        'chunking': {
            'child_splitter': {
                'chunk_size': 128,
                'chunk_overlap': 25,
            }
        },
        'embedding': {
            'provider': 'bge-base-en-v1.5',
        }
    }
    
    if config:
        # Deep merge config
        for key, value in config.items():
            if isinstance(value, dict) and key in default_config:
                default_config[key].update(value)
            else:
                default_config[key] = value
    
    return AdvancedRAGRetriever(config=default_config)
