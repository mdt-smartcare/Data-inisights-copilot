from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
from collections import OrderedDict
import hashlib
from concurrent.futures import ThreadPoolExecutor
from langchain_core.documents import Document
from langchain_community.retrievers.bm25 import BM25Retriever
from langchain_chroma import Chroma
from backend.services.embeddings import get_embedding_model
from backend.rag.pickle_utils import load_with_remapping
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, BaseModel
import logging
import pickle
from dotenv import load_dotenv
from sentence_transformers import CrossEncoder 

logger = logging.getLogger(__name__)
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

# RELEVANT_TABLES removed for generic white-labeling
# The system now indexes all documents found in the docstore.


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
    
    # Synonyms now sourced from configuration or empty by default
    medical_synonyms: Dict[str, List[str]] = Field(default_factory=dict)

    def __init__(self, config: Dict, **kwargs):
        """Initialize the hybrid retriever with both dense and sparse components."""
        super().__init__(**kwargs)
        self.config = config
        
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
        chroma_path = self.config['vector_store']['chroma_path']
        if chroma_path.startswith('./'):
            resolved_path = (backend_root / chroma_path.lstrip('./')).resolve()
            self.config['vector_store']['chroma_path'] = str(resolved_path)
            logger.info(f"Resolved chroma_path to: {resolved_path}")
        
        # Resolve model_path
        model_path = self.config['embedding']['model_path']
        if model_path.startswith('./'):
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
        
        # Save original search kwargs to restore later
        original_kwargs = self.child_chunk_retriever.search_kwargs.copy()
        
        if filter:
            # We must pass the Chromadb filter into the dense retriever search_kwargs
            self.child_chunk_retriever.search_kwargs["filter"] = filter
            logger.info(f"Applied metadata filter to dense retrieval: {filter}")

        try:
            # --- 1. DENSE (small-to-big) RETRIEVAL ---
            child_chunks = self.child_chunk_retriever._get_relevant_documents(expanded_query, run_manager=run_manager)
        finally:
            self.child_chunk_retriever.search_kwargs = original_kwargs

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
        """Load the vector store from disk."""
        client_settings = chromadb.Settings(anonymized_telemetry=False)
        return Chroma(
            persist_directory=self.config['vector_store']['chroma_path'],
            embedding_function=self.embedding_function,
            collection_name=self.config['vector_store']['collection_name'],
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
            
    def retrieve_and_rerank_with_scores(self, query: str, top_k: Optional[int] = None) -> List[Tuple[Document, float]]:
        """
        Special retrieval method for the Embedding Explorer.
        Returns documents AND their final reranker scores.
        Uses the same cache as _get_relevant_documents.
        """
        logger.info(f"Executing retrieve_and_rerank_with_scores for: {query}")
        
        k_final = top_k or self.config.get('retriever', {}).get('top_k_final', 5)
        expanded_query = self._expand_query(query)
        
        # --- 1. DENSE (small-to-big) RETRIEVAL ---
        child_chunks = self.child_chunk_retriever._get_relevant_documents(expanded_query, run_manager=None)
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