import faiss
import json
import os
import numpy as np
from typing import List, Dict, Any
import logging
import chromadb
from src.pipeline.embed import create_embedding_model

logger = logging.getLogger(__name__)

class VectorRetriever:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.config = self._load_config(config_path)
        self.client = None
        self.collection = None
        self.embedding_model = create_embedding_model(config_path)
        
    def _load_config(self, config_path):
        """Load configuration"""
        import yaml
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def load_index(self):
        """Load ChromaDB index"""
        try:
            chroma_path = "./data/indexes/chroma_db"
            self.client = chromadb.PersistentClient(path=chroma_path)
            self.collection = self.client.get_collection("spice_healthcare")
            
            logger.info(f"Loaded ChromaDB index with {self.collection.count()} documents")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load ChromaDB index: {e}")
            return False
    
    def search(self, query: str, k: int = 5, score_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        if not self.collection:
            raise ValueError("Collection not loaded. Call load_index() first.")
        
        try:
            # Use ChromaDB's built-in search
            results = self.collection.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "metadatas", "distances"]
            )
            
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i, (doc, metadata, distance) in enumerate(zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0]
                )):
                    # Convert distance to similarity score (Chroma uses distance, we want similarity)
                    similarity_score = 1.0 / (1.0 + distance) if distance > 0 else 1.0
                    
                    if similarity_score >= score_threshold:
                        result = {
                            "content": doc,
                            "metadata": metadata,
                            "score": float(similarity_score)
                        }
                        formatted_results.append(result)
            
            logger.info(f"Search returned {len(formatted_results)} results for query: {query}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def batch_search(self, queries: List[str], k: int = 5) -> List[List[Dict[str, Any]]]:
        """Search for multiple queries at once"""
        if not self.collection:
            raise ValueError("Collection not loaded. Call load_index() first.")
        
        try:
            results = self.collection.query(
                query_texts=queries,
                n_results=k,
                include=["documents", "metadatas", "distances"]
            )
            
            all_results = []
            for query_idx in range(len(queries)):
                query_results = []
                if (results["documents"] and results["documents"][query_idx] and
                    results["metadatas"] and results["metadatas"][query_idx] and
                    results["distances"] and results["distances"][query_idx]):
                    
                    for doc, metadata, distance in zip(
                        results["documents"][query_idx],
                        results["metadatas"][query_idx],
                        results["distances"][query_idx]
                    ):
                        similarity_score = 1.0 / (1.0 + distance) if distance > 0 else 1.0
                        query_results.append({
                            "content": doc,
                            "metadata": metadata,
                            "score": float(similarity_score)
                        })
                
                all_results.append(query_results)
            
            return all_results
            
        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            return [[] for _ in queries]

# Factory function
def create_retriever(config_path="config/embedding_config.yaml"):
    retriever = VectorRetriever(config_path)
    if retriever.load_index():
        return retriever
    else:
        raise Exception("Failed to load vector index")