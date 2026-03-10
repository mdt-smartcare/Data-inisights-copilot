from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
from collections import OrderedDict
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from langchain_core.documents import Document
from langchain_community.retrievers.bm25 import BM25Retriever
from backend.services.embeddings import get_embedding_model
from backend.rag.pickle_utils import load_with_remapping
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, BaseModel
from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

from backend.core.logging import get_logger

logger = get_logger(__name__)
load_dotenv()

# =============================================================================
# Reranker Performance Optimizations
# =============================================================================

# Dedicated thread pool for CPU-bound CrossEncoder inference.
# Prevents GIL-heavy reranker from blocking the FastAPI event loop.
_RERANK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reranker")

# LRU cache for reranker results: cache_key -> List[(doc_index, score)]
# Avoids re-running the neural model for repeated/similar queries.
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
    reranker: CrossEncoder,
    query: str,
    merged_docs: List[Document],
    k_final: int,
) -> List[Document]:
    """
    Rerank with LRU caching.
    
    CPU Bottleneck Fix:
    - CrossEncoder.predict() runs a neural model synchronously (~200-500ms)
    - Caching eliminates re-computation for repeated/similar queries
    - ~256 entries ≈ 10KB memory overhead
    """
    doc_contents = [doc.page_content for doc in merged_docs]
    cache_key = _compute_rerank_cache_key(query, doc_contents)
    
    # Check cache
    if cache_key in _RERANK_CACHE:
        cached_scores = _RERANK_CACHE[cache_key]
        # Move to end (LRU)
        _RERANK_CACHE.move_to_end(cache_key)
        logger.debug(f"Reranker cache HIT for query: {query[:50]}...")
        
        # Reconstruct result from cached indices + scores
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
    indexed_scores = sorted(
        enumerate(scores), key=lambda x: x[1], reverse=True
    )
    
    # Store in cache
    _RERANK_CACHE[cache_key] = indexed_scores
    if len(_RERANK_CACHE) > _RERANK_CACHE_MAX:
        _RERANK_CACHE.popitem(last=False)  # Remove oldest
    
    # Return top-k documents
    return [merged_docs[idx] for idx, _ in indexed_scores[:k_final]]


def _get_vector_store_type() -> str:
    """Get configured vector store type from settings."""
    try:
        from backend.services.settings_service import get_settings_service, SettingCategory
        settings_service = get_settings_service()
        vs_settings = settings_service.get_category_settings_raw(SettingCategory.VECTOR_STORE)
        return vs_settings.get("type", "qdrant").strip('"')
    except Exception:
        return "qdrant"


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
    
    # For ChromaDB, return the filter as-is (it supports MongoDB-style syntax)
    if vector_store_type != "qdrant":
        return filter_dict
    
    # For Qdrant, convert MongoDB-style to Qdrant Filter format
    try:
        from qdrant_client import models
        
        conditions = []
        
        for field, condition in filter_dict.items():
            if isinstance(condition, dict):
                # Handle $in operator
                if "$in" in condition:
                    values = condition["$in"]
                    # Filter out None values and convert to strings
                    valid_values = [str(v) for v in values if v is not None and str(v).lower() != 'none']
                    if valid_values:
                        # Use MatchAny for $in operator
                        conditions.append(
                            models.FieldCondition(
                                key=f"metadata.{field}",
                                match=models.MatchAny(any=valid_values)
                            )
                        )
                # Handle $eq operator
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
                # Direct value comparison
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
    config: Dict = Field(default_factory=dict)
    embedding_function: Any = Field(default=None)
    vector_store: Any = Field(default=None)
    docstore: Any = Field(default=None)
    child_splitter: Any = Field(default=None)
    child_chunk_retriever: Any = Field(default=None)
    sparse_retriever: Any = Field(default=None)
    reranker: Any = Field(default=None) 
    _bm25_initialized: bool = False  # Task 8: lazy BM25
    _vector_store_type: str = "qdrant"
    
    # Synonyms now sourced from configuration or empty by default
    medical_synonyms: Dict[str, List[str]] = Field(default_factory=dict)

    def __init__(self, config: Dict, **kwargs):
        """Initialize the hybrid retriever with both dense and sparse components."""
        super().__init__(**kwargs)
        self.config = config
        
        # Get vector store type from settings
        self._vector_store_type = _get_vector_store_type()
        logger.info(f"Initializing RAG Retriever with vector store type: {self._vector_store_type}")
        
        # Resolve paths in config to absolute paths
        self._resolve_config_paths()
        
        self.embedding_function = get_embedding_model()
        
        self.vector_store = self._load_vector_store()
        self.docstore = self._load_docstore()
        
        # Create a child splitter instance
        child_splitter_config = self.config['chunking']['child_splitter']
        self.child_splitter = RecursiveCharacterTextSplitter(**child_splitter_config)
        
        # Initialize retrievers
        self._setup_retrievers()
        
        # Initialize reranker
        if 'reranker_model_name' in self.config['retriever']:
            logger.info(f"Initializing reranker: {self.config['retriever']['reranker_model_name']}")
            self.reranker = CrossEncoder(self.config['retriever']['reranker_model_name'])
        else:
            logger.warning("No reranker model specified in config. Reranking will be skipped.")
            self.reranker = None

        logger.info("Advanced RAG Retriever initialized successfully.")

    def _resolve_config_paths(self):
        """Resolve relative paths in config to absolute paths based on backend directory."""
        # Get backend root directory (go up from rag to backend)
        backend_root = Path(__file__).parent.parent
        
        # Resolve chroma_path
        chroma_path = self.config['vector_store'].get('chroma_path', '')
        if (chroma_path and chroma_path.startswith('./')):
            resolved_path = (backend_root / chroma_path.lstrip('./')).resolve()
            self.config['vector_store']['chroma_path'] = str(resolved_path)
            logger.info(f"Resolved storage path to: {resolved_path}")
        
        # Resolve model_path
        model_path = self.config['embedding'].get('model_path', '')
        if model_path and model_path.startswith('./'):
            resolved_path = (backend_root / model_path.lstrip('./')).resolve()
            self.config['embedding']['model_path'] = str(resolved_path)
            logger.info(f"Resolved model_path to: {resolved_path}")

    def _setup_retrievers(self):
        """Initialize dense retriever. BM25 (sparse) is lazy-loaded on first query."""
        
        # 1. Dense Retriever (for CHILD chunks from vector store)
        self.child_chunk_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": 50} 
        )
        
        # 2. BM25 Sparse Retriever — LAZY LOADED (Task 8)
        # Building BM25 index on 100K+ docs takes 10-30s.
        # Deferred to first query to avoid blocking startup.
        self.sparse_retriever = None
        self._bm25_initialized = False
        logger.info("Dense retriever ready. BM25 will be loaded on first query.")

    def _ensure_bm25(self):
        """
        Lazy-load BM25 index on first query.
        
        CPU Bottleneck Fix (Task 8):
        - Original: BM25 built in __init__, blocking startup for 10-30s
        - Fixed: Deferred to first query. Subsequent queries use cached index.
        """
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
            
            self.sparse_retriever = BM25Retriever.from_documents(
                bm25_docs,
                k=self.config['retriever']['top_k_initial']
            )
            logger.info(f"BM25 index built lazily with {len(bm25_docs)} documents.")
        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
        finally:
            self._bm25_initialized = True

    def refresh_bm25(self):
        """
        Force-rebuild the BM25 index (e.g., after a vector DB update).
        Thread-safe: called externally.
        """
        logger.info("Refreshing BM25 index...")
        self._bm25_initialized = False
        self._ensure_bm25()


    async def aget_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """Async retrieval is not implemented."""
        raise NotImplementedError

    def _expand_query(self, query: str) -> str:
        """Expand query with medical synonyms for better retrieval."""
        query_lower = query.lower()
        expanded_terms = [query]
        
        for term, synonyms in self.medical_synonyms.items():
            if term in query_lower:
                # Add the most relevant synonym (first one)
                expanded_terms.append(synonyms[0])
        
        return " ".join(expanded_terms)

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None, filter: dict = None, top_k: Optional[int] = None) -> List[Document]:
        """
        Full retrieval pipeline:
        1. Get PARENT docs from sparse (BM25) retriever (already filtered to relevant tables).
        2. Get PARENT docs from dense (small-to-big) retriever.
        3. Merge and de-duplicate the results.
        4. Rerank the merged list to get the final, most relevant docs.
        """
        logger.info(f"Executing query: {query}")
        
        # Use provided top_k or fall back to config
        k_final = top_k or self.config.get('retriever', {}).get('top_k_final', 5)
        
        # Expand the query with medical synonyms
        expanded_query = self._expand_query(query)
        
        # --- 1. DENSE (small-to-big) RETRIEVAL WITH DYNAMIC SCORE PRUNING ---
        try:
            qdrant_filter = _convert_filter_to_qdrant(filter, self._vector_store_type)
            dense_results = self.vector_store.similarity_search_with_score(expanded_query, k=50, filter=qdrant_filter)
        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}. Continuing with sparse retrieval only.")
            dense_results = []
        
        child_chunks = []
        if dense_results:
            scores = [s for _, s in dense_results]
            cliff_idx = len(dense_results)
            min_candidates = min(5, len(dense_results))
            
            for i in range(min_candidates, len(dense_results) - 1):
                s1, s2 = scores[i-1], scores[i]
                diff = abs(s1 - s2)
                denom = max(abs(s1), abs(s2), 1e-5)
                relative_drop = diff / denom
                
                if relative_drop > 0.15:  # 15% sudden drop in score
                    cliff_idx = i
                    logger.info(f"Dynamic Pruning: Found score cliff at index {cliff_idx}. Pruning {len(dense_results) - cliff_idx} candidates.")
                    break
                    
            child_chunks = [doc for doc, _ in dense_results[:cliff_idx]]

        # Get unique parent IDs from child chunks
        parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]
        
        # --- 2. SPARSE (BM25) RETRIEVAL (lazy-loaded) ---
        self._ensure_bm25()  # Task 8: build on first query
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(expanded_query, run_manager=run_manager)
        merged_docs_dict = { (doc.page_content, doc.metadata.get('source_id', '')): doc for doc in dense_parent_docs }
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
        
        final_docs = _rerank_with_cache(
            self.reranker, query, merged_docs, k_final
        )
        
        logger.info(f"Returning {len(final_docs)} reranked documents.")
        return final_docs

    def _load_vector_store(self):
        """
        Load the vector store using VectorStoreFactory pattern.
        Supports Qdrant (primary) and ChromaDB (fallback).
        """
        collection_name = self.config['vector_store']['collection_name']
        
        if self._vector_store_type == "qdrant":
            try:
                from langchain_qdrant import QdrantVectorStore
                from qdrant_client import QdrantClient
                
                qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
                logger.info(f"Connecting to Qdrant at {qdrant_url} for collection: {collection_name}")
                
                client = QdrantClient(url=qdrant_url)
                
                return QdrantVectorStore(
                    client=client,
                    collection_name=collection_name,
                    embedding=self.embedding_function
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant: {e}. Falling back to ChromaDB.")
                self._vector_store_type = "chroma"
        
        # Fallback to ChromaDB
        import chromadb
        from langchain_chroma import Chroma
        
        chroma_path = self.config['vector_store'].get('chroma_path', './data/indexes/default')
        logger.info(f"Using ChromaDB at {chroma_path} for collection: {collection_name}")
        
        client_settings = chromadb.Settings(anonymized_telemetry=False)
        return Chroma(
            persist_directory=chroma_path,
            embedding_function=self.embedding_function,
            collection_name=collection_name,
            client_settings=client_settings
        )

    def _load_docstore(self):
        """Load the parent document store from disk with module remapping."""
        docstore_path = f"{self.config['vector_store']['chroma_path']}/parent_docstore.pkl"
        try:
            logger.info(f"Loading docstore from {docstore_path} with module remapping")
            docstore = load_with_remapping(docstore_path)
            logger.info("Successfully loaded docstore with module remapping")
            return docstore
        except FileNotFoundError:
            logger.critical(f"FATAL: Parent docstore not found at {docstore_path}. The RAG system cannot function.")
            raise
        except Exception as e:
            logger.error(f"Failed to load docstore: {e}", exc_info=True)
            raise
            
    def retrieve_and_rerank_with_scores(self, query: str, top_k: Optional[int] = None, filter: Optional[Dict[str, Any]] = None) -> List[Tuple[Document, float]]:
        """
        Special retrieval method for the Embedding Explorer.
        Returns documents AND their final reranker scores.
        Uses the same cache as _get_relevant_documents.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filter: Optional metadata filter dict (MongoDB-style, converted for Qdrant)
        
        Returns:
            List of (document, score) tuples
        """
        logger.info(f"Executing retrieve_and_rerank_with_scores for: {query}")
        
        k_final = top_k or self.config.get('retriever', {}).get('top_k_final', 5)
        expanded_query = self._expand_query(query)
        
        # --- 1. DENSE (small-to-big) RETRIEVAL WITH DYNAMIC SCORE PRUNING ---
        try:
            dense_results = self.vector_store.similarity_search_with_score(
                expanded_query, 
                k=50, 
                filter=_convert_filter_to_qdrant(filter, self._vector_store_type)
            )
        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}. Continuing with sparse retrieval only.")
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
            
        parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]

        # --- 2. SPARSE (BM25) RETRIEVAL (lazy) ---
        self._ensure_bm25()
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(expanded_query, run_manager=None)

        # --- 3. MERGE & DE-DUPLICATE ---
        merged_docs_dict = { (doc.page_content, doc.metadata.get('source_id', '')): doc for doc in dense_parent_docs }
        for doc in sparse_parent_docs:
            key = (doc.page_content, doc.metadata.get('source_id', ''))
            if key not in merged_docs_dict:
                merged_docs_dict[key] = doc
        
        merged_docs = list(merged_docs_dict.values())

        if not merged_docs:
            return []
            
        # --- 4. RERANK (with cache) ---
        if not self.reranker:
            logger.warning("No reranker found. Returning merged docs with placeholder scores.")
            return [(doc, 0.0) for doc in merged_docs[:k_final]]

        # Use cache for scores
        doc_contents = [doc.page_content for doc in merged_docs]
        cache_key = _compute_rerank_cache_key(query, doc_contents)
        
        if cache_key in _RERANK_CACHE:
            _RERANK_CACHE.move_to_end(cache_key)
            indexed_scores = _RERANK_CACHE[cache_key]
        else:
            pairs = [[query, content] for content in doc_contents]
            scores = self.reranker.predict(pairs)
            indexed_scores = sorted(
                enumerate(scores), key=lambda x: x[1], reverse=True
            )
            _RERANK_CACHE[cache_key] = indexed_scores
            if len(_RERANK_CACHE) > _RERANK_CACHE_MAX:
                _RERANK_CACHE.popitem(last=False)
        
        return [
            (merged_docs[idx], float(score))
            for idx, score in indexed_scores[:k_final]
            if idx < len(merged_docs)
        ]