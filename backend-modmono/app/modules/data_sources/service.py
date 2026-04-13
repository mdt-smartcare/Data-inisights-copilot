"""
Business logic for data source management.
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import select, create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.data_sources.repository import DataSourceRepository
from app.modules.data_sources.schemas import (
    DataSourceResponse, DataSourceListResponse
)


class DataSourceService:
    """Service for data source management."""
    
    # Class-level cache for database schemas to avoid redundant slow lookups
    # Maps source_id -> (timestamp, schema_data)
    _schema_cache = {}
    _CACHE_TTL = 300  # 5 minutes cache TTL
    
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
        
        For file sources, also cleans up:
        - Original uploaded file
        - DuckDB table and associated CSV file
        
        Returns:
            Dict with 'success' bool and optional 'error' message.
            If agent configs reference this source, returns list of dependent agents.
        """
        import os
        from app.modules.agents.models import AgentConfigModel, AgentModel
        
        # Get the source first to access file paths for cleanup
        source = await self.repo.get_by_id(source_id)
        if not source:
            return {"success": False, "error": "Data source not found"}
        
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
        
        # Clean up files for file data sources
        if source.source_type == "file":
            # Delete DuckDB table (and associated CSV) if exists
            if source.duckdb_table_name and source.created_by:
                from app.modules.data_sources.utils import delete_duckdb_table
                delete_duckdb_table(str(source.created_by), source.duckdb_table_name)
            
            # Delete original uploaded file if exists
            if source.original_file_path and os.path.exists(source.original_file_path):
                try:
                    os.remove(source.original_file_path)
                except Exception:
                    pass  # Best effort cleanup
        
        # Delete the database record
        deleted = await self.repo.delete(source_id)
        return {"success": deleted}
    
    async def is_used_by_active_config(self, source_id: UUID) -> bool:
        """
        Check if data source is used by any active agent configuration.
        
        Used to prevent updates to data sources that are actively in use.
        
        Returns:
            True if used by at least one active config, False otherwise.
        """
        from app.modules.agents.models import AgentConfigModel
        
        query = (
            select(AgentConfigModel.id)
            .where(AgentConfigModel.data_source_id == source_id)
            .where(AgentConfigModel.is_active == True)
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar() is not None
    
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
        # Check cache first
        now = time.time()
        if source_id in self._schema_cache:
            timestamp, cached_schema = self._schema_cache[source_id]
            if now - timestamp < self._CACHE_TTL:
                return cached_schema

        source = await self.repo.get_by_id(source_id)
        if not source:
            raise ValueError(f"Data source {source_id} not found")
        
        source_type = source.source_type
        
        if source_type == "database":
            # Use asyncio.to_thread to run the blocking SQLAlchemy reflection code
            schema_info = await asyncio.to_thread(self._reflect_schema_sync, source)
            
            # Cache the result
            self._schema_cache[source_id] = (time.time(), schema_info)
            return schema_info
            
        # Handle file sources
        tables_info = []
        
        if source_type == "file":
            # For file sources, parse columns from columns_json, duckdb, or original file
            table_name = source.duckdb_table_name or source.title or "data"
            columns = []
            
            if source.columns_json:
                # Parse stored column info
                try:
                    import json
                    col_list = json.loads(source.columns_json)
                    for col_name in col_list:
                        columns.append({
                            "column_name": col_name,
                            "data_type": "string",  # Default type
                            "is_nullable": True,
                            "is_primary_key": False,
                            "foreign_key": None,
                        })
                except Exception:
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
            
        result = {
            "source_type": source_type,
            "title": source.title,
            "file_name": file_name,
            "tables": tables_info,
            "relationships": [],
        }
        
        # Cache the result for file sources too
        self._schema_cache[source_id] = (time.time(), result)
        return result

    def _reflect_schema_sync(self, source, max_tables: int = 500) -> Dict[str, Any]:
        """
        Synchronous helper for schema reflection, intended to run in a threadPool.
        """
        import logging
        import traceback
        
        db_url = source.db_url
        logging.info(f"Starting schema reflection for: {source.title}")
        
        # Normalize common typos in database URL dialects
        db_url = db_url.replace("postgressql://", "postgresql://")
        db_url = db_url.replace("postgress://", "postgresql://")
        db_url = db_url.replace("postgres://", "postgresql://")
        
        # Fix malformed URLs with extra ://
        if "@://" in db_url:
            db_url = db_url.replace("@://", "@")
            logging.warning(f"Fixed malformed URL (removed extra ://)")
        
        tables_info = []
        relationships = []
        total_tables_in_db = 0
        
        try:
            is_postgresql = "postgresql" in source.db_engine_type.lower()
            
            connect_args = {"connect_timeout": 30} if is_postgresql else {}
            
            logging.info(f"Connecting to database...")
            engine = create_engine(db_url, pool_pre_ping=True, pool_size=1, connect_args=connect_args)
            
            with engine.connect() as conn:
                logging.info("Connection established")
                
                if is_postgresql:
                    try:
                        conn.execute(text("SET statement_timeout = '30s'"))
                    except:
                        pass
                    
                    # Count tables
                    count_result = conn.execute(text("""
                        SELECT COUNT(*) FROM information_schema.tables 
                        WHERE table_type = 'BASE TABLE'
                        AND table_schema NOT IN ('pg_catalog', 'information_schema')
                        AND table_schema NOT LIKE 'pg_temp%'
                    """))
                    total_tables_in_db = count_result.scalar() or 0
                    logging.info(f"Total tables found: {total_tables_in_db}")
                    
                    if total_tables_in_db == 0:
                        # List available schemas for debugging
                        schema_result = conn.execute(text("SELECT schema_name FROM information_schema.schemata"))
                        schemas = [r[0] for r in schema_result]
                        logging.info(f"Available schemas: {schemas}")
                        
                        # Try without schema filter
                        alt_count = conn.execute(text("""
                            SELECT COUNT(*) FROM information_schema.tables WHERE table_type = 'BASE TABLE'
                        """))
                        alt_total = alt_count.scalar() or 0
                        logging.info(f"Total tables (no schema filter): {alt_total}")
                    
                    # Get tables
                    result = conn.execute(text("""
                        SELECT table_schema, table_name 
                        FROM information_schema.tables 
                        WHERE table_type = 'BASE TABLE'
                        AND table_schema NOT IN ('pg_catalog', 'information_schema')
                        AND table_schema NOT LIKE 'pg_temp%'
                        ORDER BY table_schema, table_name
                        LIMIT :limit
                    """), {"limit": max_tables})
                    discovered_tables = [(row[0], row[1]) for row in result]
                    logging.info(f"Tables to process: {len(discovered_tables)}")
                    
                    if discovered_tables:
                        # Batch fetch columns
                        all_columns = {}
                        col_result = conn.execute(text("""
                            SELECT table_schema, table_name, column_name, data_type, is_nullable
                            FROM information_schema.columns
                            WHERE (table_schema, table_name) IN (
                                SELECT table_schema, table_name FROM information_schema.tables 
                                WHERE table_type = 'BASE TABLE'
                                AND table_schema NOT IN ('pg_catalog', 'information_schema')
                                AND table_schema NOT LIKE 'pg_temp%'
                                LIMIT :limit
                            )
                            ORDER BY table_schema, table_name, ordinal_position
                        """), {"limit": max_tables})
                        
                        for row in col_result:
                            key = (row[0], row[1])
                            if key not in all_columns:
                                all_columns[key] = []
                            all_columns[key].append({
                                "column_name": row[2],
                                "data_type": row[3],
                                "is_nullable": row[4] == 'YES',
                            })

                        # Batch fetch PRIMARY KEYS
                        pk_result = conn.execute(text("""
                            SELECT kcu.table_schema, kcu.table_name, kcu.column_name
                            FROM information_schema.table_constraints AS tc
                            JOIN information_schema.key_column_usage AS kcu
                              ON tc.constraint_name = kcu.constraint_name
                              AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'PRIMARY KEY'
                            AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                            AND tc.table_schema NOT LIKE 'pg_temp%'
                        """))
                        
                        pk_map = {}
                        for row in pk_result:
                            key = (row[0], row[1])
                            if key not in pk_map:
                                pk_map[key] = set()
                            pk_map[key].add(row[2])

                        # Batch fetch FOREIGN KEYS
                        fk_result = conn.execute(text("""
                            SELECT
                                tc.table_schema, 
                                tc.table_name, 
                                kcu.column_name, 
                                ccu.table_schema AS foreign_table_schema,
                                ccu.table_name AS foreign_table_name,
                                ccu.column_name AS foreign_column_name
                            FROM 
                                information_schema.table_constraints AS tc 
                                JOIN information_schema.key_column_usage AS kcu
                                  ON tc.constraint_name = kcu.constraint_name
                                  AND tc.table_schema = kcu.table_schema
                                JOIN information_schema.constraint_column_usage AS ccu
                                  ON ccu.constraint_name = tc.constraint_name
                                  AND ccu.table_schema = tc.table_schema
                            WHERE tc.constraint_type = 'FOREIGN KEY'
                            AND tc.table_schema NOT IN ('pg_catalog', 'information_schema')
                            AND tc.table_schema NOT LIKE 'pg_temp%'
                        """))
                        
                        fk_map = {}
                        for row in fk_result:
                            key = (row[0], row[1], row[2]) # (schema, table, col)
                            fk_map[key] = {
                                "referenced_table": f"{row[3]}.{row[4]}" if row[3] != 'public' else row[4],
                                "referenced_column": row[5]
                            }
                            
                            # Add to relationships list
                            relationships.append({
                                "from_table": f"{row[0]}.{row[1]}" if row[0] != 'public' else row[1],
                                "from_columns": [row[2]],
                                "to_table": f"{row[3]}.{row[4]}" if row[3] != 'public' else row[4],
                                "to_columns": [row[5]]
                            })
                        
                        # Build tables_info
                        for schema, table_name in discovered_tables:
                            key = (schema, table_name)
                            full_name = f"{schema}.{table_name}" if schema != 'public' else table_name
                            columns = []
                            table_pks = pk_map.get(key, set())
                            
                            for col in all_columns.get(key, []):
                                col_name = col["column_name"]
                                is_pk = col_name in table_pks
                                fk_info = fk_map.get((schema, table_name, col_name))
                                
                                columns.append({
                                    "column_name": col_name,
                                    "data_type": col["data_type"],
                                    "is_nullable": col["is_nullable"],
                                    "is_primary_key": is_pk,
                                    "foreign_key": fk_info,
                                })
                            
                            tables_info.append({
                                "table_name": full_name,
                                "columns": columns,
                                "primary_key_columns": list(table_pks),
                            })
                else:
                    inspector = inspect(engine)
                    all_tables = inspector.get_table_names()
                    total_tables_in_db = len(all_tables)
                    for tbl in all_tables[:max_tables]:
                        try:
                            cols = inspector.get_columns(tbl)
                            tables_info.append({
                                "table_name": tbl,
                                "columns": [{"column_name": c["name"], "data_type": str(c["type"]), "is_nullable": True, "is_primary_key": False, "foreign_key": None} for c in cols],
                                "primary_key_columns": [],
                            })
                        except Exception as e:
                            logging.warning(f"Failed for {tbl}: {e}")
                
                engine.dispose()
            
            logging.info(f"Schema complete: {len(tables_info)} tables")
            
            result = {
                "source_type": "database",
                "title": source.title,
                "file_name": None,
                "tables": tables_info,
                "relationships": [],
                "total_tables_in_db": total_tables_in_db,
            }
            if total_tables_in_db > max_tables:
                result["truncated"] = True
                result["message"] = f"Showing {max_tables} of {total_tables_in_db} tables."
            return result
            
        except Exception as e:
            logging.error(f"Schema error: {e}")
            logging.error(traceback.format_exc())
            return {
                "source_type": "database",
                "title": getattr(source, 'title', 'Database'),
                "tables": [],
                "relationships": [],
                "error": str(e)
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
