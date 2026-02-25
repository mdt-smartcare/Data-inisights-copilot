"""
Vector store service for semantic search using ChromaDB.
Provides retrieval capabilities for the RAG pipeline.
"""
import sys
import os
import time
from pathlib import Path
from functools import lru_cache
from typing import List, Optional
import yaml

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import chromadb
from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder

from backend.services.embeddings import get_embedding_model
from backend.services.chroma_service import get_chroma_client
from backend.rag.retrieve import AdvancedRAGRetriever
from langchain_core.documents import Document

# Note: Tracing is handled by the parent LangChain callback handler
# to ensure all RAG operations are grouped under a single trace.

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


from backend.sqliteDb.db import get_db_service
import json

class VectorStoreService:
    """Service for managing vector store operations."""
    
    def __init__(self, agent_id: Optional[int] = None):
        """Initialize the vector store with advanced retrieval.
        
        Args:
            agent_id: Optional agent ID to load specific configuration.
        """
        self.agent_id = agent_id
        logger.info(f"Initializing vector store service (Agent: {agent_id if agent_id else 'Global'})")
        
        # Load RAG configuration - resolve path relative to backend directory
        config_path = Path(settings.rag_config_path)
        if not config_path.is_absolute():
            # If relative, resolve from backend directory
            backend_root = Path(__file__).parent.parent  # backend/services -> backend/
            # Remove leading './' if present
            config_rel_path = str(settings.rag_config_path).lstrip('./')
            config_path = (backend_root / config_rel_path).resolve()
        
        logger.info(f"Looking for RAG config at: {config_path}")
        
        if not config_path.exists():
            raise FileNotFoundError(f"RAG config not found at {config_path}")
        
        logger.info(f"Loading RAG config from {config_path}")
        
        with open(config_path, 'r') as f:
            self.rag_config = yaml.safe_load(f)
            
        # ------------------------------------------------------------------
        # OVERRIDE WITH DB CONFIG
        # ------------------------------------------------------------------
        try:
            db_service = get_db_service()
            active_config = db_service.get_active_config(agent_id=self.agent_id)
            
            if active_config:
                logger.info(f"Found active RAG config for agent {self.agent_id}. Applying overrides...")
                
                # Override Embedding Config
                if active_config.get('embedding_config'):
                    try:
                        emb_conf = json.loads(active_config['embedding_config'])
                        # Map frontend keys to backend config structure if needed
                        # Frontend sends: { model, chunkSize, chunkOverlap }
                        # Backend expects: 
                        # embedding: { model_name }
                        # chunking: { parent_splitter: { chunk_size, chunk_overlap }, ... }
                        
                        if 'model' in emb_conf and emb_conf['model']:
                            self.rag_config['embedding']['model_name'] = emb_conf['model']
                        
                        # Apply Vector DB Name override if present
                        if 'vectorDbName' in emb_conf and emb_conf['vectorDbName']:
                            vdb_name = emb_conf['vectorDbName']
                            # Update chroma path and collection name
                            # Path is relative to data/indexes/
                            backend_root = Path(__file__).parent.parent
                            new_chroma_path = (backend_root / "data" / "indexes" / vdb_name).resolve()
                            self.rag_config['vector_store']['chroma_path'] = str(new_chroma_path)
                            self.rag_config['vector_store']['collection_name'] = vdb_name
                            logger.info(f"Overrode vector store path to: {new_chroma_path}")
                            
                        logger.info(f"Applied embedding config overrides from DB: {emb_conf}")
                    except Exception as e:
                        logger.error(f"Failed to parse embedding_config from DB: {e}")

                # Override Chunking Config
                if active_config.get('chunking_config'):
                    try:
                        chunk_conf = json.loads(active_config['chunking_config'])
                        if 'chunking' not in self.rag_config: self.rag_config['chunking'] = {}
                        if 'parent_splitter' not in self.rag_config['chunking']: self.rag_config['chunking']['parent_splitter'] = {}
                        if 'child_splitter' not in self.rag_config['chunking']: self.rag_config['chunking']['child_splitter'] = {}
                        
                        if 'parentChunkSize' in chunk_conf:
                            self.rag_config['chunking']['parent_splitter']['chunk_size'] = int(chunk_conf['parentChunkSize'])
                        if 'parentChunkOverlap' in chunk_conf:
                            self.rag_config['chunking']['parent_splitter']['chunk_overlap'] = int(chunk_conf['parentChunkOverlap'])
                        if 'childChunkSize' in chunk_conf:
                            self.rag_config['chunking']['child_splitter']['chunk_size'] = int(chunk_conf['childChunkSize'])
                        if 'childChunkOverlap' in chunk_conf:
                            self.rag_config['chunking']['child_splitter']['chunk_overlap'] = int(chunk_conf['childChunkOverlap'])
                            
                        logger.info(f"Applied chunking config overrides from DB: {chunk_conf}")
                    except Exception as e:
                        logger.error(f"Failed to parse chunking_config from DB: {e}")

                # Override Retriever Config
                if active_config.get('retriever_config'):
                    try:
                        ret_conf = json.loads(active_config['retriever_config'])
                        # Frontend sends: { topKInitial, topKFinal, hybridWeights }
                        # Backend expects: retriever: { top_k_initial, top_k_final, hybrid_search_weights }
                        
                        if 'retriever' not in self.rag_config: self.rag_config['retriever'] = {}
                        
                        if 'topKInitial' in ret_conf:
                            self.rag_config['retriever']['top_k_initial'] = int(ret_conf['topKInitial'])
                        
                        if 'topKFinal' in ret_conf:
                            self.rag_config['retriever']['top_k_final'] = int(ret_conf['topKFinal'])
                            
                        if 'hybridWeights' in ret_conf:
                            self.rag_config['retriever']['hybrid_search_weights'] = ret_conf['hybridWeights']
                            
                        if 'rerankEnabled' in ret_conf:
                            self.rag_config['retriever']['rerank_enabled'] = bool(ret_conf['rerankEnabled'])
                            
                        if 'rerankerModel' in ret_conf:
                            self.rag_config['retriever']['reranker_model_name'] = str(ret_conf['rerankerModel'])
                            
                        logger.info(f"Applied retriever config overrides from DB: {ret_conf}")
                    except Exception as e:
                        logger.error(f"Failed to parse retriever_config from DB: {e}")
                        
        except Exception as e:
            logger.warning(f"Failed to load config overrides from DB: {e}. Using YAML defaults.")
        
        logger.info("Final RAG Config loaded successfully")
        
        # Initialize Embedding Function
        self.embedding_function = get_embedding_model()

        # Initialize Advanced RAG Retriever (handles Dense/Sparse/BM25)
        self.retriever = AdvancedRAGRetriever(config=self.rag_config)
        self.vector_store = self.retriever.vector_store # Expose underlying store if needed
        self.reranker = self.retriever.reranker

        logger.info("Vector store initialized successfully")
    
    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        """
        Perform semantic search on the vector store.
        
        Note: Tracing is handled by the parent LangChain callback handler
        to ensure all RAG operations are grouped under a single trace.
        
        Args:
            query: Search query text
            top_k: Number of results to return (defaults to settings)
        
        Returns:
            List of relevant documents
        """
        k = top_k or settings.rag_top_k
        logger.info(f"Searching vector store for query: '{query[:100]}...' (top_k={k})")
        
        try:
            start_time = time.time()
            
            # Use AdvancedRAGRetriever
            # Pass top_k down via config override briefly if needed
            original_k = self.retriever.config['retriever']['top_k_final']
            self.retriever.config['retriever']['top_k_final'] = k
            
            docs = self.retriever._get_relevant_documents(query)
            
            self.retriever.config['retriever']['top_k_final'] = original_k
            
            duration = time.time() - start_time
            logger.info(f"Retrieved {len(docs)} documents from AdvancedRAGRetriever in {duration:.2f} seconds")
                
            return docs
            
        except Exception as e:
            logger.error(f"Vector store search failed: {e}", exc_info=True)
            raise
    
    def search_with_scores(self, query: str, top_k: Optional[int] = None) -> List[tuple]:
        """
        Perform semantic search with relevance scores.
        
        Note: Tracing is handled by the parent LangChain callback handler
        to ensure all RAG operations are grouped under a single trace.
        
        Args:
            query: Search query text
            top_k: Number of results to return
        
        Returns:
            List of (document, score) tuples
        """
        k = top_k or settings.rag_top_k
        logger.info(f"Searching with scores for: '{query[:100]}...'")
        
        try:
            start_time = time.time()

            original_k = self.retriever.config['retriever']['top_k_final']
            self.retriever.config['retriever']['top_k_final'] = k
            
            # Delegate entirely to the advanced retriever
            results = self.retriever.retrieve_and_rerank_with_scores(query)
            
            self.retriever.config['retriever']['top_k_final'] = original_k

            duration = time.time() - start_time
            logger.info(f"Retrieved {len(results)} documents with scores in {duration:.2f} seconds")
                
            return results
                
        except Exception as e:
            logger.error(f"Vector store search with scores failed: {e}", exc_info=True)
            raise
    
    def health_check(self) -> bool:
        """
        Check if vector store is accessible.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Perform a simple test query
            test_results = self.search("test health check", top_k=1)
            return len(test_results) >= 0  # Even 0 results means DB is accessible
        except Exception as e:
            logger.error(f"Vector store health check failed: {e}")
            return False


@lru_cache()
def get_vector_store(agent_id: Optional[int] = None) -> VectorStoreService:
    """
    Get cached vector store service instance.
    Cached by agent_id to support multi-tenant configurations while avoiding redundant loading.
    
    Returns:
        Context-aware vector store service
    """
    return VectorStoreService(agent_id=agent_id)
