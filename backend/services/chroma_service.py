import chromadb
from chromadb.config import Settings
from typing import Dict
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
