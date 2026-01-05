import logging
from typing import List
from pathlib import Path
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class LocalHuggingFaceEmbeddings(Embeddings):
    def __init__(self, model_id: str):
        logger.info(f"Initializing local embedding model from: {model_id}")
        
        # Resolve relative paths to absolute paths
        model_path = Path(model_id)
        if not model_path.is_absolute() and model_id.startswith('./'):
            # Get the backend directory (go up from pipeline to backend)
            backend_root = Path(__file__).parent.parent
            model_path = (backend_root / model_id.lstrip('./')).resolve()
            logger.info(f"Resolved model path to: {model_path}")
        else:
            model_path = model_id
        
        try:
            self.model = SentenceTransformer(str(model_path))
            logger.info("Embedding model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model from {model_path}: {e}")
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, show_progress_bar=True, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(text, normalize_embeddings=True).tolist()