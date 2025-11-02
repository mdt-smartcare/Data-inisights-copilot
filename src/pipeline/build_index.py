import logging
import pickle
import os
from typing import List, Dict
from langchain_core.documents import Document
from langchain_core.stores import BaseStore
from langchain_chroma import Chroma
from src.pipeline.embed import LocalHuggingFaceEmbeddings
import chromadb

logger = logging.getLogger(__name__)

def build_advanced_chroma_index(
    child_docs: List[Document],
    docstore: BaseStore,
    embedding_function: LocalHuggingFaceEmbeddings,
    config: dict
):
    chroma_path = config['vector_store']['chroma_path']
    collection_name = config['vector_store']['collection_name']
    
    logger.info(f"Building Chroma index at '{chroma_path}' with {len(child_docs)} documents.")

    # --- THIS IS THE FIX ---
    # Create the directory before trying to save files in it
    os.makedirs(chroma_path, exist_ok=True)
    # -----------------------

    # Disable telemetry to fix the log errors
    client_settings = chromadb.Settings(anonymized_telemetry=False)

    Chroma.from_documents(
        documents=child_docs, 
        embedding=embedding_function,
        collection_name=collection_name, 
        persist_directory=chroma_path,
        client_settings=client_settings
    )
    
    docstore_path = f"{chroma_path}/parent_docstore.pkl"
    with open(docstore_path, "wb") as f:
        pickle.dump(docstore, f)
        
    logger.info(f"Chroma index built and parent docstore saved to '{docstore_path}'.")