"""
Vector store service for semantic search using ChromaDB.
Provides retrieval capabilities for the RAG pipeline.
"""
import sys
import time
import json
from pathlib import Path
from functools import lru_cache
from typing import List, Optional, Dict, Any

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.embeddings import get_embedding_model
from backend.rag.retrieve import AdvancedRAGRetriever
from langchain_core.documents import Document

# Note: Tracing is handled by the parent LangChain callback handler
# to ensure all RAG operations are grouped under a single trace.

from backend.config import (
    get_settings, get_rag_settings, get_embedding_settings, 
    get_chunking_settings, get_vector_store_settings
)
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service

settings = get_settings()
logger = get_logger(__name__)


class VectorStoreService:
    """Service for managing vector store operations."""
    
    def __init__(self, agent_id: Optional[int] = None):
        """Initialize the vector store with advanced retrieval.
        
        Args:
            agent_id: Optional agent ID to load specific configuration.
        """
        self.agent_id = agent_id
        logger.info(f"Initializing vector store service (Agent: {agent_id if agent_id else 'Global'})")
        
        # Build RAG config from database system_settings (primary source)
        self.rag_config = self._build_config_from_db()
        
        # Override with agent-specific config if available
        self._apply_agent_overrides()
        
        logger.info("Final RAG Config loaded successfully")
        
        # Initialize Embedding Function
        self.embedding_function = get_embedding_model()

        # Initialize Advanced RAG Retriever (handles Dense/Sparse/BM25)
        self.retriever = AdvancedRAGRetriever(config=self.rag_config)
        self.vector_store = self.retriever.vector_store # Expose underlying store if needed
        self.reranker = self.retriever.reranker

        logger.info("Vector store initialized successfully")
    
    def _build_config_from_db(self) -> Dict[str, Any]:
        """Build RAG configuration from database system_settings."""
        # Get settings from database (with fallback defaults)
        embedding_settings = get_embedding_settings()
        rag_settings = get_rag_settings()
        chunking_settings = get_chunking_settings()
        vector_store_settings = get_vector_store_settings()
        
        # Build config structure expected by AdvancedRAGRetriever
        backend_root = Path(__file__).parent.parent
        default_collection = vector_store_settings.get('default_collection', 'default_collection')
        
        config = {
            'embedding': {
                'model_name': embedding_settings.get('model_name', 'BAAI/bge-m3'),
                'model_path': embedding_settings.get('model_path', './models/bge-m3'),
                'batch_size': embedding_settings.get('batch_size', 128),
            },
            'chunking': {
                'parent_splitter': {
                    'chunk_size': chunking_settings.get('parent_chunk_size', 800),
                    'chunk_overlap': chunking_settings.get('parent_chunk_overlap', 150),
                },
                'child_splitter': {
                    'chunk_size': chunking_settings.get('child_chunk_size', 200),
                    'chunk_overlap': chunking_settings.get('child_chunk_overlap', 50),
                },
            },
            'vector_store': {
                'type': vector_store_settings.get('type', 'chroma'),
                'chroma_path': str((backend_root / "data" / "indexes" / default_collection).resolve()),
                'collection_name': default_collection,
            },
            'retriever': {
                'top_k_initial': rag_settings.get('top_k_initial', 50),
                'top_k_final': rag_settings.get('top_k_final', 10),
                'hybrid_search_weights': rag_settings.get('hybrid_weights', [0.75, 0.25]),
                'rerank_enabled': rag_settings.get('rerank_enabled', True),
                'reranker_model_name': rag_settings.get('reranker_model', 'BAAI/bge-reranker-base'),
            },
            'text_processing': {
                'min_chunk_length': chunking_settings.get('min_chunk_length', 50),
            },
        }
        
        logger.info(f"Built RAG config from system_settings: embedding={embedding_settings.get('model_name')}, "
                   f"top_k={rag_settings.get('top_k_final')}, collection={default_collection}")
        
        return config
    
    def _apply_agent_overrides(self):
        """Apply agent-specific configuration overrides from rag_configurations table."""
        try:
            db_service = get_db_service()
            active_config = db_service.get_active_config(agent_id=self.agent_id)
            
            if not active_config:
                logger.info("No agent-specific config found, using system_settings defaults")
                return
                
            logger.info(f"Found active RAG config for agent {self.agent_id}. Applying overrides...")
            
            # Override Embedding Config
            if active_config.get('embedding_config'):
                try:
                    emb_conf = json.loads(active_config['embedding_config'])
                    
                    if emb_conf.get('model'):
                        self.rag_config['embedding']['model_name'] = emb_conf['model']
                    
                    # Apply Vector DB Name override if present
                    if emb_conf.get('vectorDbName'):
                        vdb_name = emb_conf['vectorDbName']
                        backend_root = Path(__file__).parent.parent
                        new_chroma_path = (backend_root / "data" / "indexes" / vdb_name).resolve()
                        self.rag_config['vector_store']['chroma_path'] = str(new_chroma_path)
                        self.rag_config['vector_store']['collection_name'] = vdb_name
                        logger.info(f"Overrode vector store path to: {new_chroma_path}")
                        
                    logger.info(f"Applied embedding config overrides: {emb_conf}")
                except Exception as e:
                    logger.error(f"Failed to parse embedding_config from DB: {e}")

            # Override Chunking Config
            if active_config.get('chunking_config'):
                try:
                    chunk_conf = json.loads(active_config['chunking_config'])
                    
                    if 'parentChunkSize' in chunk_conf:
                        self.rag_config['chunking']['parent_splitter']['chunk_size'] = int(chunk_conf['parentChunkSize'])
                    if 'parentChunkOverlap' in chunk_conf:
                        self.rag_config['chunking']['parent_splitter']['chunk_overlap'] = int(chunk_conf['parentChunkOverlap'])
                    if 'childChunkSize' in chunk_conf:
                        self.rag_config['chunking']['child_splitter']['chunk_size'] = int(chunk_conf['childChunkSize'])
                    if 'childChunkOverlap' in chunk_conf:
                        self.rag_config['chunking']['child_splitter']['chunk_overlap'] = int(chunk_conf['childChunkOverlap'])
                        
                    logger.info(f"Applied chunking config overrides: {chunk_conf}")
                except Exception as e:
                    logger.error(f"Failed to parse chunking_config from DB: {e}")

            # Override Retriever Config
            if active_config.get('retriever_config'):
                try:
                    ret_conf = json.loads(active_config['retriever_config'])
                    
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
                        
                    logger.info(f"Applied retriever config overrides: {ret_conf}")
                except Exception as e:
                    logger.error(f"Failed to parse retriever_config from DB: {e}")
                    
        except Exception as e:
            logger.warning(f"Failed to load agent config overrides: {e}. Using system_settings defaults.")
    
    def search(self, query: str, top_k: Optional[int] = None, filter: Optional[Dict[str, Any]] = None) -> List[Document]:
        """
        Perform semantic search on the vector store.
        
        Note: Tracing is handled by the parent LangChain callback handler
        to ensure all RAG operations are grouped under a single trace.
        
        Args:
            query: Search query text
            top_k: Number of results to return (defaults to settings)
            filter: Optional metadata filter dict for ChromaDB
        
        Returns:
            List of relevant documents
        """
        rag_settings = get_rag_settings()
        k = top_k or rag_settings.get('top_k_final', 10)
        logger.info(f"Searching vector store for query: '{query[:100]}...' (top_k={k}, filter={filter})")
        
        try:
            start_time = time.time()
            
            # Use AdvancedRAGRetriever
            # The AdvancedRAGRetriever kwargs allow passing search parameters down
            docs = self.retriever._get_relevant_documents(query, run_manager=None, filter=filter, top_k=k)
            
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
        rag_settings = get_rag_settings()
        k = top_k or rag_settings.get('top_k_final', 10)
        logger.info(f"Searching with scores for: '{query[:100]}...'")
        
        try:
            start_time = time.time()

            # Delegate entirely to the advanced retriever
            results = self.retriever.retrieve_and_rerank_with_scores(query, top_k=k)

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


# Cache for vector store instances by agent_id
_vector_store_cache: Dict[Optional[int], VectorStoreService] = {}


def get_vector_store(agent_id: Optional[int] = None) -> VectorStoreService:
    """
    Get cached vector store service instance with agent-specific isolation.
    
    SECURITY: Each agent has its own vector collection (vectorDbName).
    Agent 1 cannot access Agent 2's RAG data.
    
    Args:
        agent_id: Agent ID for isolation. None = global/default collection.
    
    Returns:
        Context-aware vector store service
    """
    if agent_id not in _vector_store_cache:
        logger.info(f"Creating new VectorStoreService for agent_id={agent_id}")
        _vector_store_cache[agent_id] = VectorStoreService(agent_id=agent_id)
    return _vector_store_cache[agent_id]


def clear_vector_store_cache(agent_id: Optional[int] = None):
    """
    Clear cached vector store instances to force re-initialization.
    
    Use this when:
    - Agent RAG configuration changes
    - Vector DB is rebuilt
    - Security/access rules change
    
    Args:
        agent_id: Specific agent to clear, or None to clear all
    """
    global _vector_store_cache
    
    if agent_id is not None:
        if agent_id in _vector_store_cache:
            del _vector_store_cache[agent_id]
            logger.info(f"Cleared vector store cache for agent_id={agent_id}")
    else:
        _vector_store_cache.clear()
        logger.info("Cleared all vector store caches")
