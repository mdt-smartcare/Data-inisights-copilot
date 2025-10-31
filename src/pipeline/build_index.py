import faiss
import json
import os
import numpy as np
from tqdm import tqdm
import logging
import chromadb
from typing import List, Dict, Any
import yaml

logger = logging.getLogger(__name__)

class VectorIndexBuilder:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.config = self._load_config(config_path)
        self.index = None
        
    def _load_config(self, config_path):
        """Load configuration"""
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def build_faiss_index(self, embeddings: np.ndarray, metadata: List[Dict]):
        """Build FAISS index from embeddings"""
        # FIX: Ensure embeddings is a numpy array
        if isinstance(embeddings, list):
            embeddings = np.array(embeddings)
        
        # FIX: Check if embeddings is not empty
        if len(embeddings) == 0:
            raise ValueError("No embeddings provided to build index")
            
        dimension = embeddings.shape[1]
        
        # Create FAISS index (using Inner Product for cosine similarity since vectors are normalized)
        self.index = faiss.IndexFlatIP(dimension)
        
        # Add embeddings to index
        self.index.add(embeddings.astype('float32'))
        
        logger.info(f"FAISS index built with {self.index.ntotal} vectors")
        return self.index
    
    def save_faiss_index(self, index_path: str = None):
        """Save FAISS index to disk"""
        if not self.index:
            raise ValueError("No index to save. Call build_faiss_index first.")
        
        if index_path is None:
            index_path = self.config['vector_store']['index_path']
        
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        faiss.write_index(self.index, index_path)
        logger.info(f"FAISS index saved to: {index_path}")
    
    def save_metadata(self, metadata: List[Dict], metadata_path: str = None):
        """Save metadata to JSONL file"""
        if metadata_path is None:
            metadata_path = self.config['vector_store']['metadata_path']
        
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            for item in metadata:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        logger.info(f"Metadata saved to: {metadata_path}")
    
    def build_chroma_index(self, documents: List[Dict], embedding_model):
        """Build ChromaDB index"""
        chroma_path = "./data/indexes/chroma_db"
        
        # Create Chroma client
        client = chromadb.PersistentClient(path=chroma_path)
        
        # Create or get collection
        collection = client.get_or_create_collection(
            name="spice_healthcare",
            metadata={"description": "Healthcare database embeddings"}
        )
        
        # Prepare data for ChromaDB
        ids = [doc["metadata"]["row_hash"] for doc in documents]
        documents_text = [doc["content"] for doc in documents]
        metadatas = [doc["metadata"] for doc in documents]
        
        # Add to collection
        collection.add(
            ids=ids,
            documents=documents_text,
            metadatas=metadatas
        )
        
        logger.info(f"ChromaDB index built with {collection.count()} documents")
        return collection
    
    def build_complete_index(self, embeddings: np.ndarray, metadata: List[Dict], 
                           documents: List[Dict] = None, embedding_model = None):
        """Build complete vector index system"""
        vector_store_type = self.config['vector_store']['type']
        
        if vector_store_type == "faiss":
            # FIX: Convert embeddings to numpy array if it's a list
            if isinstance(embeddings, list):
                embeddings = np.array(embeddings)
                logger.info(f"Converted embeddings from list to numpy array with shape: {embeddings.shape}")
            
            self.build_faiss_index(embeddings, metadata)
            self.save_faiss_index()
            self.save_metadata(metadata)
            logger.info("FAISS index building completed successfully")
            
        elif vector_store_type == "chroma" and documents is not None:
            self.build_chroma_index(documents, embedding_model)
            logger.info("ChromaDB index building completed successfully")
        else:
            raise ValueError(f"Unsupported vector store type: {vector_store_type}")

# Factory function
def create_index_builder(config_path="config/embedding_config.yaml"):
    return VectorIndexBuilder(config_path)