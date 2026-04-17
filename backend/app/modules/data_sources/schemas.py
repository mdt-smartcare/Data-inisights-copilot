"""
Pydantic schemas for data sources.

Supports both database connections and file-based sources.
Includes file ingestion schemas for DuckDB processing.
"""
from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ==========================================
# Base Schemas
# ==========================================

class DataSourceBase(BaseModel):
    """Base data source schema."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    source_type: Literal["database", "file"] = Field(..., description="Type of data source")


# ==========================================
# Create Schemas
# ==========================================

class DatabaseSourceCreate(DataSourceBase):
    """Create a database connection data source."""
    source_type: Literal["database"] = "database"
    db_url: str = Field(..., description="Database connection URL (can be base64 encoded)")
    db_engine_type: str = Field(..., description="Database engine: postgresql, mysql, sqlite")
    is_encoded: bool = Field(default=False, description="Whether db_url is base64 encoded")
    
    @field_validator("db_engine_type")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        allowed = {"postgresql", "mysql", "sqlite", "mssql", "oracle"}
        if v.lower() not in allowed:
            raise ValueError(f"db_engine_type must be one of: {', '.join(allowed)}")
        return v.lower()


class FileSourceCreate(DataSourceBase):
    """Create a file-based data source."""
    source_type: Literal["file"] = "file"
    original_file_path: str = Field(..., description="Path to uploaded file")
    file_type: str = Field(..., description="File type: csv, xlsx, pdf, json")
    duckdb_file_path: Optional[str] = None
    duckdb_table_name: Optional[str] = None
    columns_json: Optional[str] = None
    row_count: Optional[int] = None
    
    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, v: str) -> str:
        allowed = {"csv", "xlsx", "xls", "pdf", "json", "parquet"}
        if v.lower() not in allowed:
            raise ValueError(f"file_type must be one of: {', '.join(allowed)}")
        return v.lower()


# ==========================================
# Update Schema
# ==========================================

class DataSourceUpdate(BaseModel):
    """Update a data source (all fields optional)."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    # Database fields
    db_url: Optional[str] = None
    db_engine_type: Optional[str] = None
    # File fields
    original_file_path: Optional[str] = None
    file_type: Optional[str] = None
    duckdb_file_path: Optional[str] = None
    duckdb_table_name: Optional[str] = None
    columns_json: Optional[str] = None
    row_count: Optional[int] = None


# ==========================================
# Response Schemas
# ==========================================

class DataSourceResponse(DataSourceBase):
    """Data source response schema."""
    id: UUID
    # Database fields - credentials are masked in db_url
    db_url: Optional[str] = None  # Returned with credentials masked
    db_engine_type: Optional[str] = None
    # File fields
    original_file_path: Optional[str] = None
    file_type: Optional[str] = None
    duckdb_file_path: Optional[str] = None
    duckdb_table_name: Optional[str] = None
    columns_json: Optional[str] = None
    row_count: Optional[int] = None
    # Metadata
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    # Dependency info (populated in list/get views)
    dependent_agents: List[str] = Field(default_factory=list, description="Names of agents using this source")
    dependent_config_count: int = Field(default=0, description="Number of configurations using this source")
    
    model_config = {"from_attributes": True}


class DataSourceListResponse(BaseModel):
    """Paginated list of data sources."""
    data_sources: List[DataSourceResponse]
    total: int
    skip: int
    limit: int


# ==========================================
# Search Schema
# ==========================================

class DataSourceSearchParams(BaseModel):
    """Search parameters for data sources."""
    query: Optional[str] = Field(None, description="Search in title/description")
    source_type: Optional[Literal["database", "file"]] = None
    created_by: Optional[UUID] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


# ==========================================
# Connection Test Schemas
# ==========================================

class TestConnectionRequest(BaseModel):
    """Request to test a database connection."""
    db_url: str
    db_engine_type: str
    is_encoded: bool = Field(default=False, description="Whether db_url is base64 encoded")


class TestConnectionResponse(BaseModel):
    """Response from connection test."""
    success: bool
    message: str
    tables: Optional[List[str]] = None
    error: Optional[str] = None


# ==========================================
# File Ingestion Schemas
# ==========================================

class ExtractedDocument(BaseModel):
    """A single extracted document preview for RAG."""
    page_content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestionResponse(BaseModel):
    """Response from file upload/extraction endpoint."""
    status: str
    file_name: str
    file_type: str
    total_documents: int
    documents: List[ExtractedDocument] = Field(default_factory=list)
    table_name: Optional[str] = None
    columns: Optional[List[str]] = None
    column_details: Optional[List[Dict[str, str]]] = None
    row_count: Optional[int] = None
    processing_mode: Optional[str] = None  # 'sync' or 'background'
    message: Optional[str] = None
    data_source_id: Optional[UUID] = None  # Link to created data source


class SQLQueryRequest(BaseModel):
    """Request for SQL query execution."""
    query: str = Field(..., min_length=1)


class SQLQueryResponse(BaseModel):
    """Response from SQL query execution."""
    status: str
    query: str
    row_count: int
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None


class FileTableInfo(BaseModel):
    """Information about an uploaded file table."""
    name: str
    original_filename: str
    file_type: str
    row_count: Optional[int] = None
    columns: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None


class FileTablesResponse(BaseModel):
    """Response listing available tables from uploaded files."""
    tables: List[FileTableInfo] = Field(default_factory=list)




class DataSourcePreviewResponse(BaseModel):
    """Response with sample data for a data source."""
    source_type: str
    file_name: Optional[str] = None
    table_name: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    column_details: Optional[List[Dict[str, str]]] = None
    row_count: Optional[int] = None
    documents: List[ExtractedDocument] = Field(default_factory=list)
    total_documents: int = 0


class ForeignKeyInfo(BaseModel):
    """Foreign key reference info."""
    referenced_table: str
    referenced_column: Optional[str] = None


class TableSchemaColumn(BaseModel):
    """Column info in table schema."""
    column_name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    foreign_key: Optional[ForeignKeyInfo] = None


class TableSchemaResponse(BaseModel):
    """Table schema response."""
    table_name: str
    columns: List[TableSchemaColumn]
    primary_key_columns: List[str] = Field(default_factory=list)


class TableRelationship(BaseModel):
    """Foreign key relationship between tables."""
    from_table: str
    from_columns: List[str]
    to_table: str
    to_columns: List[str]


class DataSourceSchemaResponse(BaseModel):
    """
    Full schema response for a data source.
    Used in Step 2 of config wizard to show available tables/columns for selection.
    """
    source_type: str  # 'database' or 'file'
    tables: List[TableSchemaResponse]
    relationships: List[TableRelationship] = Field(default_factory=list)
    file_name: Optional[str] = None
    row_count: Optional[int] = None
