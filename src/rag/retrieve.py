from typing import List, Dict, Any, Tuple
from langchain_core.documents import Document
from langchain_community.retrievers.bm25 import BM25Retriever
from langchain_chroma import Chroma
from src.pipeline.embed import LocalHuggingFaceEmbeddings
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

# --- THIS IS THE FIX for the RAG EXPLORER ---
# We remove "prescription" so the sparse (keyword) search
# doesn't find irrelevant medication names.
RELEVANT_TABLES = {
    "patient_tracker",
    "patient",
    "bp_log",
    "glucose_log",
    "patient_diagnosis",
    "patient_comorbidity",
    "patient_complication",
    # "prescription", # <-- REMOVED
    "call_register",
    "patient_vitals", # From notebook
    "patient_conditions", # From notebook
}
# --- END OF FIX ---


class AdvancedRAGRetriever(BaseRetriever, BaseModel):
    config: Dict = Field(default_factory=dict)
    embedding_function: Any = Field(default=None)
    vector_store: Any = Field(default=None)
    docstore: Any = Field(default=None)
    child_splitter: Any = Field(default=None)
    child_chunk_retriever: Any = Field(default=None) # Renamed for clarity
    sparse_retriever: Any = Field(default=None)
    reranker: Any = Field(default=None) 

    def __init__(self, config: Dict, **kwargs):
        """Initialize the hybrid retriever with both dense and sparse components."""
        super().__init__(**kwargs)
        self.config = config
        self.embedding_function = LocalHuggingFaceEmbeddings(model_id=config['embedding']['model_path'])
        
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
        bm25_docs = [
            doc for doc in parent_documents 
            if doc.metadata.get("source_table") in RELEVANT_TABLES
        ]
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

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """
        Full retrieval pipeline:
        1. Get PARENT docs from sparse (BM25) retriever (already filtered to relevant tables).
        2. Get PARENT docs from dense (small-to-big) retriever.
        3. Merge and de-duplicate the results.
        4. Rerank the merged list to get the final, most relevant docs.
        """
        logger.info(f"Executing query: {query}")
        
        # --- 1. DENSE (small-to-big) RETRIEVAL ---
        # Find child chunks
        child_chunks = self.child_chunk_retriever._get_relevant_documents(query, run_manager=run_manager)
        # Get unique parent IDs from child chunks
        parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
        # Retrieve the full parent documents
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None] # Clean up
        
        # --- 2. SPARSE (BM25) RETRIEVAL ---
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(query, run_manager=run_manager)
        
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
            # Return top_k_final from the *merged* list if no reranker
            return merged_docs[:self.config['retriever']['top_k_final']]
        
        logger.info(f"Reranking {len(merged_docs)} documents for query: '{query}'")
        
        pairs = [[query, doc.page_content] for doc in merged_docs]
        scores = self.reranker.predict(pairs)
        
        doc_score_pairs = list(zip(merged_docs, scores))
        sorted_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)
        
        final_docs = [doc for doc, score in sorted_pairs[:self.config['retriever']['top_k_final']]]
        
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
        """Load the parent document store from disk."""
        docstore_path = f"{self.config['vector_store']['chroma_path']}/parent_docstore.pkl"
        try:
            with open(docstore_path, "rb") as f:
                return pickle.load(f)
        except FileNotFoundError:
            logger.critical(f"FATAL: Parent docstore not found at {docstore_path}. The RAG system cannot function.")
            raise
            
    def retrieve_and_rerank_with_scores(self, query: str) -> List[Tuple[Document, float]]:
        """
        Special retrieval method for the Embedding Explorer.
        Returns documents AND their final reranker scores.
        """
        logger.info(f"Executing retrieve_and_rerank_with_scores for: {query}")
        
        # --- 1. DENSE (small-to-big) RETRIEVAL ---
        child_chunks = self.child_chunk_retriever._get_relevant_documents(query, run_manager=None)
        parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
        dense_parent_docs = self.docstore.mget(parent_ids)
        dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]

        # --- 2. SPARSE (BM25) RETRIEVAL ---
        sparse_parent_docs = []
        if self.sparse_retriever:
            sparse_parent_docs = self.sparse_retriever._get_relevant_documents(query, run_manager=None)

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
            return [(doc, 0.0) for doc in merged_docs[:self.config['retriever']['top_k_final']]]

        pairs = [[query, doc.page_content] for doc in merged_docs]
        scores = self.reranker.predict(pairs)
        
        doc_score_pairs = list(zip(merged_docs, scores))
        sorted_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)
        
        return sorted_pairs[:self.config['retriever']['top_k_final']]