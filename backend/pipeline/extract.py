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

from backend.connector import db_connector

logger = logging.getLogger(__name__)


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
    """
    
    def __init__(self, config_path: str = "config/embedding_config.yaml"):
        """
        Initialize extractor with configuration.
        
        Args:
            config_path: Path to embedding_config.yaml
        """
        self.config = self._load_config(config_path)
        self.excluded_tables = set(self.config['tables'].get('exclude_tables', []))
        self.global_exclude_columns = set(self.config['tables'].get('global_exclude_columns', []))
        self.table_specific_exclusions = self.config['tables'].get('table_specific_exclusions', {})
    
    def _load_config(self, config_path: str) -> Dict:
        """Load YAML configuration file."""
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    
    def get_allowed_tables(self) -> List[str]:
        """Get list of tables to process (excluding system/PII tables)."""
        all_tables = db_connector.get_all_tables()
        allowed_tables = [table for table in all_tables if table not in self.excluded_tables]
        logger.info(f"Found {len(allowed_tables)} tables to process.")
        return allowed_tables
    
    def get_safe_columns(self, table_name: str) -> List[str]:
        """
        Get columns safe for embedding (PII filtered).
        
        Applies both global and table-specific exclusions.
        """
        schema = db_connector.execute_query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :table",
            {"table": table_name}
        )
        all_columns = [col[0] for col in schema]
        
        # Combine global and table-specific exclusions
        exclude_cols = self.global_exclude_columns.copy()
        if table_name in self.table_specific_exclusions:
            exclude_cols.update(self.table_specific_exclusions[table_name])
        
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
            
            cols_str = ", ".join([f'"{c}"' for c in safe_columns])
            query = f'SELECT {cols_str} FROM public."{table_name}"'
            if table_limit:
                query += f" LIMIT {table_limit}"
            
            try:
                results = db_connector.execute_query(query)
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
                results = db_connector.execute_query(query)
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
            result = db_connector.execute_query(count_query)
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
                results = db_connector.execute_query(query)
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


def create_data_extractor(config_path: str = "config/embedding_config.yaml") -> DataExtractor:
    """Factory function for DataExtractor (backward compatibility)."""
    return DataExtractor(config_path)