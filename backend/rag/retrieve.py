from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
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

# RELEVANT_TABLES removed for generic white-labeling
# The system now indexes all documents found in the docstore.


class AdvancedRAGRetriever(BaseRetriever, BaseModel):
    config: Dict = Field(default_factory=dict)
    embedding_function: Any = Field(default=None)
    vector_store: Any = Field(default=None)
    docstore: Any = Field(default=None)
    child_splitter: Any = Field(default=None)
    child_chunk_retriever: Any = Field(default=None) # Renamed for clarity
    sparse_retriever: Any = Field(default=None)
    reranker: Any = Field(default=None) 
    
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
        """Initialize both dense and sparse retrievers."""
        
        # 1. Dense Retriever (for CHILD chunks from vector store)
        self.child_chunk_retriever = self.vector_store.as_retriever(
            # Widen the net to find more child chunks
            search_kwargs={"k": 50} 
        )

        # 2. Sparse Retriever (for PARENT documents)
        all_parent_doc_keys = list(self.docstore.yield_keys())
        logger.info(f"Loading {len(all_parent_doc_keys)} parent documents for BM25...")
        
        parent_documents = list(self.docstore.mget(all_parent_doc_keys))
        parent_documents = [doc for doc in parent_documents if doc is not None] # Clean up
        
        # Filter documents for BM25
        # For Generic Mode: We invoke all documents, or filtering should be injected via config
        bm25_docs = parent_documents
        logger.info(f"Filtered to {len(bm25_docs)} documents from relevant tables for BM25 index.")
        
        if not bm25_docs:
            logger.error("No relevant parent documents found for BM25. Sparse retriever will not work.")
            self.sparse_retriever = None 
            return

        self.sparse_retriever = BM25Retriever.from_documents(
            bm25_docs,  # Use the filtered list
            k=self.config['retriever']['top_k_initial'] # Use config K
        )
        logger.info("BM25Retriever initialized on relevant tables.")


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
            # Find child chunks
            child_chunks = self.child_chunk_retriever._get_relevant_documents(expanded_query, run_manager=run_manager)
        finally:
            # Restore original kwargs
            self.child_chunk_retriever.search_kwargs = original_kwargs

        # Get unique parent IDs from child chunks
        parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
        # Retrieve the full parent documents
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None] # Clean up
        
        # --- 2. SPARSE (BM25) RETRIEVAL ---
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(expanded_query, run_manager=run_manager)
        
        # --- 3. MERGE & DE-DUPLICATE (both lists now contain PARENT docs) ---
        merged_docs_dict = { (doc.page_content, doc.metadata.get('source_id', '')): doc for doc in dense_parent_docs }
        for doc in sparse_parent_docs:
            key = (doc.page_content, doc.metadata.get('source_id', ''))
            if key not in merged_docs_dict:
                merged_docs_dict[key] = doc
        
        merged_docs = list(merged_docs_dict.values())
        
        # --- 4. RERANK ---
        if not self.reranker or not merged_docs:
            logger.info(f"Skipping reranking. Returning {len(merged_docs)} merged docs.")
            # Return k_final from the *merged* list if no reranker
            return merged_docs[:k_final]
        
        logger.info(f"Reranking {len(merged_docs)} documents for query: '{query}'")
        
        pairs = [[query, doc.page_content] for doc in merged_docs]
        scores = self.reranker.predict(pairs)
        
        doc_score_pairs = list(zip(merged_docs, scores))
        sorted_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)
        
        final_docs = [doc for doc, score in sorted_pairs[:k_final]]
        
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
        """
        logger.info(f"Executing retrieve_and_rerank_with_scores for: {query}")
        
        # Use provided top_k or fall back to config
        k_final = top_k or self.config.get('retriever', {}).get('top_k_final', 5)
        
        # Expand the query with medical synonyms
        expanded_query = self._expand_query(query)
        
        # --- 1. DENSE (small-to-big) RETRIEVAL ---
        child_chunks = self.child_chunk_retriever._get_relevant_documents(expanded_query, run_manager=None)
        parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]

        # --- 2. SPARSE (BM25) RETRIEVAL ---
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
            
        # --- 4. RERANK ---
        if not self.reranker:
            logger.warning("No reranker found. Returning merged docs with placeholder scores.")
            return [(doc, 0.0) for doc in merged_docs[:k_final]]

        pairs = [[query, doc.page_content] for doc in merged_docs]
        scores = self.reranker.predict(pairs)
        
        doc_score_pairs = list(zip(merged_docs, scores))
        sorted_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)
        
        return sorted_pairs[:k_final]