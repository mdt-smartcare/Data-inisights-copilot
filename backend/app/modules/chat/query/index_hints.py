"""
Index Metadata Extractor — Enriches schema with index information.

Extracts database index information and enriches schema context
to help the LLM generate more efficient queries.

The LLM doesn't know about physical design by default. By injecting
index hints into the schema context, we can nudge it to:
- Use equality/range filters on indexed columns
- Avoid wrapping indexed columns in functions
- Prefer partition keys for time-based filters
"""
from typing import Optional, List, Dict, Set
from dataclasses import dataclass, field
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IndexInfo:
    """Metadata for a database index."""
    name: str
    table_name: str
    columns: List[str]
    is_unique: bool = False
    is_primary: bool = False
    is_clustered: bool = False
    index_type: str = "BTREE"  # BTREE, HASH, GIN, GIST, etc.


@dataclass
class ColumnIndexHint:
    """Index hints for a specific column."""
    column_name: str
    table_name: str
    is_indexed: bool = False
    is_primary_key: bool = False
    is_partition_key: bool = False
    index_type: str = ""
    
    def to_hint_string(self) -> str:
        """Generate a hint string for the prompt."""
        hints = []
        if self.is_primary_key:
            hints.append("PRIMARY KEY")
        if self.is_partition_key:
            hints.append("PARTITION KEY")
        if self.is_indexed and not self.is_primary_key:
            hints.append(f"INDEXED ({self.index_type})")
        return ", ".join(hints) if hints else ""


class IndexMetadataExtractor:
    """
    Extracts index metadata from the database.
    
    Supports PostgreSQL and DuckDB.
    
    Usage:
        extractor = IndexMetadataExtractor(engine)
        indexes = extractor.get_indexes_for_table("patient_tracker")
        
        # Get column hints for prompt enrichment
        hints = extractor.get_column_hints("patient_tracker")
        for col, hint in hints.items():
            print(f"{col}: {hint.to_hint_string()}")
    """
    
    def __init__(self, engine: Engine, schema_name: str = "public"):
        self.engine = engine
        self.schema_name = schema_name
        self._db_type = self._detect_db_type()
        
        # Cache
        self._indexes_cache: Dict[str, List[IndexInfo]] = {}
        self._column_hints_cache: Dict[str, Dict[str, ColumnIndexHint]] = {}
    
    def _detect_db_type(self) -> str:
        """Detect database type from engine."""
        dialect = self.engine.dialect.name.lower()
        if "duckdb" in dialect:
            return "duckdb"
        elif "postgres" in dialect:
            return "postgresql"
        else:
            return dialect
    
    def get_indexes_for_table(self, table_name: str) -> List[IndexInfo]:
        """
        Get all indexes for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of IndexInfo objects
        """
        if table_name in self._indexes_cache:
            return self._indexes_cache[table_name]
        
        try:
            if self._db_type == "postgresql":
                indexes = self._get_pg_indexes(table_name)
            elif self._db_type == "duckdb":
                indexes = self._get_duckdb_indexes(table_name)
            else:
                indexes = self._get_generic_indexes(table_name)
            
            self._indexes_cache[table_name] = indexes
            return indexes
            
        except Exception as e:
            logger.warning(f"Failed to extract indexes for {table_name}: {e}")
            return []
    
    def _get_pg_indexes(self, table_name: str) -> List[IndexInfo]:
        """Extract indexes from PostgreSQL."""
        query = text("""
            SELECT 
                i.relname as index_name,
                t.relname as table_name,
                array_agg(a.attname ORDER BY x.ord) as columns,
                ix.indisunique as is_unique,
                ix.indisprimary as is_primary,
                ix.indisclustered as is_clustered,
                am.amname as index_type
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_am am ON i.relam = am.oid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            CROSS JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS x(attnum, ord)
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.attnum
            WHERE t.relname = :table_name
              AND n.nspname = :schema_name
            GROUP BY i.relname, t.relname, ix.indisunique, ix.indisprimary, ix.indisclustered, am.amname
        """)
        
        indexes = []
        with self.engine.connect() as conn:
            result = conn.execute(query, {
                "table_name": table_name,
                "schema_name": self.schema_name
            })
            
            for row in result:
                indexes.append(IndexInfo(
                    name=row.index_name,
                    table_name=row.table_name,
                    columns=list(row.columns),
                    is_unique=row.is_unique,
                    is_primary=row.is_primary,
                    is_clustered=row.is_clustered,
                    index_type=row.index_type.upper()
                ))
        
        return indexes
    
    def _get_duckdb_indexes(self, table_name: str) -> List[IndexInfo]:
        """Extract indexes from DuckDB (limited support)."""
        # DuckDB has limited index support, mainly uses ART for primary keys
        # and has automatic indexing for certain operations
        try:
            inspector = inspect(self.engine)
            pk_cols = inspector.get_pk_constraint(table_name).get('constrained_columns', [])
            
            indexes = []
            if pk_cols:
                indexes.append(IndexInfo(
                    name=f"{table_name}_pkey",
                    table_name=table_name,
                    columns=pk_cols,
                    is_unique=True,
                    is_primary=True,
                    index_type="ART"  # DuckDB uses Adaptive Radix Tree
                ))
            
            return indexes
            
        except Exception as e:
            logger.debug(f"DuckDB index extraction limited: {e}")
            return []
    
    def _get_generic_indexes(self, table_name: str) -> List[IndexInfo]:
        """Generic index extraction using SQLAlchemy inspector."""
        try:
            inspector = inspect(self.engine)
            
            indexes = []
            
            # Get primary key
            pk = inspector.get_pk_constraint(table_name, schema=self.schema_name)
            if pk and pk.get('constrained_columns'):
                indexes.append(IndexInfo(
                    name=pk.get('name', f"{table_name}_pkey"),
                    table_name=table_name,
                    columns=pk['constrained_columns'],
                    is_unique=True,
                    is_primary=True
                ))
            
            # Get other indexes
            for idx in inspector.get_indexes(table_name, schema=self.schema_name):
                indexes.append(IndexInfo(
                    name=idx['name'],
                    table_name=table_name,
                    columns=idx.get('column_names', []),
                    is_unique=idx.get('unique', False)
                ))
            
            return indexes
            
        except Exception as e:
            logger.warning(f"Generic index extraction failed: {e}")
            return []
    
    def get_column_hints(self, table_name: str) -> Dict[str, ColumnIndexHint]:
        """
        Get index hints for all columns in a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dict mapping column name to ColumnIndexHint
        """
        if table_name in self._column_hints_cache:
            return self._column_hints_cache[table_name]
        
        indexes = self.get_indexes_for_table(table_name)
        
        hints: Dict[str, ColumnIndexHint] = {}
        
        for idx in indexes:
            for col in idx.columns:
                if col not in hints:
                    hints[col] = ColumnIndexHint(
                        column_name=col,
                        table_name=table_name
                    )
                
                hints[col].is_indexed = True
                
                if idx.is_primary:
                    hints[col].is_primary_key = True
                
                if idx.is_clustered:
                    hints[col].is_partition_key = True
                
                if not hints[col].index_type:
                    hints[col].index_type = idx.index_type
        
        self._column_hints_cache[table_name] = hints
        return hints
    
    def clear_cache(self):
        """Clear the index cache."""
        self._indexes_cache.clear()
        self._column_hints_cache.clear()


def enrich_schema_with_index_hints(
    schema_context: str,
    engine: Engine,
    table_names: List[str],
    schema_name: str = "public"
) -> str:
    """
    Enrich schema context with index hints.
    
    Adds index information to schema context to help LLM
    generate more efficient queries.
    
    Args:
        schema_context: Original schema context string
        engine: Database engine
        table_names: Tables to get index hints for
        schema_name: Database schema
        
    Returns:
        Enriched schema context with index hints
    """
    try:
        extractor = IndexMetadataExtractor(engine, schema_name)
        
        hint_sections = []
        
        for table_name in table_names:
            hints = extractor.get_column_hints(table_name)
            if hints:
                indexed_cols = []
                for col, hint in hints.items():
                    hint_str = hint.to_hint_string()
                    if hint_str:
                        indexed_cols.append(f"  - {col}: {hint_str}")
                
                if indexed_cols:
                    hint_sections.append(
                        f"INDEX HINTS FOR {table_name}:\n" + "\n".join(indexed_cols)
                    )
        
        if hint_sections:
            index_context = "\n\n".join(hint_sections)
            
            optimization_guidance = """
QUERY OPTIMIZATION GUIDELINES:
- Prefer equality or range filters on INDEXED columns
- Use PRIMARY KEY columns for efficient lookups
- Filter on PARTITION KEY columns for time-range queries
- AVOID wrapping indexed columns in functions (e.g., don't use DATE(indexed_col) in WHERE)
- When filtering by time periods, generate predicates directly on partition keys
"""
            
            return f"{schema_context}\n\n{index_context}\n\n{optimization_guidance}"
        
        return schema_context
        
    except Exception as e:
        logger.warning(f"Failed to enrich schema with index hints: {e}")
        return schema_context


# Common partition/date columns to prioritize in hints
COMMON_DATE_COLUMNS = {
    "created_at", "updated_at", "date", "timestamp", "event_date",
    "order_date", "visit_date", "measurement_date", "effective_date"
}


def infer_partition_columns(columns: List[str]) -> Set[str]:
    """Infer likely partition columns based on naming conventions."""
    return {col for col in columns if col.lower() in COMMON_DATE_COLUMNS}
