"""
API routes for data source management.

Provides endpoints for:
- Database connection management
- File-based source management
- File upload and ingestion (DuckDB processing)
- SQL query execution
- Connection testing
"""
from typing import Optional, List
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, Query, status,
    File, UploadFile, BackgroundTasks,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import get_current_user, require_editor, require_admin
from app.core.models.common import BaseResponse
from app.modules.users.schemas import User
from app.modules.data_sources.service import DataSourceService
from app.modules.data_sources.schemas import (
    DatabaseSourceCreate, FileSourceCreate, DataSourceUpdate,
    DataSourceResponse, DataSourceListResponse,
    TestConnectionRequest, TestConnectionResponse,
    # Ingestion schemas
    IngestionResponse, ExtractedDocument,
    SQLQueryRequest, SQLQueryResponse,
    FileTablesResponse, FileTableInfo,
    TableSchemaResponse, TableSchemaColumn,
    DataSourceSchemaResponse, DataSourcePreviewResponse,
)


router = APIRouter(prefix="/data-sources", tags=["data-sources"])


# ==========================================
# Dependencies
# ==========================================

def get_data_source_service(db: AsyncSession = Depends(get_db)) -> DataSourceService:
    return DataSourceService(db)


# ==========================================
# Create Endpoints
# ==========================================

@router.post("/database", response_model=BaseResponse[DataSourceResponse], status_code=status.HTTP_201_CREATED)
async def create_database_source(
    data: DatabaseSourceCreate,
    current_user: User = Depends(require_editor),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceResponse]:
    """Create a database connection data source."""
    source = await service.create_database_source(
        title=data.title,
        db_url=data.db_url,
        db_engine_type=data.db_engine_type,
        description=data.description,
        created_by=current_user.id,
    )
    return BaseResponse.ok(data=source)


@router.post("/file", response_model=BaseResponse[DataSourceResponse], status_code=status.HTTP_201_CREATED)
async def create_file_source(
    data: FileSourceCreate,
    current_user: User = Depends(require_editor),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceResponse]:
    """Create a file-based data source."""
    source = await service.create_file_source(
        title=data.title,
        original_file_path=data.original_file_path,
        file_type=data.file_type,
        description=data.description,
        duckdb_file_path=data.duckdb_file_path,
        duckdb_table_name=data.duckdb_table_name,
        columns_json=data.columns_json,
        row_count=data.row_count,
        created_by=current_user.id,
    )
    return BaseResponse.ok(data=source)


# ==========================================
# List/Get Endpoints
# ==========================================

@router.get("", response_model=BaseResponse[DataSourceListResponse])
async def list_data_sources(
    query: Optional[str] = Query(None, description="Search in title/description"),
    source_type: Optional[str] = Query(None, pattern="^(database|file)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceListResponse]:
    """List data sources with optional filters."""
    result = await service.list_sources(
        query=query,
        source_type=source_type,
        skip=skip,
        limit=limit,
    )
    return BaseResponse.ok(data=result)


@router.get("/{source_id}", response_model=BaseResponse[DataSourceResponse])
async def get_data_source(
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceResponse]:
    """Get data source by ID."""
    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    return BaseResponse.ok(data=source)


@router.get("/{source_id}/schema", response_model=BaseResponse[DataSourceSchemaResponse])
async def get_data_source_schema(
    source_id: UUID,
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceSchemaResponse]:
    """
    Get schema (tables and columns) for a data source.
    
    Used in Step 2 of config wizard to display available tables/columns for selection.
    
    For database sources: Returns all tables with their columns from the connected database.
    For file sources: Returns the table schema from DuckDB or columns_json.
    """
    try:
        schema_data = await service.get_schema(source_id)
        # Convert to response model
        tables = [
            TableSchemaResponse(
                table_name=t["table_name"],
                columns=[TableSchemaColumn(**c) for c in t["columns"]]
            )
            for t in schema_data["tables"]
        ]
        return BaseResponse.ok(data=DataSourceSchemaResponse(
            source_type=schema_data["source_type"],
            tables=tables,
            file_name=schema_data.get("file_name"),
            row_count=schema_data.get("row_count"),
        ))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{source_id}/preview", response_model=BaseResponse[DataSourcePreviewResponse])
async def get_data_source_preview(
    source_id: UUID,
    limit: int = Query(10, ge=1, le=50, description="Number of sample rows to return"),
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourcePreviewResponse]:
    """
    Get sample data preview for a data source.
    
    Returns sample rows formatted as documents for display in the UI.
    Currently only supports file sources (DuckDB tables).
    """
    try:
        preview_data = await service.get_preview(source_id, limit=limit)
        return BaseResponse.ok(data=DataSourcePreviewResponse(
            source_type=preview_data["source_type"],
            file_name=preview_data.get("file_name"),
            table_name=preview_data.get("table_name"),
            columns=preview_data.get("columns", []),
            column_details=preview_data.get("column_details"),
            row_count=preview_data.get("row_count"),
            documents=[ExtractedDocument(**doc) for doc in preview_data.get("documents", [])],
            total_documents=preview_data.get("total_documents", 0),
        ))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==========================================
# Update/Delete Endpoints
# ==========================================

@router.put("/{source_id}", response_model=BaseResponse[DataSourceResponse])
async def update_data_source(
    source_id: UUID,
    data: DataSourceUpdate,
    current_user: User = Depends(require_editor),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceResponse]:
    """Update a data source."""
    source = await service.update_source(source_id, data.model_dump(exclude_unset=True))
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    return BaseResponse.ok(data=source)


@router.delete("/{source_id}", response_model=BaseResponse[dict])
async def delete_data_source(
    source_id: UUID,
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[dict]:
    """
    Delete a data source. Requires admin role.
    
    Returns error if data source is used by any agent configurations.
    """
    result = await service.delete_source(source_id)
    
    if not result.get("success"):
        error_msg = result.get("error", "Data source not found")
        dependent_agents = result.get("dependent_agents", [])
        
        if dependent_agents:
            # Return 409 Conflict when data source is in use
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": error_msg,
                    "reason": f"This data source is currently linked to the following agents: {', '.join(dependent_agents)}. Please reconfigure these agents before deleting.",
                    "dependent_agents": dependent_agents,
                    "dependent_config_count": result.get("dependent_config_count", 0),
                }
            )
        else:
            raise HTTPException(status_code=404, detail=error_msg)
    
    return BaseResponse.ok(message="Data source deleted successfully")


# ==========================================
# Connection Testing
# ==========================================

@router.post("/test-connection", response_model=BaseResponse[TestConnectionResponse])
async def test_database_connection(
    data: TestConnectionRequest,
    current_user: User = Depends(require_editor),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[TestConnectionResponse]:
    """Test a database connection before saving."""
    result = await service.test_connection(data.db_url, data.db_engine_type)
    return BaseResponse.ok(data=TestConnectionResponse(**result))


# ==========================================
# File Ingestion Endpoints
# ==========================================

SUPPORTED_EXTENSIONS = {'.csv', '.xlsx', '.pdf', '.json'}
SQL_SUPPORTED_EXTENSIONS = {'.csv', '.xlsx'}
MAX_PREVIEW_DOCS = 50
MAX_CONTENT_LENGTH = 500
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB


@router.post("/upload", response_model=BaseResponse[IngestionResponse], status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Query(None, description="Optional title for the data source"),
    description: Optional[str] = Query(None, description="Optional description"),
    current_user: User = Depends(require_editor),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[IngestionResponse]:
    """
    Upload a file and process it for SQL queries and RAG.
    
    Supports: .csv, .xlsx, .pdf, .json
    
    For CSV/Excel files:
    - Creates DuckDB table for SQL queries
    - Small files (<10MB): Processed immediately
    - Large files (≥10MB): Background processing
    
    Returns document previews for RAG indexing.
    """
    import os
    import tempfile
    import shutil
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )
    
    # Create temp directory
    tmp_dir = tempfile.mkdtemp(prefix="ingestion_")
    tmp_path = os.path.join(tmp_dir, file.filename)
    
    table_name = None
    columns = None
    column_details = None
    row_count = None
    processing_mode = None
    message = None
    data_source_id = None
    
    try:
        # Stream file to disk
        file_size = 0
        with open(tmp_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
                file_size += len(chunk)
        
        file_type = ext.lstrip('.')
        
        # Process file
        if ext in SQL_SUPPORTED_EXTENSIONS:
            if file_size >= LARGE_FILE_THRESHOLD:
                processing_mode = "background"
                from app.modules.data_sources.utils import (
                    normalize_table_name,
                    extract_file_columns_fast,
                    get_file_row_count_estimate,
                    get_user_data_dir,
                )
                
                table_name = normalize_table_name(file.filename)
                row_count = get_file_row_count_estimate(tmp_path, file_type)
                
                # Extract columns BEFORE background processing so frontend can display them
                columns, column_details = extract_file_columns_fast(tmp_path, file_type)
                
                # Copy to permanent location for background processing
                permanent_source = get_user_data_dir(str(current_user.id)) / f"_source_{file.filename}"
                shutil.copy(tmp_path, permanent_source)
                
                # Schedule background processing
                from app.modules.data_sources.utils import process_file_for_duckdb
                background_tasks.add_task(
                    process_file_for_duckdb,
                    user_id=str(current_user.id),
                    table_name=table_name,
                    source_path=str(permanent_source),
                    file_type=file_type,
                    original_filename=file.filename,
                )
                
                message = f"Large file ({file_size / (1024*1024):.1f} MB). Processing in background. {len(columns)} columns detected."
                
                # Create data source record with duckdb_file_path
                import json
                from app.modules.data_sources.utils import get_user_duckdb_path
                duckdb_path = str(get_user_duckdb_path(str(current_user.id)))
                
                ds = await service.create_file_source(
                    title=title or file.filename,
                    original_file_path=str(permanent_source),
                    file_type=file_type,
                    description=description,
                    duckdb_file_path=duckdb_path,
                    duckdb_table_name=table_name,
                    columns_json=json.dumps(columns) if columns else None,
                    row_count=row_count,
                    created_by=current_user.id,
                )
                data_source_id = ds.id
            else:
                processing_mode = "sync"
                result = await service.ingest_file(
                    file_path=tmp_path,
                    original_filename=file.filename,
                    file_type=file_type,
                    user_id=str(current_user.id),
                    title=title,
                    description=description,
                    process_sync=True,
                )
                
                if result["status"] == "error":
                    message = result.get("error")
                else:
                    table_name = result.get("table_name")
                    columns = result.get("columns")
                    column_details = result.get("column_details")
                    row_count = result.get("row_count")
                    data_source_id = UUID(result["data_source_id"]) if result.get("data_source_id") else None
        else:
            # Non-SQL files - just create data source
            ds = await service.create_file_source(
                title=title or file.filename,
                original_file_path=tmp_path,
                file_type=file_type,
                description=description,
                created_by=current_user.id,
            )
            data_source_id = ds.id
            processing_mode = "sync"
        
        # Extract document previews for RAG
        documents: List[ExtractedDocument] = []
        total = 0
        
        # TODO: Integrate with document extractor for RAG previews
        # For now, return empty documents - RAG integration to be added
        
        return BaseResponse.ok(data=IngestionResponse(
            status="success",
            file_name=file.filename,
            file_type=file_type,
            total_documents=total,
            documents=documents,
            table_name=table_name,
            columns=columns,
            column_details=column_details,
            row_count=row_count,
            processing_mode=processing_mode,
            message=message,
            data_source_id=data_source_id,
        ))
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(exc)}")
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


@router.get("/sql/tables", response_model=BaseResponse[FileTablesResponse])
async def list_sql_tables(
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[FileTablesResponse]:
    """List all uploaded file tables available for SQL querying."""
    result = await service.get_sql_tables(str(current_user.id))
    tables = [FileTableInfo(**t) for t in result.get("tables", [])]
    return BaseResponse.ok(data=FileTablesResponse(tables=tables))


@router.post("/sql/query", response_model=BaseResponse[SQLQueryResponse])
async def execute_sql_query(
    request: SQLQueryRequest,
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[SQLQueryResponse]:
    """
    Execute SQL query against uploaded file data using DuckDB.
    
    Supports millions of rows without loading into RAM.
    Only SELECT queries allowed for security.
    
    Example queries:
    - SELECT * FROM your_table LIMIT 10
    - SELECT AVG(age), gender FROM patients GROUP BY gender
    """
    result = await service.execute_sql(str(current_user.id), request.query)
    return BaseResponse.ok(data=SQLQueryResponse(**result))


@router.get("/sql/schema/{table_name}", response_model=BaseResponse[TableSchemaResponse])
async def get_table_schema(
    table_name: str,
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[TableSchemaResponse]:
    """Get the schema (columns and types) of a specific table."""
    result = await service.get_sql_table_schema(str(current_user.id), table_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
    return BaseResponse.ok(data=TableSchemaResponse(
        table_name=result["table_name"],
        columns=[TableSchemaColumn(**col) for col in result["schema"]],
    ))


@router.delete("/sql/tables/{table_name}", response_model=BaseResponse[dict])
async def delete_sql_table(
    table_name: str,
    current_user: User = Depends(require_editor),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[dict]:
    """Delete an uploaded file table and its CSV data."""
    deleted = await service.delete_sql_table(str(current_user.id), table_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
    return BaseResponse.ok(message=f"Table '{table_name}' deleted.")


@router.delete("/sql/tables", response_model=BaseResponse[dict])
async def delete_all_sql_tables(
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[dict]:
    """Delete all uploaded file tables and data."""
    await service.delete_all_sql_tables(str(current_user.id))
    return BaseResponse.ok(message="All tables deleted.")
