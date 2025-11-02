import logging
import pickle
import os
from dotenv import load_dotenv
from typing import List, Dict
from langchain_core.documents import Document
from langchain_community.retrievers.bm25 import BM25Retriever
from langchain_chroma import Chroma
from src.pipeline.embed import LocalHuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import yaml
import chromadb

logger = logging.getLogger(__name__)
load_dotenv()

class AdvancedRAGRetriever:
    def __init__(self, config: Dict):
        self.config = config
        self.embedding_function = LocalHuggingFaceEmbeddings(model_id=config['embedding']['model_path'])
        
        self.vector_store = self._load_vector_store()
        self.docstore = self._load_docstore()
        
        # Create a child splitter instance
        child_splitter_config = self.config['chunking']['child_splitter']
        self.child_splitter = RecursiveCharacterTextSplitter(**child_splitter_config)
        
        # Initialize retrievers
        self._setup_retrievers()
        logger.info("Advanced RAG Retriever initialized successfully.")

    def _setup_retrievers(self):
        # 1. Dense Retriever (Vector Store)
        self.dense_retriever = self.vector_store.as_retriever(
            search_kwargs={"k": self.config['retriever']['top_k_initial']}
        )

        # 2. Sparse Retriever (BM25)
        parent_documents = list(self.docstore.mget(list(self.docstore.yield_keys())))
        self.sparse_retriever = BM25Retriever.from_documents(
            parent_documents,
            k=self.config['retriever']['top_k_initial']
        )

    def _merge_results(self, dense_docs: List[Document], sparse_docs: List[Document], weights: List[float]) -> List[Document]:
        """Merge results from dense and sparse retrievers with weights."""
        # Create a dict to store unique documents with their scores
        doc_scores = {}
        
        # Process dense retrieval results
        for i, doc in enumerate(dense_docs):
            score = weights[0] * (1.0 - (i / len(dense_docs)))
            doc_scores[doc.page_content] = {"doc": doc, "score": score}
        
        # Process sparse retrieval results and combine scores
        for i, doc in enumerate(sparse_docs):
            score = weights[1] * (1.0 - (i / len(sparse_docs)))
            if doc.page_content in doc_scores:
                doc_scores[doc.page_content]["score"] += score
            else:
                doc_scores[doc.page_content] = {"doc": doc, "score": score}
        
        # Sort by combined scores and return documents
        sorted_results = sorted(doc_scores.values(), key=lambda x: x["score"], reverse=True)
        return [item["doc"] for item in sorted_results[:self.config['retriever']['top_k_initial']]]

    def query(self, question: str) -> List[Document]:
        logger.info(f"Executing query: {question}")
        
        # Get results from both retrievers
        dense_docs = self.dense_retriever.get_relevant_documents(question)
        sparse_docs = self.sparse_retriever.get_relevant_documents(question)
        
        # Combine results using weights from config
        weights = self.config['retriever']['hybrid_search_weights']
        return self._merge_results(dense_docs, sparse_docs, weights)

    def _load_vector_store(self):
        client_settings = chromadb.Settings(anonymized_telemetry=False)
        return Chroma(
            persist_directory=self.config['vector_store']['chroma_path'],
            embedding_function=self.embedding_function,
            collection_name=self.config['vector_store']['collection_name'],
            client_settings=client_settings
        )

    def _load_docstore(self):
        docstore_path = f"{self.config['vector_store']['chroma_path']}/parent_docstore.pkl"
        with open(docstore_path, "rb") as f:
            return pickle.load(f)