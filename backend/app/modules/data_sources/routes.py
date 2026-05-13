"""
API routes for data source management.

Provides endpoints for:
- Database connection management
- File-based source management
- File upload and ingestion (DuckDB processing)
- SQL query execution
- Connection testing
"""
import logging
from typing import Optional, List, Dict
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, Query, status,
    File, UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import get_current_user, require_admin
from app.core.models.common import BaseResponse
from app.modules.audit.helpers import AuditLogger, get_audit_logger
from app.modules.audit.schemas import AuditAction
from app.modules.users.schemas import User
from app.core.settings import get_settings
from app.modules.data_sources.service import DataSourceService
from app.modules.data_sources.utils import decode_db_url
from app.modules.data_sources.schemas import (
    DatabaseSourceCreate, DataSourceUpdate,
    DataSourceResponse, DataSourceListResponse,
    TestConnectionRequest, TestConnectionResponse,
    # Ingestion schemas
    IngestionResponse, ExtractedDocument,
    SQLQueryRequest, SQLQueryResponse,
    FileTablesResponse, FileTableInfo,
    TableSchemaResponse, TableSchemaColumn,
    DataSourceSchemaResponse, DataSourcePreviewResponse,
)

logger = logging.getLogger(__name__)


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
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[DataSourceResponse]:
    """Create a database connection data source."""
    # Decode URL if it was base64 encoded
    db_url = data.db_url
    if data.is_encoded:
        try:
            db_url = decode_db_url(data.db_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    try:
        source = await service.create_database_source(
            title=data.title,
            db_url=db_url,
            db_engine_type=data.db_engine_type,
            description=data.description,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    
    # Audit log: datasource.created
    await audit.log(
        action=AuditAction.DATASOURCE_CREATED,
        actor=current_user,
        resource_type="datasource",
        resource_id=str(source.id),
        resource_name=source.title,
        details={
            "type": "database",
            "engine": data.db_engine_type,
            "created_by": current_user.username
        },
    )
    
    return BaseResponse.ok(data=source)


# ==========================================
# List/Get Endpoints
# ==========================================

@router.get("", response_model=BaseResponse[DataSourceListResponse])
async def list_data_sources(
    query: Optional[str] = Query(None, description="Search in title/description"),
    source_type: Optional[str] = Query(None, pattern="^(database|file)$"),
    status: Optional[str] = Query(None, pattern="^(pending|processing|completed|failed)$", description="Filter by processing status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[DataSourceListResponse]:
    """List data sources with optional filters."""
    result = await service.list_sources(
        query=query,
        source_type=source_type,
        processing_status=status,
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


@router.get("/{source_id}/progress", summary="Long-polling progress endpoint")
async def get_processing_progress(
    source_id: UUID,
    known_status: Optional[str] = Query(None, description="Client's current known status"),
    known_progress: Optional[int] = Query(None, description="Client's current known progress"),
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_data_source_service),
):
    """
    Long-polling endpoint for processing progress.
    
    Waits for status/progress to change from known values (timeout from config).
    Returns immediately if status differs from known_status or progress differs from known_progress.
    
    Use this instead of interval polling for efficient real-time updates.
    """
    settings = get_settings()
    
    progress_data = await service.get_processing_progress(
        source_id=source_id,
        known_status=known_status,
        known_progress=known_progress,
        timeout_seconds=settings.long_polling_timeout_seconds,
    )
    
    if progress_data is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    return BaseResponse.ok(data=progress_data)


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
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[DataSourceResponse]:
    """
    Update a data source.
    
    Title and description can always be updated.
    Other fields (db_url, db_engine_type, file paths, etc.) can only be updated
    if the data source is not used by any active configuration.
    """
    update_data = data.model_dump(exclude_unset=True)
    
    # Fields that are safe to update even when in use
    safe_fields = {"title", "description"}
    requested_fields = set(update_data.keys())
    critical_fields = requested_fields - safe_fields
    
    # Only check active config constraint if updating critical fields
    if critical_fields:
        is_in_use = await service.is_used_by_active_config(source_id)
        if is_in_use:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot update critical fields ({', '.join(critical_fields)}) while data source is used by an active configuration. Deactivate the configuration first, or only update title/description."
            )
    
    source = await service.update_source(source_id, update_data)
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")
    
    # Audit log: datasource.updated
    await audit.log(
        action=AuditAction.DATASOURCE_UPDATED,
        actor=current_user,
        resource_type="datasource",
        resource_id=str(source_id),
        resource_name=source.title,
        details={
            "fields_changed": list(update_data.keys()),
            "updated_by": current_user.username
        },
    )
    
    return BaseResponse.ok(data=source)


@router.delete("/{source_id}", response_model=BaseResponse[dict])
async def delete_data_source(
    source_id: UUID,
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[dict]:
    """
    Delete a data source. Requires admin role.
    
    Returns error if data source is used by any agent configurations.
    """
    # Get source info before deletion for audit log
    source = await service.get_source(source_id)
    source_name = source.title if source else str(source_id)
    
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
    
    # Audit log: datasource.deleted
    await audit.log(
        action=AuditAction.DATASOURCE_DELETED,
        actor=current_user,
        resource_type="datasource",
        resource_id=str(source_id),
        resource_name=source_name,
        details={
            "deleted_by": current_user.username
        },
    )
    
    return BaseResponse.ok(message="Data source deleted successfully")


# ==========================================
# Connection Testing
# ==========================================

@router.post("/test-connection", response_model=BaseResponse[TestConnectionResponse])
async def test_database_connection(
    data: TestConnectionRequest,
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
) -> BaseResponse[TestConnectionResponse]:
    """Test a database connection before saving."""
    # Decode URL if it was base64 encoded
    db_url = data.db_url
    if data.is_encoded:
        try:
            db_url = decode_db_url(data.db_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    result = await service.test_connection(db_url, data.db_engine_type)
    return BaseResponse.ok(data=TestConnectionResponse(**result))


# ==========================================
# File Ingestion Endpoints
# ==========================================

SUPPORTED_EXTENSIONS = {'.csv', '.xlsx'}
MAX_PREVIEW_DOCS = 50
MAX_CONTENT_LENGTH = 500


@router.post("/upload", response_model=BaseResponse[IngestionResponse], status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    title: Optional[str] = Query(None, description="Optional title for the data source"),
    description: Optional[str] = Query(None, description="Optional description"),
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_data_source_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> BaseResponse[IngestionResponse]:
    """
    Upload a CSV or Excel file for SQL queries.
    
    Supported formats: .csv, .xlsx
    
    - Creates DuckDB table for SQL queries
    - Uses background processing for fast response
    - Column info extracted immediately for display
    
    Returns data source info with columns detected.
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
    
    # Create temp directory and stream file to disk
    tmp_dir = tempfile.mkdtemp(prefix="ingestion_")
    tmp_path = os.path.join(tmp_dir, file.filename)
    
    try:
        # Stream file to disk
        file_size = 0
        with open(tmp_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
                file_size += len(chunk)
        
        file_type = ext.lstrip('.')
        
        # Delegate to service layer for all business logic
        result = await service.ingest_uploaded_file(
            temp_file_path=tmp_path,
            original_filename=file.filename,
            file_type=file_type,
            file_size=file_size,
            title=title,
            description=description,
            created_by=current_user.id,
        )
        
        # Audit log: datasource.created (for file uploads)
        await audit.log(
            action=AuditAction.DATASOURCE_CREATED,
            actor=current_user,
            resource_type="datasource",
            resource_id=str(result["data_source_id"]),
            resource_name=title or file.filename,
            details={
                "type": "file",
                "file_type": file_type,
                "file_name": file.filename,
                "processing_mode": "background",
                "created_by": current_user.username,
            },
        )
        
        return BaseResponse.ok(data=IngestionResponse(
            status="success",
            file_name=file.filename,
            file_type=file_type,
            total_documents=0,  # Not used for CSV/Excel
            documents=[],
            table_name=result["table_name"],
            columns=result["columns"],
            column_details=result["column_details"],
            row_count=result["row_count"],
            processing_mode="background",
            message=result["message"],
            data_source_id=result["data_source_id"],
        ))
        
    except HTTPException:
        raise
    except ValueError as e:
        # Duplicate title error
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
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
    current_user: User = Depends(require_admin),
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
