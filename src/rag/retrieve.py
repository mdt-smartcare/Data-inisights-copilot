import logging
import pickle
import os
from dotenv import load_dotenv
from typing import List, Dict
from langchain.docstore.document import Document
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain.retrievers.parent_document_retriever import ParentDocumentRetriever
from langchain_community.vectorstores import Chroma

# --- Reranker imports REMOVED to fix the error ---

from src.pipeline.embed import LocalHuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
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
        
        # Create a child splitter instance (this fixes the other error)
        child_splitter_config = self.config['chunking']['child_splitter']
        child_splitter = RecursiveCharacterTextSplitter(**child_splitter_config)
        
        # 1. Initialize ParentDocumentRetriever
        parent_retriever = ParentDocumentRetriever(
            vectorstore=self.vector_store,
            docstore=self.docstore,
            child_splitter=child_splitter,
        )

        # 2. Sparse Retriever (BM25)
        parent_documents = list(self.docstore.mget(list(self.docstore.yield_keys())))
        self.sparse_retriever = BM25Retriever.from_documents(parent_documents)
        self.sparse_retriever.k = config['retriever']['top_k_initial']

        # 3. Dense Retriever
        self.dense_retriever = parent_retriever
        self.dense_retriever.search_kwargs = {'k': config['retriever']['top_k_initial']}

        # 4. Ensemble Retriever (Hybrid Search)
        # This is now our final retriever
        self.final_retriever = EnsembleRetriever(
            retrievers=[self.sparse_retriever, self.dense_retriever],
            weights=config['retriever']['hybrid_search_weights']
        )
        
        logger.info("Advanced RAG Retriever (Hybrid Search Only) initialized successfully.")

    def _load_vector_store(self):
        # Disable telemetry to fix the log errors
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

    def query(self, question: str) -> List[Document]:
        logger.info(f"Executing advanced query: {question}")
        # Use 'invoke' which is the standard for langchain 0.2.x
        return self.final_retriever.invoke(question)