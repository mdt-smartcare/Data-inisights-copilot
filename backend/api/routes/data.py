from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any

from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.models.data import DbConnectionCreate, DbConnectionResponse
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/data", tags=["Data Configuration"])

@router.get("/connections", response_model=List[DbConnectionResponse])
async def list_connections(
    db_service: DatabaseService = Depends(get_db_service)
):
    """List all saved database connections."""
    try:
        connections = db_service.get_db_connections()
        return connections
    except Exception as e:
        logger.error(f"Error listing connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/connections", response_model=Dict[str, Any])
async def create_connection(
    connection: DbConnectionCreate,
    db_service: DatabaseService = Depends(get_db_service)
):
    """Add a new database connection."""
    try:
        conn_id = db_service.add_db_connection(
            name=connection.name,
            uri=connection.uri,
            engine_type=connection.engine_type,
            created_by=connection.created_by
        )
        return {"status": "success", "id": conn_id, "message": "Connection added successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: int,
    db_service: DatabaseService = Depends(get_db_service)
):
    """Delete a database connection."""
    try:
        success = db_service.delete_db_connection(connection_id)
        if not success:
            raise HTTPException(status_code=404, detail="Connection not found")
        return {"status": "success", "message": "Connection deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Placeholder for Schema Explorer (Phase 7)
@router.get("/connections/{connection_id}/schema")
async def get_connection_schema(
    connection_id: int,
    db_service: DatabaseService = Depends(get_db_service)
):
    """Fetch schema for a specific connection (To be implemented)."""
    # Verify connection exists
    conn = db_service.get_db_connection_by_id(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # TODO: Implement connection testing and schema fetch in SQLService
    return {"message": "Schema fetching not implemented yet", "connection": conn["name"]}
