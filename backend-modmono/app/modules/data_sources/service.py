"""
Business logic for data source management.
"""
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.data_sources.repository import DataSourceRepository
from app.modules.data_sources.schemas import (
    DataSourceResponse, DataSourceListResponse
)


class DataSourceService:
    """Service for data source management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DataSourceRepository(db)
    
    async def create_database_source(
        self,
        title: str,
        db_url: str,
        db_engine_type: str,
        description: Optional[str] = None,
        created_by: Optional[UUID] = None,
    ) -> DataSourceResponse:
        """Create a database connection data source."""
        data = {
            "title": title,
            "description": description,
            "source_type": "database",
            "db_url": db_url,
            "db_engine_type": db_engine_type,
        }
        source = await self.repo.create(data, created_by)
        return DataSourceResponse.model_validate(source)
    
    async def create_file_source(
        self,
        title: str,
        original_file_path: str,
        file_type: str,
        description: Optional[str] = None,
        duckdb_file_path: Optional[str] = None,
        duckdb_table_name: Optional[str] = None,
        columns_json: Optional[str] = None,
        row_count: Optional[int] = None,
        created_by: Optional[UUID] = None,
    ) -> DataSourceResponse:
        """Create a file-based data source."""
        data = {
            "title": title,
            "description": description,
            "source_type": "file",
            "original_file_path": original_file_path,
            "file_type": file_type,
            "duckdb_file_path": duckdb_file_path,
            "duckdb_table_name": duckdb_table_name,
            "columns_json": columns_json,
            "row_count": row_count,
        }
        source = await self.repo.create(data, created_by)
        return DataSourceResponse.model_validate(source)
    
    async def get_source(self, source_id: UUID) -> Optional[DataSourceResponse]:
        """Get data source by ID."""
        source = await self.repo.get_by_id(source_id)
        if source:
            return DataSourceResponse.model_validate(source)
        return None
    
    async def get_source_model(self, source_id: UUID):
        """Get raw data source model (for internal use)."""
        return await self.repo.get_by_id(source_id)
    
    async def update_source(
        self,
        source_id: UUID,
        data: Dict[str, Any],
    ) -> Optional[DataSourceResponse]:
        """Update a data source."""
        source = await self.repo.update(source_id, data)
        if source:
            return DataSourceResponse.model_validate(source)
        return None
    
    async def delete_source(self, source_id: UUID) -> Dict[str, Any]:
        """
        Delete a data source.
        
        Returns:
            Dict with 'success' bool and optional 'error' message.
            If agent configs reference this source, returns list of dependent agents.
        """
        from app.modules.agents.models import AgentConfigModel, AgentModel
        
        # Check if any agent configs reference this data source
        query = (
            select(AgentConfigModel, AgentModel.title)
            .join(AgentModel, AgentConfigModel.agent_id == AgentModel.id)
            .where(AgentConfigModel.data_source_id == source_id)
        )
        result = await self.db.execute(query)
        dependent_configs = result.all()
        
        if dependent_configs:
            # Build list of dependent agents for error message
            agent_names = list(set(row[1] for row in dependent_configs))
            return {
                "success": False,
                "error": f"Cannot delete data source: it is used by {len(dependent_configs)} agent configuration(s)",
                "dependent_agents": agent_names,
                "dependent_config_count": len(dependent_configs),
            }
        
        # Safe to delete
        deleted = await self.repo.delete(source_id)
        return {"success": deleted}
    
    async def list_sources(
        self,
        query: Optional[str] = None,
        source_type: Optional[str] = None,
        created_by: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> DataSourceListResponse:
        """List data sources with filters."""
        sources, total = await self.repo.search(
            query=query,
            source_type=source_type,
            created_by=created_by,
            skip=skip,
            limit=limit,
        )
        return DataSourceListResponse(
            data_sources=[DataSourceResponse.model_validate(s) for s in sources],
            total=total,
            skip=skip,
            limit=limit,
        )
    
    async def test_connection(self, db_url: str, db_engine_type: str) -> Dict[str, Any]:
        """Test a database connection."""
        from sqlalchemy import create_engine, text
        
        try:
            engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
            with engine.connect() as conn:
                # Test connection
                conn.execute(text("SELECT 1"))
                
                # Get table list
                tables = []
                if "postgresql" in db_engine_type:
                    result = conn.execute(text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                    ))
                    tables = [row[0] for row in result]
                elif "mysql" in db_engine_type:
                    result = conn.execute(text("SHOW TABLES"))
                    tables = [row[0] for row in result]
                elif "sqlite" in db_engine_type:
                    result = conn.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ))
                    tables = [row[0] for row in result]
            
            return {
                "success": True,
                "message": "Connection successful",
                "tables": tables,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "message": "Connection failed",
                "tables": None,
                "error": str(e),
            }
    
    async def get_schema(self, source_id: UUID) -> Dict[str, Any]:
        """
        Get schema (tables and columns) for a data source.
        
        Used in Step 2 of config wizard to show available tables/columns for selection.
        Includes primary key and foreign key information for databases.
        """
        import json
        from sqlalchemy import create_engine, inspect
        
        source = await self.repo.get_by_id(source_id)
        if not source:
            raise ValueError(f"Data source {source_id} not found")
        
        source_type = source.source_type
        tables_info = []
        relationships = []  # Foreign key relationships between tables
        
        if source_type == "database":
            # Fetch schema from database connection
            if not source.db_url:
                raise ValueError("Database URL not configured")
            
            # Normalize common typos in database URL dialects
            db_url = source.db_url
            db_url = db_url.replace("postgressql://", "postgresql://")
            db_url = db_url.replace("postgress://", "postgresql://")
            db_url = db_url.replace("postgres://", "postgresql://")
            
            try:
                engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
                inspector = inspect(engine)
                
                try:
                    table_names = inspector.get_table_names()
                except Exception as e:
                    # Fallback for table names if inspector fails
                    if "postgresql" in source.db_engine_type.lower():
                        from sqlalchemy import text
                        with engine.connect() as conn:
                            result = conn.execute(text(
                                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                            ))
                            table_names = [row[0] for row in result]
                    else:
                        raise e
                
                for table_name in table_names:
                    # Get primary key columns
                    pk_columns = set()
                    try:
                        pk_constraint = inspector.get_pk_constraint(table_name)
                        pk_columns = set(pk_constraint.get("constrained_columns", []) if pk_constraint else [])
                    except Exception:
                        # PK info is optional for reflection
                        pass
                    
                    # Get foreign keys for this table
                    fk_columns = {}  # column_name -> referenced table info
                    try:
                        foreign_keys = inspector.get_foreign_keys(table_name)
                        for fk in foreign_keys:
                            ref_table = fk.get("referred_table")
                            ref_columns = fk.get("referred_columns", [])
                            constrained_columns = fk.get("constrained_columns", [])
                            
                            for i, col in enumerate(constrained_columns):
                                fk_columns[col] = {
                                    "referenced_table": ref_table,
                                    "referenced_column": ref_columns[i] if i < len(ref_columns) else None,
                                }
                            
                            # Add to relationships list
                            if ref_table and constrained_columns:
                                relationships.append({
                                    "from_table": table_name,
                                    "from_columns": constrained_columns,
                                    "to_table": ref_table,
                                    "to_columns": ref_columns,
                                })
                    except Exception:
                        # FK info is optional for reflection
                        pass
                    
                    columns = []
                    try:
                        raw_columns = inspector.get_columns(table_name)
                    except Exception as e:
                        # Fallback for column reflection if inspector fails (e.g. pg_collation permissions)
                        if "postgresql" in source.db_engine_type.lower():
                            from sqlalchemy import text
                            with engine.connect() as conn:
                                query = text("""
                                    SELECT column_name, data_type, is_nullable
                                    FROM information_schema.columns
                                    WHERE table_name = :table AND table_schema = 'public'
                                """)
                                res = conn.execute(query, {"table": table_name})
                                raw_columns = [
                                    {
                                        "name": row[0],
                                        "type": row[1],
                                        "nullable": row[2] == 'YES'
                                    } for row in res
                                ]
                        else:
                            raise e

                    for col in raw_columns:
                        col_name = col["name"]
                        col_info = {
                            "column_name": col_name,
                            "data_type": str(col["type"]),
                            "is_nullable": col.get("nullable", True),
                            "is_primary_key": col_name in pk_columns,
                        }
                        
                        # Add foreign key info if applicable
                        if col_name in fk_columns:
                            col_info["foreign_key"] = fk_columns[col_name]
                        
                        columns.append(col_info)
                    
                    tables_info.append({
                        "table_name": table_name,
                        "columns": columns,
                        "primary_key_columns": list(pk_columns),
                    })
                
                engine.dispose()
                
            except Exception as e:
                # Log the actual error for debugging
                import logging
                logging.error(f"Schema reflection error: {str(e)}")
                raise ValueError(f"Failed to fetch database schema: {str(e)}")
        
        elif source_type == "file":
            # For file sources, parse columns from columns_json, duckdb, or original file
            table_name = source.duckdb_table_name or source.title or "data"
            columns = []
            
            if source.columns_json:
                # Parse stored column info
                try:
                    col_list = json.loads(source.columns_json)
                    for col_name in col_list:
                        columns.append({
                            "column_name": col_name,
                            "data_type": "string",  # Default type
                            "is_nullable": True,
                            "is_primary_key": False,
                            "foreign_key": None,
                        })
                except json.JSONDecodeError:
                    pass
            
            if not columns and source.duckdb_file_path:
                # Try to get schema from DuckDB
                try:
                    import duckdb
                    conn = duckdb.connect(source.duckdb_file_path, read_only=True)
                    result = conn.execute(f"DESCRIBE {table_name}").fetchall()
                    for row in result:
                        columns.append({
                            "column_name": row[0],
                            "data_type": row[1],
                            "is_nullable": row[2] == "YES" if len(row) > 2 else True,
                            "is_primary_key": False,
                            "foreign_key": None,
                        })
                    conn.close()
                except Exception:
                    pass  # Fall back to original file
            
            # Fallback: Extract columns directly from original file
            if not columns and source.original_file_path:
                try:
                    from app.modules.data_sources.utils import extract_file_columns_fast
                    col_names, col_details = extract_file_columns_fast(
                        source.original_file_path, 
                        source.file_type or "csv"
                    )
                    for i, col_name in enumerate(col_names):
                        col_type = col_details[i].get("type", "VARCHAR") if i < len(col_details) else "VARCHAR"
                        columns.append({
                            "column_name": col_name,
                            "data_type": col_type,
                            "is_nullable": True,
                            "is_primary_key": False,
                            "foreign_key": None,
                        })
                except Exception as e:
                    import logging
                    logging.warning(f"Failed to extract columns from original file: {e}")
            
            tables_info.append({
                "table_name": table_name,
                "columns": columns,
                "primary_key_columns": [],  # Files don't have PKs
            })
        
        # Extract file name from path
        file_name = None
        if source.original_file_path:
            file_name = source.original_file_path.split("/")[-1].split("\\")[-1]
        
        return {
            "source_type": source_type,
            "tables": tables_info,
            "relationships": relationships,
            "file_name": file_name,
            "row_count": source.row_count,
        }

    async def get_preview(self, source_id: UUID, limit: int = 10) -> Dict[str, Any]:
        """
        Get sample data preview for a data source.
        
        Returns sample rows formatted as documents for preview display.
        """
        import json
        
        source = await self.repo.get_by_id(source_id)
        if not source:
            raise ValueError(f"Data source {source_id} not found")
        
        if source.source_type != "file":
            # Only file sources support preview for now
            return {
                "source_type": source.source_type,
                "documents": [],
                "total_documents": 0,
            }
        
        # Extract file name from path
        file_name = None
        if source.original_file_path:
            file_name = source.original_file_path.split("/")[-1].split("\\")[-1]
        
        table_name = source.duckdb_table_name or "data"
        columns = []
        column_details = []
        documents = []
        total_documents = source.row_count or 0
        
        # Parse columns
        if source.columns_json:
            try:
                col_list = json.loads(source.columns_json)
                for col in col_list:
                    if isinstance(col, dict):
                        columns.append(col.get("name", str(col)))
                        column_details.append(col)
                    else:
                        columns.append(str(col))
                        column_details.append({"name": str(col), "type": "VARCHAR"})
            except json.JSONDecodeError:
                pass
        
        # Fetch sample rows from DuckDB
        if source.duckdb_file_path:
            try:
                import duckdb
                conn = duckdb.connect(source.duckdb_file_path, read_only=True)
                
                # Get columns if not already loaded
                if not columns:
                    result = conn.execute(f"DESCRIBE {table_name}").fetchall()
                    for row in result:
                        columns.append(row[0])
                        column_details.append({"name": row[0], "type": row[1]})
                
                # Fetch sample rows
                rows = conn.execute(f"SELECT * FROM {table_name} LIMIT {limit}").fetchall()
                
                for row in rows:
                    # Format row as document content
                    content_parts = []
                    metadata = {}
                    for i, col in enumerate(columns):
                        value = row[i] if i < len(row) else None
                        if value is not None:
                            content_parts.append(f"{col}: {value}")
                            metadata[col] = str(value) if value is not None else None
                    
                    documents.append({
                        "page_content": "\n".join(content_parts),
                        "metadata": metadata,
                    })
                
                conn.close()
            except Exception as e:
                # Log error but continue with empty documents
                import logging
                logging.warning(f"Failed to fetch preview from DuckDB: {e}")
        
        return {
            "source_type": source.source_type,
            "file_name": file_name,
            "table_name": table_name,
            "columns": columns,
            "column_details": column_details,
            "row_count": source.row_count,
            "documents": documents,
            "total_documents": total_documents,
        }

    # ==========================================
    # File Ingestion Methods
    # ==========================================
    
    async def ingest_file(
        self,
        file_path: str,
        original_filename: str,
        file_type: str,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        process_sync: bool = True,
    ) -> Dict[str, Any]:
        """
        Ingest a file and create corresponding data source.
        
        For CSV/Excel: Creates DuckDB table for SQL queries
        For all: Returns document previews for RAG
        
        Args:
            file_path: Path to the uploaded file
            original_filename: Original name of uploaded file
            file_type: File extension (csv, xlsx, pdf, json)
            user_id: ID of the user uploading
            title: Optional title (defaults to filename)
            description: Optional description
            process_sync: If True, process immediately. If False, return immediately.
            
        Returns:
            Dict with processing results and data_source_id
        """
        from app.modules.data_sources.utils import (
            normalize_table_name,
            process_file_for_duckdb,
            get_file_row_count_estimate,
        )
        
        table_name = None
        columns = None
        column_details = None
        row_count = None
        duckdb_file_path = None
        csv_path = None
        
        # Process for SQL support (CSV and Excel)
        sql_supported = {'csv', 'xlsx'}
        
        if file_type.lower() in sql_supported:
            table_name = normalize_table_name(original_filename)
            
            if process_sync:
                try:
                    result = process_file_for_duckdb(
                        user_id=user_id,
                        table_name=table_name,
                        source_path=file_path,
                        file_type=file_type.lower(),
                        original_filename=original_filename,
                    )
                    columns = result["columns"]
                    row_count = result["row_count"]
                    csv_path = result["csv_path"]
                    duckdb_file_path = result["duckdb_path"]
                    
                    # Get column types
                    from app.modules.data_sources.utils import get_table_schema
                    schema_info = get_table_schema(user_id, table_name)
                    if schema_info:
                        column_details = [
                            {"name": col["column_name"], "type": col["data_type"]}
                            for col in schema_info
                        ]
                except Exception as e:
                    return {
                        "status": "error",
                        "error": f"SQL processing failed: {str(e)}",
                        "data_source_id": None,
                    }
            else:
                row_count = get_file_row_count_estimate(file_path, file_type.lower())
        
        # Create data source record
        import json
        from uuid import UUID
        
        data_source = await self.create_file_source(
            title=title or original_filename,
            original_file_path=file_path,
            file_type=file_type.lower(),
            description=description,
            duckdb_file_path=duckdb_file_path,
            duckdb_table_name=table_name,
            columns_json=json.dumps(columns) if columns else None,
            row_count=row_count,
            created_by=UUID(user_id) if user_id else None,
        )
        
        return {
            "status": "success",
            "data_source_id": str(data_source.id),
            "table_name": table_name,
            "columns": columns,
            "column_details": column_details,
            "row_count": row_count,
            "csv_path": csv_path,
            "duckdb_path": duckdb_file_path,
        }
    
    async def execute_sql(
        self,
        user_id: str,
        query: str,
        max_rows: int = 10000,
    ) -> Dict[str, Any]:
        """
        Execute SQL query against user's uploaded files via DuckDB.
        
        Only SELECT queries are allowed for security.
        """
        from app.modules.data_sources.utils import execute_duckdb_query
        
        query = query.strip()
        query_upper = query.upper()
        
        # Security: Only allow SELECT and WITH (CTEs)
        if not (query_upper.startswith("SELECT") or query_upper.startswith("WITH")):
            return {
                "status": "error",
                "query": query,
                "row_count": 0,
                "columns": [],
                "rows": [],
                "error": "Only SELECT queries are allowed for security.",
            }
        
        result = execute_duckdb_query(user_id, query, max_rows)
        result["query"] = query
        return result
    
    async def get_sql_tables(self, user_id: str) -> Dict[str, Any]:
        """List all SQL tables available for a user."""
        from app.modules.data_sources.utils import list_duckdb_tables
        
        tables = list_duckdb_tables(user_id)
        return {"tables": tables}
    
    async def get_sql_table_schema(
        self,
        user_id: str,
        table_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Get schema for a specific table."""
        from app.modules.data_sources.utils import get_table_schema
        
        schema = get_table_schema(user_id, table_name)
        if schema:
            return {"table_name": table_name, "schema": schema}
        return None
    
    async def delete_sql_table(
        self,
        user_id: str,
        table_name: str,
    ) -> bool:
        """Delete a SQL table and its data."""
        from app.modules.data_sources.utils import delete_duckdb_table
        return delete_duckdb_table(user_id, table_name)
    
    async def delete_all_sql_tables(self, user_id: str) -> bool:
        """Delete all SQL tables for a user."""
        from app.modules.data_sources.utils import delete_all_user_tables
        return delete_all_user_tables(user_id)
