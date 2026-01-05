from typing import List, Dict, Any, Optional
import logging
from backend.rag.retrieve import create_retriever

logger = logging.getLogger(__name__)

class RAGQueryInterface:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.retriever = create_retriever(config_path)
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path):
        """Load configuration"""
        import yaml
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def query(self, question: str, k: int = 5, score_threshold: float = 0.7) -> Dict[str, Any]:
        """Execute a RAG query and return formatted results"""
        try:
            # Retrieve relevant documents
            results = self.retriever.search(question, k, score_threshold)
            
            # Format response
            response = {
                "question": question,
                "results": results,
                "total_results": len(results),
                "summary": self._generate_summary(results)
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
    
    def _generate_summary(self, results: List[Dict]) -> str:
        """Generate a summary of the search results"""
        if not results:
            return "No relevant results found."
        
        table_counts = {}
        for result in results:
            table_name = result["metadata"].get("table_name", "unknown")
            table_counts[table_name] = table_counts.get(table_name, 0) + 1
        
        summary_parts = [f"Found {len(results)} relevant documents from:"]
        for table, count in table_counts.items():
            summary_parts.append(f"- {table}: {count} documents")
        
        return "\n".join(summary_parts)
    
    def get_table_statistics(self) -> Dict[str, Any]:
        """Get statistics about the indexed data"""
        if not self.retriever.collection:
            return {"error": "Collection not loaded"}
        
        table_stats = {}
        try:
            # Get all documents metadata to count tables
            all_docs = self.retriever.collection.get(include=["metadatas"])
            if all_docs and all_docs["metadatas"]:
                for metadata in all_docs["metadatas"]:
                    table_name = metadata.get("table_name")
                    if table_name:
                        table_stats[table_name] = table_stats.get(table_name, 0) + 1
            
            return {
                "total_documents": len(all_docs["metadatas"]) if all_docs.get("metadatas") else 0,
                "tables_indexed": len(table_stats),
                "documents_per_table": table_stats
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}

# API for external integration
class RAGAPI:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.query_interface = RAGQueryInterface(config_path)
    
    def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """Public API method for search"""
        return self.query_interface.query(query, **kwargs)
    
    def health_check(self) -> Dict[str, Any]:
        """Health check endpoint"""
        stats = self.query_interface.get_table_statistics()
        return {
            "status": "healthy",
            "index_size": stats.get("total_documents", 0),
            "tables_available": stats.get("tables_indexed", 0)
        }

# Factory function
def create_query_interface(config_path="config/embedding_config.yaml"):
    return RAGQueryInterface(config_path)