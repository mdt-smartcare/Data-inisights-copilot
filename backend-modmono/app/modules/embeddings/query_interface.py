"""
RAG Query Interface - High-level API for RAG retrieval and chat.

Provides:
- RAGQueryInterface for executing queries against embedded documents
- RAGAPI for external integration with health checks
- Table statistics and search result formatting
"""
from typing import List, Dict, Any, Optional

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class RAGQueryInterface:
    """
    High-level interface for RAG queries.
    
    Wraps the AdvancedRAGRetriever with convenience methods
    for common query patterns.
    """
    
    def __init__(self, collection_name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the query interface.
        
        Args:
            collection_name: Name of the vector store collection
            config: Optional retriever configuration
        """
        self.collection_name = collection_name
        self.config = config or {}
        self._retriever = None
    
    @property
    def retriever(self):
        """Lazy initialization of retriever."""
        if self._retriever is None:
            from app.modules.embeddings.retrieve import create_retriever
            self._retriever = create_retriever(
                collection_name=self.collection_name,
                config=self.config
            )
        return self._retriever
    
    def query(
        self, 
        question: str, 
        top_k: int = 5, 
        filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a RAG query and return formatted results.
        
        Args:
            question: The query text
            top_k: Number of results to return
            filter: Optional metadata filter
            
        Returns:
            Dict with question, results, total_results, and summary
        """
        try:
            # Retrieve relevant documents
            results = self.retriever._get_relevant_documents(
                question, 
                top_k=top_k,
                filter=filter
            )
            
            # Format results
            formatted_results = []
            for doc in results:
                formatted_results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source_table": doc.metadata.get("source_table", "unknown"),
                    "source_id": doc.metadata.get("source_id", "unknown"),
                })
            
            response = {
                "question": question,
                "results": formatted_results,
                "total_results": len(formatted_results),
                "summary": self._generate_summary(formatted_results)
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {
                "question": question,
                "error": str(e),
                "results": [],
                "total_results": 0
            }
    
    def query_with_scores(
        self, 
        question: str, 
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a RAG query and return results with relevance scores.
        
        Args:
            question: The query text
            top_k: Number of results to return
            filter: Optional metadata filter
            
        Returns:
            Dict with results including reranker scores
        """
        try:
            results_with_scores = self.retriever.retrieve_and_rerank_with_scores(
                question,
                top_k=top_k,
                filter=filter
            )
            
            formatted_results = []
            for doc, score in results_with_scores:
                formatted_results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "source_table": doc.metadata.get("source_table", "unknown"),
                    "source_id": doc.metadata.get("source_id", "unknown"),
                    "relevance_score": round(score, 4),
                })
            
            return {
                "question": question,
                "results": formatted_results,
                "total_results": len(formatted_results),
                "summary": self._generate_summary(formatted_results)
            }
            
        except Exception as e:
            logger.error(f"Query with scores failed: {e}")
            return {
                "question": question,
                "error": str(e),
                "results": [],
                "total_results": 0
            }
    
    def _generate_summary(self, results: List[Dict]) -> str:
        """Generate a summary of the search results."""
        if not results:
            return "No relevant results found."
        
        table_counts = {}
        for result in results:
            table_name = result.get("source_table", "unknown")
            table_counts[table_name] = table_counts.get(table_name, 0) + 1
        
        summary_parts = [f"Found {len(results)} relevant documents from:"]
        for table, count in table_counts.items():
            summary_parts.append(f"- {table}: {count} documents")
        
        return "\n".join(summary_parts)
    
    def get_context_for_llm(
        self, 
        question: str, 
        top_k: int = 5,
        max_context_length: int = 4000
    ) -> str:
        """
        Get formatted context for LLM prompt injection.
        
        Args:
            question: The query text
            top_k: Number of documents to retrieve
            max_context_length: Maximum character length of context
            
        Returns:
            Formatted context string for LLM
        """
        results = self.query(question, top_k=top_k)
        
        if not results.get("results"):
            return "No relevant context found."
        
        context_parts = []
        current_length = 0
        
        for i, result in enumerate(results["results"], 1):
            entry = f"[Document {i}]\n{result['content']}\n"
            
            if current_length + len(entry) > max_context_length:
                break
            
            context_parts.append(entry)
            current_length += len(entry)
        
        return "\n".join(context_parts)


class RAGAPI:
    """
    Public API for RAG operations with health checks.
    
    Designed for external integration and monitoring.
    """
    
    def __init__(self, collection_name: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the RAG API.
        
        Args:
            collection_name: Name of the vector store collection
            config: Optional configuration
        """
        self.query_interface = RAGQueryInterface(collection_name, config)
        self.collection_name = collection_name
    
    def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Public API method for search.
        
        Args:
            query: Search query text
            **kwargs: Additional arguments (top_k, filter, etc.)
            
        Returns:
            Search results
        """
        return self.query_interface.query(query, **kwargs)
    
    def search_with_scores(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        Search with relevance scores.
        
        Args:
            query: Search query text
            **kwargs: Additional arguments
            
        Returns:
            Search results with scores
        """
        return self.query_interface.query_with_scores(query, **kwargs)
    
    def get_context(self, query: str, **kwargs) -> str:
        """
        Get context for LLM.
        
        Args:
            query: Query text
            **kwargs: Additional arguments
            
        Returns:
            Formatted context string
        """
        return self.query_interface.get_context_for_llm(query, **kwargs)
    
    def health_check(self) -> Dict[str, Any]:
        """
        Health check endpoint.
        
        Returns:
            Health status with index statistics
        """
        try:
            from app.modules.embeddings.vector_stores.factory import get_vector_store
            
            vector_store = get_vector_store(self.collection_name)
            
            # Try to get collection count
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, can't use run_until_complete
                    count = 0  # Fallback
                else:
                    count = loop.run_until_complete(vector_store.get_collection_count())
            except Exception:
                count = 0
            
            return {
                "status": "healthy",
                "collection": self.collection_name,
                "index_size": count,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "collection": self.collection_name,
                "error": str(e)
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics about the index.
        
        Returns:
            Index statistics
        """
        try:
            from app.modules.embeddings.vector_stores.factory import get_vector_store
            import asyncio
            
            vector_store = get_vector_store(self.collection_name)
            
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    count = 0
                else:
                    count = loop.run_until_complete(vector_store.get_collection_count())
            except Exception:
                count = 0
            
            return {
                "collection": self.collection_name,
                "total_vectors": count,
                "status": "available" if count > 0 else "empty"
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {
                "collection": self.collection_name,
                "error": str(e)
            }


# =============================================================================
# Factory Functions
# =============================================================================

def create_query_interface(
    collection_name: str,
    config: Optional[Dict[str, Any]] = None
) -> RAGQueryInterface:
    """
    Create a RAG query interface for a collection.
    
    Args:
        collection_name: Name of the vector store collection
        config: Optional retriever configuration
        
    Returns:
        Configured RAGQueryInterface
    """
    return RAGQueryInterface(collection_name, config)


def create_rag_api(
    collection_name: str,
    config: Optional[Dict[str, Any]] = None
) -> RAGAPI:
    """
    Create a RAG API instance for a collection.
    
    Args:
        collection_name: Name of the vector store collection
        config: Optional configuration
        
    Returns:
        Configured RAGAPI
    """
    return RAGAPI(collection_name, config)
