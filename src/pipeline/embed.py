import os
import torch
import yaml
import logging
from typing import List, Dict, Any
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import numpy as np

logger = logging.getLogger(__name__)

# --- YOUR TRIAL CODE INTEGRATED ---
class LocalHuggingFaceEmbeddings(Embeddings):
    """Custom embedding class to use local BGE-M3 model with LangChain"""
    def __init__(self, model_id: str, model_path: str = None):
        self.model_id = model_id
        self.model_path = model_path
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load the model from local path or download if needed"""
        try:
            # Try to load from local path first
            if self.model_path and os.path.exists(self.model_path):
                logger.info(f"Loading model from local path: {self.model_path}")
                self.model = SentenceTransformer(self.model_path)
            else:
                logger.info(f"Downloading model: {self.model_id}")
                self.model = SentenceTransformer(self.model_id)
                # Save locally for future use if path provided
                if self.model_path:
                    os.makedirs(self.model_path, exist_ok=True)
                    self.model.save(self.model_path)
                    logger.info(f"Model saved to: {self.model_path}")
            
            logger.info("Model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed documents - disable progress bar to allow tqdm control"""
        if not self.model:
            raise ValueError("Model not loaded. Call load_model() first.")
        
        return self.model.encode(
            texts, 
            show_progress_bar=False, 
            normalize_embeddings=True
        ).tolist()

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query"""
        if not self.model:
            raise ValueError("Model not loaded. Call load_model() first.")
            
        return self.model.encode(
            text, 
            normalize_embeddings=True
        ).tolist()


class EmbeddingModel:
    def __init__(self, config_path="config/embedding_config.yaml"):
        self.config = self._load_config(config_path)
        self.embedding_model = None
    
    def _load_config(self, config_path):
        """Load embedding configuration"""
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def load_model(self):
        """Load the embedding model using your custom class"""
        model_path = self.config['embedding']['model_path']
        model_name = self.config['embedding']['model_name']
        
        try:
            self.embedding_model = LocalHuggingFaceEmbeddings(
                model_id=model_name,
                model_path=model_path
            )
            logger.info("Embedding model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            return False
    
    def encode_texts(self, texts: List[str], batch_size: int = None) -> np.ndarray:
        """Encode a list of texts into embeddings"""
        if not self.embedding_model:
            raise ValueError("Model not loaded. Call load_model() first.")
        
        if batch_size is None:
            batch_size = self.config['embedding']['batch_size']
        
        embeddings = []
        
        for i in tqdm(range(0, len(texts), batch_size), desc="Encoding texts"):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = self.embedding_model.embed_documents(batch_texts)
            embeddings.append(batch_embeddings)
        
        return np.vstack(embeddings)
    
    def encode_documents(self, documents: List[Dict[str, Any]]) -> tuple:
        """Encode documents and return embeddings with metadata"""
        texts = [doc["content"] for doc in documents]
        metadata = [doc["metadata"] for doc in documents]
        
        logger.info(f"Encoding {len(texts)} documents")
        embeddings = self.encode_texts(texts)
        
        logger.info(f"Generated embeddings with shape: {embeddings.shape}")
        return embeddings, metadata

    def get_langchain_embeddings(self):
        """Get the LangChain embeddings interface for use with Chroma"""
        if not self.embedding_model:
            raise ValueError("Model not loaded. Call load_model() first.")
        return self.embedding_model


# Factory function
def create_embedding_model(config_path="config/embedding_config.yaml"):
    model = EmbeddingModel(config_path)
    if model.load_model():
        return model
    else:
        raise Exception("Failed to load embedding model")