"""
Data Extraction Pipeline for RAG Embedding.

This module handles extraction of medical data from SQL databases
with PII filtering and generator-based streaming to prevent memory exhaustion.

Bottleneck Addressed:
- Original implementation loaded all tables into memory simultaneously
- Generator-based extraction allows processing one table at a time
- Parallel table extraction for faster cold-start times
"""
import pandas as pd
import yaml
from tqdm import tqdm
import logging
import asyncio
from typing import Dict, List, Iterator, Tuple, Optional, AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from backend.sqliteDb.db import get_db_service

logger = logging.getLogger(__name__)


def _get_database_uri(agent_id: Optional[int] = None, connection_id: Optional[int] = None) -> Optional[str]:
    """
    Get database URI from the active published RAG configuration.
    
    Args:
        agent_id: Optional agent ID to get agent-specific config.
        connection_id: Optional direct connection ID to use.
    
    Returns:
        Database URI string, or None if no connection is configured.
    """
    try:
        db_service = get_db_service()
        
        # If direct connection_id provided, use it
        if connection_id:
            connection = db_service.get_db_connection_by_id(connection_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection by ID: {connection.get('name')} (ID: {connection_id})")
                return connection['uri']
        
        # Try to get active config for specific agent first
        if agent_id:
            active_config = db_service.get_active_config(agent_id=agent_id)
            if active_config and active_config.get('connection_id'):
                conn_id = active_config['connection_id']
                connection = db_service.get_db_connection_by_id(conn_id)
                if connection and connection.get('uri'):
                    logger.info(f"Using database connection from agent {agent_id} config: {connection.get('name')} (ID: {conn_id})")
                    return connection['uri']
        
        # Try global config (no agent_id)
        active_config = db_service.get_active_config()
        if active_config and active_config.get('connection_id'):
            conn_id = active_config['connection_id']
            connection = db_service.get_db_connection_by_id(conn_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection from global config: {connection.get('name')} (ID: {conn_id})")
                return connection['uri']
        
        # Fallback: Check if ANY agent has a published config with a connection
        conn = db_service.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pc.connection_id, sp.agent_id
            FROM system_prompts sp
            JOIN prompt_configs pc ON sp.id = pc.prompt_id
            WHERE sp.is_active = 1 AND pc.connection_id IS NOT NULL
            ORDER BY sp.created_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            fallback_conn_id = row[0]
            fallback_agent_id = row[1]
            connection = db_service.get_db_connection_by_id(fallback_conn_id)
            if connection and connection.get('uri'):
                logger.info(f"Using database connection from agent {fallback_agent_id} config (fallback): {connection.get('name')} (ID: {fallback_conn_id})")
                return connection['uri']
        
        logger.warning("No active database connection configured.")
        return None
        
    except Exception as e:
        logger.error(f"Failed to get database URI: {e}")
        return None


class DatabaseConnector:
    """
    Database connector that uses connections from the db_connections table.
    
    Replaces the legacy connector that used db_config.yaml.
    """
    
    def __init__(self, database_uri: Optional[str] = None):
        """
        Initialize connector with a database URI.
        
        Args:
            database_uri: Optional URI. If not provided, fetches from active config.
        """
        self._database_uri = database_uri
        self.engine = None
        self.connection = None
        self.is_connected = False

    def connect(self) -> bool:
        """Establish database connection."""
        if self.is_connected and self.connection:
            return True
            
        try:
            # Get URI from active config if not provided
            uri = self._database_uri or _get_database_uri()
            if not uri:
                raise ValueError(
                    "No database connection configured. "
                    "Please configure a connection via Settings > Database Connections "
                    "and publish a RAG configuration."
                )
            
            logger.info("Connecting to database...")
            self.engine = create_engine(
                uri, 
                pool_size=20, 
                max_overflow=50, 
                pool_timeout=60
            )
            self.connection = self.engine.connect()
            self.connection.execute(text("SELECT 1"))
            logger.info("Database connection successful.")
            self.is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
        if self.engine:
            self.engine.dispose()
        self.is_connected = False
        logger.info("Database connection closed.")

    def execute_query(self, query: str, params: Optional[Dict] = None) -> List:
        """Execute a SQL query and return results."""
        if not self.is_connected:
            if not self.connect():
                raise Exception("No database connection available")
        try:
            result = self.connection.execute(text(query), params or {})
            return result.fetchall()
        except SQLAlchemyError as e:
            logger.error(f"Query execution failed: {e}")
            return []

    def get_all_tables(self) -> List[str]:
        """Get all table names from the public schema."""
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE' 
            ORDER BY table_name
        """
        results = self.execute_query(query)
        return [row[0] for row in results] if results else []


# Lazy-initialized singleton
_db_connector: Optional[DatabaseConnector] = None


def get_db_connector(database_uri: Optional[str] = None) -> DatabaseConnector:
    """
    Get or create database connector instance.
    
    Args:
        database_uri: Optional URI to use. If provided, creates a new connector.
    """
    global _db_connector
    
    if database_uri:
        # Create new connector with specific URI
        return DatabaseConnector(database_uri)
    
    if _db_connector is None:
        _db_connector = DatabaseConnector()
    
    return _db_connector


@dataclass
class TableBatch:
    """
    Represents a batch of rows from a single table.
    
    Used for streaming extraction to avoid loading entire tables into memory.
    """
    table_name: str
    dataframe: pd.DataFrame
    batch_index: int
    total_batches: int
    is_last: bool


class DataExtractor:
    """
    Production-grade data extractor with streaming and parallel capabilities.
    
    Improvements:
    - Generator-based extraction (yield vs return)
    - Parallel table fetching via connection pool
    - Configurable batch sizes for memory control
    - Async-first API for embedding pipeline integration
    - Configuration loaded from database (single source of truth)
    """
    
    def __init__(self, config_path: str = None, database_uri: Optional[str] = None):
        """
        Initialize extractor with configuration.
        
        Args:
            config_path: DEPRECATED - Path to embedding_config.yaml (used as fallback only)
            database_uri: Optional database URI. If not provided, uses active config.
        """
        self.config = self._load_config(config_path)
        self.excluded_tables = set(self.config.get('exclude_tables', []))
        self.global_exclude_columns = set(self.config.get('global_exclude_columns', []))
        self.table_specific_exclusions = self.config.get('table_specific_exclusions', {})
        self.db_connector = get_db_connector(database_uri)
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict:
        """
        Load configuration from database (primary) or YAML file (fallback).
        
        The database is the single source of truth for configuration.
        YAML file is only used as fallback if database is unavailable.
        """
        try:
            # Primary source: Database via ConfigService
            from backend.services.config_service import get_config_service
            config_service = get_config_service()
            pii_rules = config_service.get_pii_rules()
            
            logger.info("Loaded PII/extraction config from database")
            return {
                'exclude_tables': pii_rules.get('exclude_tables', []),
                'global_exclude_columns': pii_rules.get('global_exclude_columns', []),
                'table_specific_exclusions': pii_rules.get('table_specific_exclusions', {}),
            }
        except Exception as e:
            logger.warning(f"Failed to load config from database: {e}. Falling back to YAML.")
            
            # Fallback: YAML file
            if config_path is None:
                config_path = "config/embedding_config.yaml"
            
            try:
                with open(config_path, 'r') as file:
                    yaml_config = yaml.safe_load(file)
                    tables_config = yaml_config.get('tables', {})
                    return {
                        'exclude_tables': tables_config.get('exclude_tables', []),
                        'global_exclude_columns': tables_config.get('global_exclude_columns', []),
                        'table_specific_exclusions': tables_config.get('table_specific_exclusions', {}),
                    }
            except Exception as yaml_error:
                logger.error(f"Failed to load YAML config: {yaml_error}. Using empty defaults.")
                return {
                    'exclude_tables': [],
                    'global_exclude_columns': [],
                    'table_specific_exclusions': {},
                }
    
    def get_allowed_tables(self) -> List[str]:
        """Get list of tables to process (excluding system/PII tables)."""
        all_tables = self.db_connector.get_all_tables()
        allowed_tables = [table for table in all_tables if table not in self.excluded_tables]
        logger.info(f"Found {len(allowed_tables)} tables to process.")
        return allowed_tables
    
    def get_safe_columns(self, table_name: str) -> List[str]:
        """
        Get columns safe for embedding (PII filtered).
        
        Applies both global and table-specific exclusions.
        Handles schema-prefixed table names (e.g., 'rnacen.table_name').
        """
        # Parse schema and table name
        if '.' in table_name:
            schema_name, base_table_name = table_name.split('.', 1)
        else:
            schema_name = 'public'
            base_table_name = table_name
        
        schema = self.db_connector.execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = :schema AND table_name = :table",
            {"schema": schema_name, "table": base_table_name}
        )
        all_columns = [col[0] for col in schema]
        
        if not all_columns:
            logger.warning(f"No columns found for table {table_name} (schema={schema_name}, table={base_table_name})")
        
        # Combine global and table-specific exclusions
        exclude_cols = self.global_exclude_columns.copy()
        if table_name in self.table_specific_exclusions:
            exclude_cols.update(self.table_specific_exclusions[table_name])
        # Also check base table name for exclusions
        if base_table_name in self.table_specific_exclusions:
            exclude_cols.update(self.table_specific_exclusions[base_table_name])
        
        safe_columns = [col for col in all_columns if col not in exclude_cols]
        return safe_columns
    
    async def extract_all_tables(
        self, 
        table_limit: Optional[int] = None, 
        on_progress=None
    ) -> Dict[str, pd.DataFrame]:
        """
        Extract all tables (legacy API for backward compatibility).
        
        For large datasets, prefer extract_tables_streaming() instead.
        
        Args:
            table_limit: Max rows per table (for testing)
            on_progress: Async callback(current, total, table_name)
            
        Returns:
            Dict mapping table names to DataFrames
        """
        table_data = {}
        
        async for table_name, df in self.extract_tables_streaming(table_limit, on_progress):
            table_data[table_name] = df
        
        logger.info(f"Successfully extracted data from {len(table_data)} tables")
        return table_data
    
    async def extract_tables_streaming(
        self,
        table_limit: Optional[int] = None,
        on_progress=None
    ) -> AsyncIterator[Tuple[str, pd.DataFrame]]:
        """
        Generator-based table extraction for memory efficiency.
        
        Bottleneck Addressed:
        - Original loaded all tables into single dict (OOM on large schemas)
        - Generator yields one table at a time, allowing GC between tables
        
        Args:
            table_limit: Max rows per table
            on_progress: Async callback(current, total, table_name)
            
        Yields:
            Tuples of (table_name, DataFrame)
        """
        allowed_tables = self.get_allowed_tables()
        total_tables = len(allowed_tables)
        
        for i, table_name in enumerate(tqdm(allowed_tables, desc="Extracting tables")):
            if on_progress:
                if asyncio.iscoroutinefunction(on_progress):
                    await on_progress(i, total_tables, table_name)
                else:
                    on_progress(i, total_tables, table_name)
            
            safe_columns = self.get_safe_columns(table_name)
            if not safe_columns:
                logger.warning(f"No safe columns for table {table_name}, skipping.")
                continue
            
            # Parse schema and table name for query
            if '.' in table_name:
                schema_name, base_table_name = table_name.split('.', 1)
                full_table_ref = f'"{schema_name}"."{base_table_name}"'
            else:
                full_table_ref = f'public."{table_name}"'
            
            cols_str = ", ".join([f'"{c}"' for c in safe_columns])
            query = f'SELECT {cols_str} FROM {full_table_ref}'
            if table_limit:
                query += f" LIMIT {table_limit}"
            
            try:
                results = self.db_connector.execute_query(query)
                df = pd.DataFrame(results, columns=safe_columns)
                if not df.empty:
                    yield table_name, df
            except Exception as e:
                logger.error(f"Failed to extract {table_name}: {e}")
    
    async def extract_tables_parallel(
        self,
        table_limit: Optional[int] = None,
        max_concurrent: int = 4,
        on_progress=None
    ) -> Dict[str, pd.DataFrame]:
        """
        Parallel table extraction using thread pool.
        
        Bottleneck Addressed:
        - Sequential extraction blocks on large tables
        - Parallel fetching reduces total extraction time by 2-4x
        
        Args:
            table_limit: Max rows per table
            max_concurrent: Max concurrent DB connections
            on_progress: Callback(current, total, table_name)
            
        Returns:
            Dict mapping table names to DataFrames
        """
        allowed_tables = self.get_allowed_tables()
        total_tables = len(allowed_tables)
        table_data = {}
        completed = 0
        
        def extract_single_table(table_name: str) -> Tuple[str, Optional[pd.DataFrame]]:
            """Thread worker for single table extraction."""
            safe_columns = self.get_safe_columns(table_name)
            if not safe_columns:
                logger.warning(f"No safe columns for table {table_name}, skipping.")
                return table_name, None
            
            cols_str = ", ".join([f'"{c}"' for c in safe_columns])
            query = f'SELECT {cols_str} FROM public."{table_name}"'
            if table_limit:
                query += f" LIMIT {table_limit}"
            
            try:
                results = self.db_connector.execute_query(query)
                df = pd.DataFrame(results, columns=safe_columns)
                return table_name, df if not df.empty else None
            except Exception as e:
                logger.error(f"Failed to extract {table_name}: {e}")
                return table_name, None
        
        # Use ThreadPoolExecutor for I/O-bound DB queries
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = [
                loop.run_in_executor(executor, extract_single_table, table)
                for table in allowed_tables
            ]
            
            for future in asyncio.as_completed(futures):
                table_name, df = await future
                completed += 1
                
                if df is not None:
                    table_data[table_name] = df
                
                if on_progress:
                    if asyncio.iscoroutinefunction(on_progress):
                        await on_progress(completed, total_tables, table_name)
                    else:
                        on_progress(completed, total_tables, table_name)
        
        logger.info(f"Parallel extraction complete: {len(table_data)} tables")
        return table_data
    
    def extract_table_batched(
        self,
        table_name: str,
        batch_size: int = 10000,
        safe_columns: Optional[List[str]] = None
    ) -> Iterator[TableBatch]:
        """
        Extract a single table in batches for very large tables.
        
        Useful for tables with millions of rows where loading
        entire table would cause OOM.
        
        Args:
            table_name: Name of table to extract
            batch_size: Rows per batch
            safe_columns: Pre-computed safe columns (optional)
            
        Yields:
            TableBatch objects with DataFrame chunks
        """
        if safe_columns is None:
            safe_columns = self.get_safe_columns(table_name)
        
        if not safe_columns:
            logger.warning(f"No safe columns for table {table_name}")
            return
        
        # Get total row count
        count_query = f'SELECT COUNT(*) FROM public."{table_name}"'
        try:
            result = self.db_connector.execute_query(count_query)
            total_rows = result[0][0]
        except Exception as e:
            logger.error(f"Failed to get count for {table_name}: {e}")
            return
        
        total_batches = (total_rows + batch_size - 1) // batch_size
        cols_str = ", ".join([f'"{c}"' for c in safe_columns])
        
        for batch_idx in range(total_batches):
            offset = batch_idx * batch_size
            query = f'SELECT {cols_str} FROM public."{table_name}" LIMIT {batch_size} OFFSET {offset}'
            
            try:
                results = self.db_connector.execute_query(query)
                df = pd.DataFrame(results, columns=safe_columns)
                
                yield TableBatch(
                    table_name=table_name,
                    dataframe=df,
                    batch_index=batch_idx,
                    total_batches=total_batches,
                    is_last=(batch_idx == total_batches - 1)
                )
            except Exception as e:
                logger.error(f"Failed to extract batch {batch_idx} from {table_name}: {e}")


def create_data_extractor(config_path: str = "config/embedding_config.yaml", database_uri: Optional[str] = None) -> DataExtractor:
    """Factory function for DataExtractor."""
    return DataExtractor(config_path, database_uri)