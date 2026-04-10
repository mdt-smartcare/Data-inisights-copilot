"""
Ingestion API routes - Compatibility layer for frontend.

Maps /ingestion/* endpoints to the data sources service.
This provides backward compatibility with the frontend while using
the unified data sources architecture.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, BackgroundTasks

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session as get_db
from app.core.auth.permissions import get_current_user, require_editor, require_admin
from app.core.models.common import BaseResponse
from app.modules.users.schemas import User
from app.modules.data_sources.service import DataSourceService
from app.modules.data_sources.schemas import (
    IngestionResponse, ExtractedDocument,
    SQLQueryRequest, SQLQueryResponse,
    FileTablesResponse, FileTableInfo,
    TableSchemaResponse, TableSchemaColumn,
)


router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


def get_service(db: AsyncSession = Depends(get_db)) -> DataSourceService:
    return DataSourceService(db)


# ==========================================
# SQL Tables Endpoints (compatibility layer)
# ==========================================

@router.get("/sql/tables", response_model=BaseResponse[FileTablesResponse])
async def list_sql_tables(
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_service),
) -> BaseResponse[FileTablesResponse]:
    """List all uploaded file tables available for SQL querying."""
    result = await service.get_sql_tables(str(current_user.id))
    tables = [FileTableInfo(**t) for t in result.get("tables", [])]
    return BaseResponse.ok(data=FileTablesResponse(tables=tables))


@router.post("/sql/query", response_model=BaseResponse[SQLQueryResponse])
async def execute_sql_query(
    request: SQLQueryRequest,
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_service),
) -> BaseResponse[SQLQueryResponse]:
    """Execute SQL query against uploaded file data using DuckDB."""
    result = await service.execute_sql(str(current_user.id), request.query)
    return BaseResponse.ok(data=SQLQueryResponse(**result))


@router.get("/sql/schema/{table_name}", response_model=BaseResponse[TableSchemaResponse])
async def get_table_schema(
    table_name: str,
    current_user: User = Depends(get_current_user),
    service: DataSourceService = Depends(get_service),
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
    service: DataSourceService = Depends(get_service),
) -> BaseResponse[dict]:
    """Delete an uploaded file table and its CSV data."""
    deleted = await service.delete_sql_table(str(current_user.id), table_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
    return BaseResponse.ok(message=f"Table '{table_name}' deleted.")


@router.delete("/sql/tables", response_model=BaseResponse[dict])
async def delete_all_sql_tables(
    current_user: User = Depends(require_admin),
    service: DataSourceService = Depends(get_service),
) -> BaseResponse[dict]:
    """Delete all uploaded file tables and data."""
    await service.delete_all_sql_tables(str(current_user.id))
    return BaseResponse.ok(message="All tables deleted.")
