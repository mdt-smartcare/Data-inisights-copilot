import logging
from typing import List
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class LocalHuggingFaceEmbeddings(Embeddings):
    def __init__(self, model_id: str):
        logger.info(f"Initializing local embedding model from: {model_id}")
        try:
            self.model = SentenceTransformer(model_id)
            logger.info("Embedding model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model from {model_id}: {e}")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, show_progress_bar=True, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()