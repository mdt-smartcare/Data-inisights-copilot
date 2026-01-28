from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class DbConnectionCreate(BaseModel):
    name: str
    uri: str
    engine_type: str = "postgresql"
    created_by: Optional[str] = None
    pool_config: Optional[str] = None # JSON string

class DbConnectionResponse(BaseModel):
    id: int
    name: str
    uri: str
    engine_type: str
    created_at: datetime
    pool_config: Optional[str] = None

class SchemaSelection(BaseModel):
    tables: List[str]
    # Optionally include columns mapping if needed later
    # columns: Optional[Dict[str, List[str]]] = None
