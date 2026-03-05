from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any

from sqlalchemy import create_engine, inspect

from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.models.data import DbConnectionCreate, DbConnectionResponse
from backend.core.logging import get_logger
from backend.core.permissions import require_admin, require_at_least, UserRole, get_current_user, User
from backend.services.audit_service import get_audit_service, AuditAction

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

@router.post("/connections", response_model=Dict[str, Any], dependencies=[Depends(require_admin)])
async def create_connection(
    connection: DbConnectionCreate,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_db_service)
):
    """Add a new database connection. Requires Admin role or above."""
    try:
        conn_id = db_service.add_db_connection(
            name=connection.name,
            uri=connection.uri,
            engine_type=connection.engine_type,
            created_by=connection.created_by
        )
        
        # Log audit event
        audit = get_audit_service()
        audit.log(
            action=AuditAction.CONNECTION_CREATE,
            actor_id=current_user.id,
            actor_username=current_user.username,
            actor_role=current_user.role,
            resource_type="connection",
            resource_id=str(conn_id),
            resource_name=connection.name,
            details={"engine_type": connection.engine_type}
        )
        
        return {"status": "success", "id": conn_id, "message": "Connection added successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/connections/{connection_id}", dependencies=[Depends(require_admin)])
async def delete_connection(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_db_service)
):
    """Delete a database connection. Requires Admin role or above."""
    try:
        # Get connection info before deleting for audit log
        conn_info = db_service.get_db_connection_by_id(connection_id)
        
        success = db_service.delete_db_connection(connection_id)
        if not success:
            raise HTTPException(status_code=404, detail="Connection not found")
            
        # Log audit event
        if conn_info:
            audit = get_audit_service()
            audit.log(
                action=AuditAction.CONNECTION_DELETE,
                actor_id=current_user.id,
                actor_username=current_user.username,
                actor_role=current_user.role,
                resource_type="connection",
                resource_id=str(connection_id),
                resource_name=conn_info.get('name')
            )
            
        return {"status": "success", "message": "Connection deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/connections/{connection_id}/schema")
async def get_connection_schema(
    connection_id: int,
    current_user: User = Depends(get_current_user),
    db_service: DatabaseService = Depends(get_db_service)
):
    """Fetch schema for a specific connection.
    
    This endpoint connects directly to the specified database connection
    to retrieve its schema. It does NOT require a published RAG configuration.
    """
    # Verify connection exists
    conn = db_service.get_db_connection_by_id(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    try:
        uri = conn["uri"]
        # Connect directly to the database to fetch schema
        # Don't use SQLService which requires global config
        schema_info = _get_schema_for_uri(uri)
        return {"status": "success", "connection": conn["name"], "schema": schema_info}
    except Exception as e:
        logger.error(f"Error fetching schema for connection {connection_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch schema: {str(e)}")


def _get_schema_for_uri(uri: str) -> Dict[str, Any]:
    """
    Connect to a database URI and retrieve its schema (tables and columns).
    Uses raw SQL queries instead of SQLAlchemy inspect() to work with
    read-only users that don't have access to all system catalogs.
    
    Optimized to fetch all tables and columns in minimal queries to avoid timeouts.
    
    Args:
        uri: Database connection URI
        
    Returns:
        Dict with 'tables' list and 'details' dict of column info per table
    """
    from sqlalchemy import text
    
    try:
        # Create a temporary engine to query the database
        engine = create_engine(
            uri,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_pre_ping=True
        )
        
        schema_info = {}
        table_names = []
        
        with engine.connect() as conn:
            # Detect database type from dialect
            dialect_name = engine.dialect.name
            
            if dialect_name == 'postgresql':
                # PostgreSQL: Fetch tables AND columns in ONE query for performance
                # This avoids N+1 query problem that causes timeouts
                combined_query = text("""
                    SELECT 
                        t.table_schema,
                        t.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable
                    FROM information_schema.tables t
                    LEFT JOIN information_schema.columns c 
                        ON t.table_schema = c.table_schema 
                        AND t.table_name = c.table_name
                    WHERE t.table_type IN ('BASE TABLE', 'VIEW')
                    AND t.table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                    AND t.table_schema NOT LIKE 'pg_temp%'
                    ORDER BY t.table_schema, t.table_name, c.ordinal_position
                    LIMIT 10000
                """)
                result = conn.execute(combined_query)
                
                # Process results - group columns by table
                current_table_key = None
                for row in result:
                    schema_name, table_name, col_name, data_type, is_nullable = row
                    
                    # Build table key
                    if schema_name == 'public':
                        table_key = table_name
                    else:
                        table_key = f"{schema_name}.{table_name}"
                    
                    # New table encountered
                    if table_key != current_table_key:
                        if table_key not in table_names:
                            table_names.append(table_key)
                        if table_key not in schema_info:
                            schema_info[table_key] = []
                        current_table_key = table_key
                    
                    # Add column if exists (LEFT JOIN may return NULL for tables with no columns)
                    if col_name:
                        schema_info[table_key].append({
                            "name": col_name,
                            "type": data_type.upper() if data_type else "UNKNOWN",
                            "nullable": is_nullable == 'YES'
                        })
                    
            elif dialect_name == 'mysql':
                # MySQL: Fetch all in one query
                db_result = conn.execute(text("SELECT DATABASE()"))
                db_name = db_result.scalar()
                
                combined_query = text("""
                    SELECT 
                        t.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable
                    FROM information_schema.tables t
                    LEFT JOIN information_schema.columns c 
                        ON t.table_schema = c.table_schema 
                        AND t.table_name = c.table_name
                    WHERE t.table_schema = :db_name
                    AND t.table_type = 'BASE TABLE'
                    ORDER BY t.table_name, c.ordinal_position
                    LIMIT 10000
                """)
                result = conn.execute(combined_query, {"db_name": db_name})
                
                current_table = None
                for row in result:
                    table_name, col_name, data_type, is_nullable = row
                    
                    if table_name != current_table:
                        if table_name not in table_names:
                            table_names.append(table_name)
                        if table_name not in schema_info:
                            schema_info[table_name] = []
                        current_table = table_name
                    
                    if col_name:
                        schema_info[table_name].append({
                            "name": col_name,
                            "type": data_type.upper() if data_type else "UNKNOWN",
                            "nullable": is_nullable == 'YES'
                        })
                    
            elif dialect_name == 'sqlite':
                # SQLite: Use sqlite_master for tables, then batch PRAGMA calls
                tables_query = text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                    LIMIT 500
                """)
                result = conn.execute(tables_query)
                table_names = [row[0] for row in result]
                
                # SQLite doesn't support batch column queries, but tables are usually fewer
                for table in table_names:
                    cols_result = conn.execute(text(f'PRAGMA table_info("{table}")'))
                    
                    column_details = []
                    for col in cols_result:
                        column_details.append({
                            "name": col[1],
                            "type": col[2].upper() if col[2] else "TEXT",
                            "nullable": col[3] == 0
                        })
                    schema_info[table] = column_details
            else:
                # Fallback: Single combined query using information_schema
                try:
                    combined_query = text("""
                        SELECT 
                            t.table_name,
                            c.column_name,
                            c.data_type,
                            c.is_nullable
                        FROM information_schema.tables t
                        LEFT JOIN information_schema.columns c 
                            ON t.table_name = c.table_name
                        WHERE t.table_type = 'BASE TABLE'
                        ORDER BY t.table_name, c.ordinal_position
                        LIMIT 10000
                    """)
                    result = conn.execute(combined_query)
                    
                    current_table = None
                    for row in result:
                        table_name, col_name, data_type, is_nullable = row
                        
                        if table_name != current_table:
                            if table_name not in table_names:
                                table_names.append(table_name)
                            if table_name not in schema_info:
                                schema_info[table_name] = []
                            current_table = table_name
                        
                        if col_name:
                            schema_info[table_name].append({
                                "name": col_name,
                                "type": data_type.upper() if data_type else "UNKNOWN",
                                "nullable": is_nullable == 'YES' if is_nullable else True
                            })
                except Exception as fallback_error:
                    logger.warning(f"Fallback schema fetch failed: {fallback_error}")
                    raise ValueError(f"Unsupported database type: {dialect_name}")
        
        # Dispose engine to clean up connections
        engine.dispose()
        
        logger.info(f"Successfully fetched schema: {len(table_names)} tables")
        return {"tables": table_names, "details": schema_info}
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch schema for URI: {e}")
        raise ValueError(f"Could not connect or inspect database: {str(e)}")
