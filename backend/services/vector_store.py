"""
Vector store service for semantic search using ChromaDB.
Provides retrieval capabilities for the RAG pipeline.
"""
import sys
import os
from pathlib import Path
from functools import lru_cache
from typing import List, Optional
import yaml

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.rag.retrieve import AdvancedRAGRetriever
from langchain_core.documents import Document
from langfuse.decorators import observe

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


from backend.sqliteDb.db import get_db_service
import json

class VectorStoreService:
    """Service for managing vector store operations."""
    
    def __init__(self):
        """Initialize the vector store with advanced retrieval."""
        logger.info("Initializing vector store service")
        
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
            active_config = db_service.get_active_config()
            
            if active_config:
                logger.info("Found active RAG config in database. Applying overrides...")
                
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
                            
                        # Update chunking config if provided (assuming it applies to parent/child broadly or specific)
                        # For simplicity, we apply size/overlap to parent splitter as it's the main driver
                        if 'chunkSize' in emb_conf:
                            if 'chunking' not in self.rag_config: self.rag_config['chunking'] = {}
                            if 'parent_splitter' not in self.rag_config['chunking']: self.rag_config['chunking']['parent_splitter'] = {}
                            self.rag_config['chunking']['parent_splitter']['chunk_size'] = int(emb_conf['chunkSize'])
                            
                        if 'chunkOverlap' in emb_conf:
                             if 'parent_splitter' not in self.rag_config['chunking']: self.rag_config['chunking']['parent_splitter'] = {}
                             self.rag_config['chunking']['parent_splitter']['chunk_overlap'] = int(emb_conf['chunkOverlap'])
                             
                        logger.info(f"Applied embedding config overrides from DB: {emb_conf}")
                    except Exception as e:
                        logger.error(f"Failed to parse embedding_config from DB: {e}")

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
                            
                        logger.info(f"Applied retriever config overrides from DB: {ret_conf}")
                    except Exception as e:
                        logger.error(f"Failed to parse retriever_config from DB: {e}")
                        
        except Exception as e:
            logger.warning(f"Failed to load config overrides from DB: {e}. Using YAML defaults.")
        
        logger.info("Final RAG Config loaded successfully")
        
        # Initialize advanced retriever
        self.retriever = AdvancedRAGRetriever(config=self.rag_config)
        logger.info("Vector store initialized successfully")
    
    @observe(as_type="span")
    def search(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        """
        Perform semantic search on the vector store.
        
        Args:
            query: Search query text
            top_k: Number of results to return (defaults to settings)
        
        Returns:
            List of relevant documents
        """
        k = top_k or settings.rag_top_k
        logger.info(f"Searching vector store for query: '{query[:100]}...' (top_k={k})")
        
        try:
            # Add metadata to trace
            try:
                from langfuse.decorators import langfuse_context
                langfuse_context.update_current_observation(
                input=query,
                metadata={"top_k": k, "method": "search"}
                )
            except:
                pass

            # Use the advanced retriever's invoke method
            result = self.retriever.invoke(query)
            
            # Handle different return types
            if isinstance(result, str):
                # If retriever returns string, wrap in document
                docs = [Document(page_content=result, metadata={"source": "rag"})]
            elif isinstance(result, list):
                docs = result
            else:
                docs = [Document(page_content=str(result), metadata={"source": "rag"})]
            
            logger.info(f"Retrieved {len(docs)} documents from vector store")
            
            # Log result count
            try:
                from langfuse.decorators import langfuse_context
                langfuse_context.update_current_observation(
                metadata={"results_count": len(docs)}
                )
            except:
                pass
                
            return docs
            
        except Exception as e:
            logger.error(f"Vector store search failed: {e}", exc_info=True)
            raise
    
    @observe(as_type="span")
    def search_with_scores(self, query: str, top_k: Optional[int] = None) -> List[tuple]:
        """
        Perform semantic search with relevance scores.
        
        Args:
            query: Search query text
            top_k: Number of results to return
        
        Returns:
            List of (document, score) tuples
        """
        k = top_k or settings.rag_top_k
        logger.info(f"Searching with scores for: '{query[:100]}...'")
        
        try:
            # Add metadata to trace
            try:
                from langfuse.decorators import langfuse_context
                langfuse_context.update_current_observation(
                input=query,
                metadata={"top_k": k, "method": "search_with_scores"}
                )
            except:
                pass

            # Check if retriever has reranking with scores method
            if hasattr(self.retriever, 'retrieve_and_rerank_with_scores'):
                results = self.retriever.retrieve_and_rerank_with_scores(query)
                logger.info(f"Retrieved {len(results)} documents with reranking scores")
                
                # Log result count
                try:
                    from langfuse.decorators import langfuse_context
                    langfuse_context.update_current_observation(
                    metadata={"results_count": len(results)}
                    )
                except:
                    pass
                    
                return results
            else:
                # Fallback to regular search
                docs = self.search(query, top_k=k)
                # Return with dummy scores
                results = [(doc, 1.0) for doc in docs]
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
def get_vector_store() -> VectorStoreService:
    """
    Get cached vector store service instance.
    Singleton pattern to avoid reloading the vector database.
    
    Returns:
        Cached vector store service
    """
    return VectorStoreService()
