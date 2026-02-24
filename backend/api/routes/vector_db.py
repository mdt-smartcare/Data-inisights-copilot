from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import require_super_admin, User
from backend.core.logging import get_logger
import os
import chromadb
from chromadb.config import Settings

logger = get_logger(__name__)

router = APIRouter(prefix="/vector-db", tags=["Vector Database"])

@router.get("/status/{vector_db_name}", response_model=Dict[str, Any], dependencies=[Depends(require_super_admin)])
async def get_vector_db_status(
    vector_db_name: str,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Get detailed statistics for a Vector Database including index count and vectors.
    Requires Super Admin role.
    """
    try:
        conn = db_service.get_connection()
        cursor = conn.cursor()
        
        # 1. Get statistics from SQLite document_index
        cursor.execute('''
            SELECT COUNT(*) as count, MAX(updated_at) as last_updated
            FROM document_index
            WHERE vector_db_name = ?
        ''', (vector_db_name,))
        
        row = cursor.fetchone()
        document_count = row['count'] if row else 0
        last_updated = row['last_updated'] if row else None
        
        conn.close()

        # 2. Get vector count directly from ChromaDB
        chroma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../../data/indexes/{vector_db_name}"))
        vector_count = 0
        chroma_exists = False
        
        if os.path.exists(chroma_path):
            try:
                client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
                try:
                    collection = client.get_collection(name=vector_db_name)
                    vector_count = collection.count()
                    chroma_exists = True
                except ValueError:
                    # Collection doesn't exist
                    pass
            except Exception as e:
                logger.warning(f"Could not connect to ChromaDB at {chroma_path}: {e}")

        return {
            "name": vector_db_name,
            "exists": document_count > 0 or chroma_exists,
            "total_documents_indexed": document_count,
            "total_vectors": vector_count,
            "last_updated_at": last_updated
        }
        
    except Exception as e:
        logger.error(f"Error fetching Vector DB status for {vector_db_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Vector DB status: {str(e)}"
        )
