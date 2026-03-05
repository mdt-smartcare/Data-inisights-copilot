import chromadb
from chromadb.config import Settings
from typing import Dict, Set, List, Optional
import os
import threading

class ChromaClientManager:
    _instances: Dict[str, chromadb.PersistentClient] = {}
    _lock = threading.Lock()

    @classmethod
    def get_client(cls, path: str) -> chromadb.PersistentClient:
        absolute_path = os.path.abspath(path)
        with cls._lock:
            if absolute_path not in cls._instances:
                # Ensure the directory exists before creating the client
                os.makedirs(absolute_path, exist_ok=True)
                cls._instances[absolute_path] = chromadb.PersistentClient(
                    path=absolute_path, 
                    settings=Settings(anonymized_telemetry=False)
                )
            return cls._instances[absolute_path]

def get_chroma_client(path: str) -> chromadb.PersistentClient:
    return ChromaClientManager.get_client(path)


def get_existing_chunk_ids(
    chroma_path: str, 
    collection_name: str,
    batch_size: int = 10000
) -> Set[str]:
    """
    Get all existing document IDs from a Chroma collection.
    
    Used for stateful job resuming - allows filtering out already-embedded
    documents before sending to the embedding model.
    
    Args:
        chroma_path: Path to the Chroma database
        collection_name: Name of the collection to query
        batch_size: Number of IDs to fetch per batch (for large collections)
        
    Returns:
        Set of existing document IDs in the collection
    """
    if not os.path.exists(chroma_path):
        return set()
    
    try:
        client = get_chroma_client(chroma_path)
        try:
            collection = client.get_collection(name=collection_name)
        except ValueError:
            # Collection doesn't exist
            return set()
        
        # Get total count
        count = collection.count()
        if count == 0:
            return set()
        
        # Fetch all IDs in batches to avoid memory issues with large collections
        all_ids: Set[str] = set()
        offset = 0
        
        while offset < count:
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=[]  # Only fetch IDs, not embeddings or documents
            )
            if result and result.get("ids"):
                all_ids.update(result["ids"])
            offset += batch_size
        
        return all_ids
        
    except Exception as e:
        # Log but don't fail - if we can't check, we'll re-embed everything
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch existing chunk IDs: {e}")
        return set()


def filter_unembedded_chunks(
    documents: List,
    existing_ids: Set[str],
    id_generator: Optional[callable] = None
) -> tuple:
    """
    Filter documents to only include those not already embedded.
    
    Args:
        documents: List of documents to filter
        existing_ids: Set of IDs already in the vector store
        id_generator: Optional function to generate ID from document.
                      If None, uses default hash-based ID generation.
                      
    Returns:
        Tuple of (filtered_documents, filtered_indices, skipped_count)
        - filtered_documents: Documents that need embedding
        - filtered_indices: Original indices of filtered documents
        - skipped_count: Number of documents skipped (already embedded)
    """
    import hashlib
    
    def default_id_generator(doc):
        """Generate chunk ID matching the embedding job logic."""
        content = getattr(doc, "page_content", getattr(doc, "content", ""))
        parent_id = doc.metadata.get("doc_id", "unknown") if hasattr(doc, "metadata") else "unknown"
        return hashlib.sha256(f"{content}{parent_id}".encode()).hexdigest()
    
    gen_id = id_generator or default_id_generator
    
    filtered_docs = []
    filtered_indices = []
    skipped = 0
    
    for idx, doc in enumerate(documents):
        doc_id = gen_id(doc)
        if doc_id not in existing_ids:
            filtered_docs.append(doc)
            filtered_indices.append(idx)
        else:
            skipped += 1
    
    return filtered_docs, filtered_indices, skipped
