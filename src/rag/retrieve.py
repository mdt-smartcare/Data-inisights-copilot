import logging
import pickle
from typing import List, Dict, Any, Tuple
from langchain_core.documents import Document
from langchain_community.retrievers.bm25 import BM25Retriever
from langchain_chroma import Chroma
from src.pipeline.embed import LocalHuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, BaseModel
from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

# <-- NEW IMPORTS -->
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.output_parsers.json import JsonOutputParser
# <-- END NEW IMPORTS -->

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

# <-- NEW: RAG-FUSION PROMPT (STEP 1) -->
QUERY_GEN_TEMPLATE = """
You are a helpful assistant that generates multiple search queries based on a single input query.
Generate 4 search queries related to: {question}
Output (4 queries):
1.
2.
3.
4.
"""
QUERY_GEN_PROMPT = ChatPromptTemplate.from_template(QUERY_GEN_TEMPLATE)

# <-- NEW: CRAG GRADING PROMPT (STEP 2) -->
GRADING_TEMPLATE = """
You are a relevance grader. Given a user query and a retrieved document, you must determine if the document is relevant to the query.
Your response must be a JSON object with two keys:
1. "relevance": a string, either "yes" or "no".
2. "reason": a brief justification for your decision.

Query: {query}

Document:
---
{document}
---

JSON Response:
"""
GRADING_PROMPT = ChatPromptTemplate.from_template(GRADING_TEMPLATE)


class AdvancedRAGRetriever(BaseRetriever, BaseModel):
    config: Dict = Field(default_factory=dict)
    embedding_function: Any = Field(default=None)
    vector_store: Any = Field(default=None)
    docstore: Any = Field(default=None)
    child_splitter: Any = Field(default=None)
    child_chunk_retriever: Any = Field(default=None) # Renamed for clarity
    sparse_retriever: Any = Field(default=None)
    reranker: Any = Field(default=None) 
    
    # <-- NEW: LLM chains for advanced RAG steps -->
    query_gen_llm: Any = Field(default=None)
    grading_llm: Any = Field(default=None)

    def __init__(self, config: Dict, **kwargs):
        """Initialize the hybrid retriever with all components."""
        super().__init__(**kwargs)
        self.config = config
        self.embedding_function = LocalHuggingFaceEmbeddings(model_id=config['embedding']['model_path'])
        
        self.vector_store = self._load_vector_store()
        self.docstore = self._load_docstore()
        
        # Create a child splitter instance
        child_splitter_config = self.config['chunking']['child_splitter']
        self.child_splitter = RecursiveCharacterTextSplitter(**child_splitter_config)
        
        # <-- NEW: Initialize LLM chains -->
        # 1. RAG-Fusion query generator
        query_llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)
        self.query_gen_llm = QUERY_GEN_PROMPT | query_llm | StrOutputParser()
        
        # 2. CRAG document grader
        # Use a fast, modern model that's good at JSON
        grading_model = ChatOpenAI(model_name="gpt-4o-mini", temperature=0).with_structured_output(JsonOutputParser)
        self.grading_llm = GRADING_PROMPT | grading_model
        # <-- END NEW -->
        
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
            bm25_docs,
            k=self.config['retriever']['top_k_initial']
        )
        logger.info("BM25Retriever initialized on relevant tables.")

    # <-- NEW: RAG-FUSION (STEP 1) METHODS -->
    def _generate_queries(self, query: str) -> List[str]:
        """Generates multiple queries from the original query."""
        logger.info(f"Generating expanded queries for: {query}")
        try:
            response = self.query_gen_llm.invoke({"question": query})
            queries = [q.strip() for q in response.split('\n') if q.strip() and ". " in q]
            queries = [q.split('. ', 1)[1] for q in queries if len(q.split('. ', 1)) > 1]
            if not queries:
                 logger.warning("Query generation failed to produce valid queries.")
                 return [query]
            queries.append(query) # Always include the original query
            logger.info(f"Generated {len(queries)} unique queries.")
            return list(set(queries)) # Return unique queries
        except Exception as e:
            logger.error(f"Failed to generate queries: {e}")
            return [query] # Fallback to original query

    def _reciprocal_rank_fusion(self, results_map: Dict[str, List[Document]], k=60) -> List[Document]:
        """Fuses ranks from multiple query results."""
        fused_scores = {}
        
        for query, docs in results_map.items():
            for rank, doc in enumerate(docs):
                # Use a stable key for each document
                doc_key = (doc.metadata.get('source_table'), doc.metadata.get('source_id', doc.page_content))
                if doc_key not in fused_scores:
                    fused_scores[doc_key] = {'doc': doc, 'score': 0.0}
                fused_scores[doc_key]['score'] += 1.0 / (rank + k)
                
        reranked_results = sorted(fused_scores.values(), key=lambda x: x['score'], reverse=True)
        logger.info(f"Fused {len(reranked_results)} documents.")
        return [item['doc'] for item in reranked_results]
    # <-- END RAG-FUSION METHODS -->

    # <-- NEW: CRAG (STEP 2) METHOD -->
    def _grade_documents(self, query: str, documents: List[Document]) -> List[Document]:
        """Grades documents for relevance and filters out irrelevant ones."""
        logger.info(f"Grading {len(documents)} documents for relevance...")
        relevant_docs = []
        for doc in documents:
            try:
                result = self.grading_llm.invoke({"query": query, "document": doc.page_content})
                if result and result.get("relevance") == "yes":
                    relevant_docs.append(doc)
            except Exception as e:
                logger.warning(f"Failed to grade document (ID: {doc.metadata.get('source_id')}): {e}. Assuming irrelevant.")
        
        logger.info(f"Found {len(relevant_docs)} relevant documents after grading.")
        return relevant_docs
    # <-- END CRAG METHOD -->

    async def aget_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """Async retrieval is not implemented."""
        raise NotImplementedError

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """
        Full retrieval pipeline with RAG-Fusion, CRAG, and Reranking:
        1. Generate multiple queries from the original query (RAG-Fusion).
        2. For each query, get docs from sparse (BM25) and dense (vector) retrievers.
        3. Fuse all results using Reciprocal Rank Fusion (RRF).
        4. Grade the fused documents for relevance (CRAG).
        5. Rerank the final *relevant* docs to get the most relevant ones.
        """
        logger.info(f"Executing full advanced retrieval for: {query}")
        
        # --- 1. RAG-FUSION: GENERATE QUERIES ---
        queries = self._generate_queries(query)
        
        all_retrieved_docs_map = {} # To store results for RRF

        for q in queries:
            # --- 2. RETRIEVAL (for each query) ---
            child_chunks = self.child_chunk_retriever._get_relevant_documents(q, run_manager=run_manager)
            parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
            dense_parent_docs = self.docstore.mget(parent_ids)
            dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]
            
            sparse_parent_docs = []
            if self.sparse_retriever:
                sparse_parent_docs = self.sparse_retriever._get_relevant_documents(q, run_manager=run_manager)
            
            # Merge & De-duplicate (for this single query)
            merged_docs_dict = { (doc.page_content, doc.metadata.get('source_id', '')): doc for doc in dense_parent_docs }
            for doc in sparse_parent_docs:
                key = (doc.page_content, doc.metadata.get('source_id', ''))
                if key not in merged_docs_dict:
                    merged_docs_dict[key] = doc
            
            all_retrieved_docs_map[q] = list(merged_docs_dict.values())
        
        # --- 3. RAG-FUSION: FUSE ALL RESULTS ---
        fused_docs = self._reciprocal_rank_fusion(all_retrieved_docs_map)
        
        # --- 4. CRAG: GRADE DOCUMENTS ---
        graded_docs = self._grade_documents(query, fused_docs)

        if not graded_docs:
            logger.warning("No relevant documents found after grading.")
            return []

        # --- 5. RERANK (Final Step) ---
        if not self.reranker:
            logger.info(f"Skipping reranking. Returning {len(graded_docs)} graded docs.")
            return graded_docs[:self.config['retriever']['top_k_final']]
        
        logger.info(f"Reranking {len(graded_docs)} graded documents for query: '{query}'")
        
        # Rerank based on the *original* query
        pairs = [[query, doc.page_content] for doc in graded_docs]
        scores = self.reranker.predict(pairs)
        
        doc_score_pairs = list(zip(graded_docs, scores))
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
        Applies the full RAG-Fusion + CRAG + Rerank pipeline.
        """
        logger.info(f"Executing retrieve_and_rerank_with_scores for: {query}")
        
        # --- 1. RAG-FUSION: GENERATE QUERIES ---
        queries = self._generate_queries(query)
        all_retrieved_docs_map = {}
        
        for q in queries:
            # --- 2. RETRIEVAL ---
            child_chunks = self.child_chunk_retriever._get_relevant_documents(q, run_manager=None)
            parent_ids = list(set([doc.metadata['doc_id'] for doc in child_chunks if 'doc_id' in doc.metadata]))
            dense_parent_docs = self.docstore.mget(parent_ids)
            dense_parent_docs = [doc for doc in dense_parent_docs if doc is not None]

            sparse_parent_docs = []
            if self.sparse_retriever:
                sparse_parent_docs = self.sparse_retriever._get_relevant_documents(q, run_manager=None)

            # --- 3. MERGE ---
            merged_docs_dict = { (doc.page_content, doc.metadata.get('source_id', '')): doc for doc in dense_parent_docs }
            for doc in sparse_parent_docs:
                key = (doc.page_content, doc.metadata.get('source_id', ''))
                if key not in merged_docs_dict:
                    merged_docs_dict[key] = doc
            all_retrieved_docs_map[q] = list(merged_docs_dict.values())
        
        # --- 4. RAG-FUSION: FUSE ALL RESULTS ---
        fused_docs = self._reciprocal_rank_fusion(all_retrieved_docs_map)

        # --- 5. CRAG: GRADE DOCUMENTS ---
        graded_docs = self._grade_documents(query, fused_docs)
        
        if not graded_docs:
            return []
            
        # --- 6. RERANK ---
        if not self.reranker:
            logger.warning("No reranker found. Returning graded docs with placeholder scores.")
            return [(doc, 0.0) for doc in graded_docs[:self.config['retriever']['top_k_final']]]

        pairs = [[query, doc.page_content] for doc in graded_docs]
        scores = self.reranker.predict(pairs)
        
        doc_score_pairs = list(zip(graded_docs, scores))
        sorted_pairs = sorted(doc_score_pairs, key=lambda x: x[1], reverse=True)
        
        return sorted_pairs[:self.config['retriever']['top_k_final']]