import re
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional

from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.logging import get_logger
from backend.core.permissions import require_editor, User, get_current_user

logger = get_logger(__name__)

router = APIRouter(prefix="/vector-db", tags=["Vector DB"])

class VectorDBRegisterRequest(BaseModel):
    name: str
    data_source_id: str

@router.get("/check-name")
async def check_vector_db_name(
    name: str,
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Check if a vector DB name exists and is valid.
    """
    # Validate rules: Alphanumeric + underscores, no spaces
    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        return {"valid": False, "message": "Name must contain only alphanumeric characters and underscores, no spaces."}
        
    db = db_service.get_vector_db_by_name(name)
    if db:
        return {"valid": False, "message": f"Vector DB '{name}' already exists."}
        
    return {"valid": True, "message": "Name is valid and available."}

@router.post("/register")
async def register_vector_db(
    request: VectorDBRegisterRequest,
    current_user: User = Depends(require_editor),
    db_service: DatabaseService = Depends(get_db_service)
):
    """
    Register a new Vector DB namespace.
    """
    if not re.match(r'^[a-zA-Z0-9_]+$', request.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Name must contain only alphanumeric characters and underscores, no spaces."
        )
        
    db = db_service.get_vector_db_by_name(request.name)
    if db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Vector DB '{request.name}' already exists."
        )
        
    try:
        db_id = db_service.register_vector_db(request.name, request.data_source_id, current_user.username)
        return {"id": db_id, "name": request.name, "message": "Vector DB registered successfully."}
    except Exception as e:
        logger.error(f"Error registering vector DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to register Vector DB"
        )
