from typing import List, Dict, Any
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

logger = logging.getLogger(__name__)
load_dotenv()

class AdvancedRAGRetriever(BaseRetriever, BaseModel):
    config: Dict = Field(default_factory=dict)
    embedding_function: Any = Field(default=None)
    vector_store: Any = Field(default=None)
    docstore: Any = Field(default=None)
    child_splitter: Any = Field(default=None)
    dense_retriever: Any = Field(default=None)
    sparse_retriever: Any = Field(default=None)

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
        logger.info("Advanced RAG Retriever initialized successfully.")

    def _setup_retrievers(self):
        """Initialize both dense and sparse retrievers."""
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
        doc_scores = {}
        
        # Process dense retrieval results
        for i, doc in enumerate(dense_docs):
            score = weights[0] * (1.0 - (i / len(dense_docs)))
            doc_scores[doc.page_content] = {"doc": doc, "score": score}
        
        # Process sparse retrieval results
        for i, doc in enumerate(sparse_docs):
            score = weights[1] * (1.0 - (i / len(sparse_docs)))
            if doc.page_content in doc_scores:
                doc_scores[doc.page_content]["score"] += score
            else:
                doc_scores[doc.page_content] = {"doc": doc, "score": score}
        
        # Sort by combined scores
        sorted_results = sorted(doc_scores.values(), key=lambda x: x["score"], reverse=True)
        return [item["doc"] for item in sorted_results[:self.config['retriever']['top_k_initial']]]

    async def aget_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """Async retrieval is not implemented."""
        raise NotImplementedError

    def _get_relevant_documents(self, query: str, *, run_manager: Any = None) -> List[Document]:
        """Required implementation for BaseRetriever."""
        logger.info(f"Executing query: {query}")
        
        # Get results from both retrievers
        dense_docs = self.dense_retriever._get_relevant_documents(query, run_manager=run_manager)
        sparse_docs = self.sparse_retriever._get_relevant_documents(query, run_manager=run_manager)
        
        # Combine results using weights from config
        weights = self.config['retriever']['hybrid_search_weights']
        return self._merge_results(dense_docs, sparse_docs, weights)

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
        with open(docstore_path, "rb") as f:
            return pickle.load(f)