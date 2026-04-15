"""
Schema Graph — Graph-based schema representation with FK introspection.

Provides structured, machine-readable schema awareness by introspecting
the connected database for tables, columns, foreign keys, and join paths.

This replaces the flat `db.get_table_info()` text dump with a queryable
graph structure that enables:
- FK-aware join path discovery (BFS)
- Column-level type and constraint awareness
- Targeted schema context for prompt construction
"""
import time
from typing import Optional, List, Dict, Set, Tuple
from collections import defaultdict, deque
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.utils.logging import get_logger
from .models import ColumnInfo, ForeignKey, TableInfo, JoinStep, JoinPath

logger = get_logger(__name__)


class SchemaGraph:
    """
    Graph-based schema representation built from database introspection.
    
    On initialization, queries `information_schema` to build a graph of:
    - Tables and their columns (name, type, nullable, PK/FK)
    - Foreign key relationships as directed edges
    - Precomputed join paths via BFS
    
    Usage:
        engine = create_engine(database_url)
        graph = SchemaGraph(engine, schema_name="public")
        
        # Get join path between two tables
        path = graph.get_join_path("patient_tracker", "site")
        
        # Get all related tables within 2 FK hops
        related = graph.get_related_tables("patient_tracker", depth=2)
        
        # Render schema for prompt
        prompt_text = graph.to_prompt_format(["patient_tracker", "site"])
    """
    
    def __init__(
        self,
        engine: Engine,
        schema_name: str = "public",
        excluded_tables: Optional[List[str]] = None,
    ):
        """
        Initialize SchemaGraph by introspecting the database.
        
        Args:
            engine: SQLAlchemy engine connected to the target database
            schema_name: Database schema to introspect (default: "public")
            excluded_tables: Tables to exclude from the graph
        """
        self.engine = engine
        self.schema_name = schema_name
        self._excluded_tables: Set[str] = set(excluded_tables or [
            "flyway_schema_history", "audit", "user_token",
            "django_migrations", "alembic_version"
        ])
        
        # Core data structures
        self._tables: Dict[str, TableInfo] = {}
        self._foreign_keys: List[ForeignKey] = []
        self._adjacency: Dict[str, Dict[str, List[ForeignKey]]] = defaultdict(
            lambda: defaultdict(list)
        )
        
        # Cache for computed join paths
        self._join_path_cache: Dict[Tuple[str, str], Optional[JoinPath]] = {}
        
        # Build the graph
        start = time.time()
        self._introspect()
        elapsed = (time.time() - start) * 1000
        logger.info(
            f"SchemaGraph built in {elapsed:.0f}ms: "
            f"{len(self._tables)} tables, {len(self._foreign_keys)} FK relationships"
        )
    
    # =========================================================================
    # Introspection (runs once at init)
    # =========================================================================
    
    def _introspect(self):
        """Introspect the database to build the schema graph."""
        with self.engine.connect() as conn:
            self._introspect_tables_and_columns(conn)
            self._introspect_primary_keys(conn)
            self._introspect_foreign_keys(conn)
    
    def _introspect_tables_and_columns(self, conn):
        """Load all tables and their columns from information_schema."""
        try:
            # Get all tables and views
            tables_query = text("""
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = :schema
                AND table_type IN ('BASE TABLE', 'VIEW')
                ORDER BY table_name
            """)
            tables_result = conn.execute(tables_query, {"schema": self.schema_name})
            table_names = []
            for row in tables_result:
                if row[0] not in self._excluded_tables:
                    table_names.append(row[0])
            
            if not table_names:
                logger.warning(f"No tables found in schema '{self.schema_name}'")
                return
            
            # Get columns for all tables in one query
            columns_query = text("""
                SELECT table_name, column_name, data_type, 
                       is_nullable, column_default, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = :schema
                AND table_name = ANY(:tables)
                ORDER BY table_name, ordinal_position
            """)
            columns_result = conn.execute(
                columns_query, 
                {"schema": self.schema_name, "tables": table_names}
            )
            
            # Group columns by table
            table_columns: Dict[str, List[ColumnInfo]] = defaultdict(list)
            for row in columns_result:
                table_columns[row[0]].append(ColumnInfo(
                    name=row[1],
                    data_type=row[2],
                    is_nullable=(row[3] == "YES"),
                    default_value=str(row[4]) if row[4] else None
                ))
            
            # Build TableInfo objects
            for table_name in table_names:
                self._tables[table_name] = TableInfo(
                    name=table_name,
                    schema_name=self.schema_name,
                    columns=table_columns.get(table_name, [])
                )
            
            logger.info(f"Introspected {len(self._tables)} tables/views in schema '{self.schema_name}'")
            
        except Exception as e:
            logger.error(f"Failed to introspect tables and columns: {e}")
            # Fallback: try pg_class approach
            self._introspect_tables_fallback(conn)
    
    def _introspect_tables_fallback(self, conn):
        """Fallback introspection using pg_class when information_schema fails."""
        try:
            result = conn.execute(text("""
                SELECT c.relname, a.attname, 
                       pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
                       NOT a.attnotnull as is_nullable
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                WHERE c.relkind IN ('r', 'v')
                AND n.nspname = :schema
                AND a.attnum > 0
                AND NOT a.attisdropped
                AND has_table_privilege(c.oid, 'SELECT')
                ORDER BY c.relname, a.attnum
            """), {"schema": self.schema_name})
            
            table_columns: Dict[str, List[ColumnInfo]] = defaultdict(list)
            for row in result:
                if row[0] not in self._excluded_tables:
                    table_columns[row[0]].append(ColumnInfo(
                        name=row[1],
                        data_type=row[2],
                        is_nullable=row[3]
                    ))
            
            for table_name, columns in table_columns.items():
                self._tables[table_name] = TableInfo(
                    name=table_name,
                    schema_name=self.schema_name,
                    columns=columns
                )
            
            logger.info(f"Fallback introspection found {len(self._tables)} tables")
            
        except Exception as e:
            logger.error(f"Fallback introspection also failed: {e}")
    
    def _introspect_primary_keys(self, conn):
        """Load primary key constraints."""
        try:
            pk_query = text("""
                SELECT kcu.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = :schema
                ORDER BY kcu.table_name, kcu.ordinal_position
            """)
            result = conn.execute(pk_query, {"schema": self.schema_name})
            
            for row in result:
                table_name, column_name = row[0], row[1]
                if table_name in self._tables:
                    self._tables[table_name].primary_keys.append(column_name)
                    # Mark the column as PK
                    for col in self._tables[table_name].columns:
                        if col.name == column_name:
                            col.is_primary_key = True
                            break
            
        except Exception as e:
            logger.warning(f"Failed to introspect primary keys: {e}")
    
    def _introspect_foreign_keys(self, conn):
        """Load foreign key relationships and build adjacency graph."""
        try:
            fk_query = text("""
                SELECT
                    tc.constraint_name,
                    kcu.table_name AS source_table,
                    kcu.column_name AS source_column,
                    ccu.table_name AS target_table,
                    ccu.column_name AS target_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu 
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = :schema
            """)
            result = conn.execute(fk_query, {"schema": self.schema_name})
            
            for row in result:
                fk = ForeignKey(
                    source_table=row[1],
                    source_column=row[2],
                    target_table=row[3],
                    target_column=row[4],
                    constraint_name=row[0]
                )
                self._foreign_keys.append(fk)
                
                # Build bidirectional adjacency
                self._adjacency[fk.source_table][fk.target_table].append(fk)
                self._adjacency[fk.target_table][fk.source_table].append(fk)
                
                # Mark FK columns
                if fk.source_table in self._tables:
                    self._tables[fk.source_table].foreign_keys.append(fk)
                    for col in self._tables[fk.source_table].columns:
                        if col.name == fk.source_column:
                            col.is_foreign_key = True
                            break
            
            logger.info(f"Found {len(self._foreign_keys)} foreign key relationships")
            
        except Exception as e:
            logger.warning(
                f"Failed to introspect foreign keys: {e}. Join path computation will be limited."
            )
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    @property
    def tables(self) -> Dict[str, TableInfo]:
        """Get all tables in the graph."""
        return self._tables
    
    @property 
    def table_names(self) -> List[str]:
        """Get all table names."""
        return list(self._tables.keys())
    
    def get_table(self, table_name: str) -> Optional[TableInfo]:
        """Get metadata for a specific table."""
        return self._tables.get(table_name)
    
    def get_column_names(self, table_name: str) -> List[str]:
        """Get column names for a table."""
        table = self._tables.get(table_name)
        if not table:
            return []
        return [col.name for col in table.columns]
    
    def has_table(self, table_name: str) -> bool:
        """Check if a table exists in the graph."""
        return table_name in self._tables
    
    def has_column(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a specific table."""
        table = self._tables.get(table_name)
        if not table:
            return False
        return any(col.name == column_name for col in table.columns)
    
    def get_join_path(self, source: str, target: str, max_depth: int = 4) -> Optional[JoinPath]:
        """
        Find the shortest join path between two tables using BFS.
        
        Args:
            source: Source table name
            target: Target table name
            max_depth: Maximum number of hops to search (default: 4)
            
        Returns:
            JoinPath if found, None if no path exists within max_depth
        """
        cache_key = (source, target)
        if cache_key in self._join_path_cache:
            return self._join_path_cache[cache_key]
        
        if source == target:
            return None
        
        if source not in self._tables or target not in self._tables:
            return None
        
        # BFS to find shortest path
        visited: Set[str] = {source}
        # Queue entries: (current_table, path_of_steps)
        queue: deque = deque([(source, [])])
        
        while queue:
            current, path = queue.popleft()
            
            if len(path) >= max_depth:
                continue
            
            for neighbor, fk_list in self._adjacency[current].items():
                if neighbor in visited:
                    continue
                
                # Use the first FK relationship for this edge
                fk = fk_list[0]
                
                # Determine join direction
                if fk.source_table == current:
                    step = JoinStep(
                        from_table=current,
                        from_column=fk.source_column,
                        to_table=neighbor,
                        to_column=fk.target_column,
                        join_type="LEFT JOIN"
                    )
                else:
                    step = JoinStep(
                        from_table=current,
                        from_column=fk.target_column,
                        to_table=neighbor,
                        to_column=fk.source_column,
                        join_type="LEFT JOIN"
                    )
                
                new_path = path + [step]
                
                if neighbor == target:
                    result = JoinPath(
                        source_table=source,
                        target_table=target,
                        steps=new_path,
                        hop_count=len(new_path)
                    )
                    self._join_path_cache[cache_key] = result
                    return result
                
                visited.add(neighbor)
                queue.append((neighbor, new_path))
        
        # No path found
        self._join_path_cache[cache_key] = None
        return None
    
    def get_related_tables(self, table_name: str, depth: int = 2) -> List[str]:
        """
        Get all tables within N FK hops of the given table.
        
        Args:
            table_name: Starting table
            depth: Maximum hop count (default: 2)
            
        Returns:
            List of related table names (excluding the starting table)
        """
        if table_name not in self._tables:
            return []
        
        visited: Set[str] = {table_name}
        queue: deque = deque([(table_name, 0)])
        related: List[str] = []
        
        while queue:
            current, current_depth = queue.popleft()
            
            if current_depth >= depth:
                continue
            
            for neighbor in self._adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    related.append(neighbor)
                    queue.append((neighbor, current_depth + 1))
        
        return related
    
    def get_join_paths_for_tables(self, tables: List[str]) -> List[JoinPath]:
        """
        Compute join paths connecting all specified tables.
        
        Uses the first table as the anchor and finds paths to all others.
        
        Args:
            tables: List of table names to connect
            
        Returns:
            List of JoinPaths connecting the tables
        """
        if len(tables) <= 1:
            return []
        
        paths = []
        anchor = tables[0]
        
        for other in tables[1:]:
            path = self.get_join_path(anchor, other)
            if path:
                paths.append(path)
            else:
                logger.warning(f"No FK join path found between '{anchor}' and '{other}'")
        
        return paths
    
    # =========================================================================
    # Prompt Formatting
    # =========================================================================
    
    def to_prompt_format(
        self,
        tables: Optional[List[str]] = None,
        include_sample_values: bool = False,
    ) -> str:
        """
        Render schema information as structured text for LLM prompt injection.
        
        Args:
            tables: Specific tables to include (None = all tables)
            include_sample_values: Whether to include sample data hints
            
        Returns:
            Formatted schema text with FK annotations
        """
        target_tables = tables or list(self._tables.keys())
        parts = []
        
        for table_name in target_tables:
            table = self._tables.get(table_name)
            if not table:
                continue
            
            # Table header
            lines = [f"TABLE: {table_name}"]
            if table.description:
                lines.append(f"  Description: {table.description}")
            if table.row_count_estimate:
                lines.append(f"  Approximate rows: {table.row_count_estimate:,}")
            
            # Primary keys
            if table.primary_keys:
                lines.append(f"  Primary Key: {', '.join(table.primary_keys)}")
            
            # Columns
            lines.append("  Columns:")
            for col in table.columns:
                col_desc = f"    - {col.name} ({col.data_type})"
                if col.is_primary_key:
                    col_desc += " [PK]"
                if col.is_foreign_key:
                    # Find which table this FK references
                    for fk in table.foreign_keys:
                        if fk.source_column == col.name:
                            col_desc += f" [FK → {fk.target_table}.{fk.target_column}]"
                            break
                if not col.is_nullable:
                    col_desc += " [NOT NULL]"
                if col.description:
                    col_desc += f" — {col.description}"
                lines.append(col_desc)
            
            parts.append("\n".join(lines))
        
        # Add FK relationship summary
        if len(target_tables) > 1:
            relevant_fks = []
            target_set = set(target_tables)
            for fk in self._foreign_keys:
                if fk.source_table in target_set and fk.target_table in target_set:
                    relevant_fks.append(fk)
            
            if relevant_fks:
                parts.append("\nFOREIGN KEY RELATIONSHIPS:")
                for fk in relevant_fks:
                    parts.append(
                        f"  {fk.source_table}.{fk.source_column} → "
                        f"{fk.target_table}.{fk.target_column}"
                    )
            
            # Add join path hints
            join_paths = self.get_join_paths_for_tables(target_tables)
            if join_paths:
                parts.append("\nRECOMMENDED JOIN PATHS:")
                for jp in join_paths:
                    path_desc = []
                    for step in jp.steps:
                        path_desc.append(
                            f"{step.from_table}.{step.from_column} = "
                            f"{step.to_table}.{step.to_column}"
                        )
                    parts.append(
                        f"  {jp.source_table} → {jp.target_table}: " + " → ".join(path_desc)
                    )
        
        return "\n\n".join(parts)
    
    def refresh(self):
        """Re-introspect the database to pick up schema changes."""
        self._tables.clear()
        self._foreign_keys.clear()
        self._adjacency.clear()
        self._join_path_cache.clear()
        self._introspect()
        logger.info("SchemaGraph refreshed")

    # =========================================================================
    # Distinct Value Sampling (prevents hallucinated filter values)
    # =========================================================================
    
    # Constants for distinct value sampling
    _CATEGORICAL_TYPES = {
        "character varying", "varchar", "text", "char", "character",
        "enum", "boolean", "bool"
    }
    _CATEGORICAL_NAME_PATTERNS = [
        "status", "type", "category", "level", "state", "gender", "sex",
        "risk", "stage", "grade", "classification", "priority", "mode",
        "is_", "has_", "flag", "outcome", "result", "diagnosis"
    ]
    _DEFAULT_DISTINCT_LIMIT = 15
    _MAX_COLUMNS_PER_TABLE = 10
    _MAX_DISTINCT_THRESHOLD = 50

    def _is_categorical_column(self, column: ColumnInfo) -> bool:
        """Determine if a column is likely categorical based on type and name."""
        dtype_lower = column.data_type.lower()
        if any(cat_type in dtype_lower for cat_type in self._CATEGORICAL_TYPES):
            return True
        
        col_name_lower = column.name.lower()
        if any(pattern in col_name_lower for pattern in self._CATEGORICAL_NAME_PATTERNS):
            return True
        
        return False

    def _get_categorical_columns(self, table_name: str) -> List[ColumnInfo]:
        """Get columns in a table that are likely categorical."""
        table = self._tables.get(table_name)
        if not table:
            return []
        
        categorical = []
        for col in table.columns:
            if col.is_primary_key or col.is_foreign_key:
                continue
            if self._is_categorical_column(col):
                categorical.append(col)
        
        return categorical[:self._MAX_COLUMNS_PER_TABLE]

    def sample_distinct_values(
        self,
        table_name: str,
        column_name: str,
        limit: int = 15
    ) -> List[str]:
        """
        Sample distinct values from a categorical column.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            limit: Maximum number of distinct values to return
            
        Returns:
            List of distinct values as strings
        """
        if not hasattr(self, '_distinct_values_cache'):
            self._distinct_values_cache: Dict[str, List[str]] = {}
        
        cache_key = f"{table_name}.{column_name}"
        
        if cache_key in self._distinct_values_cache:
            return self._distinct_values_cache[cache_key]
        
        try:
            with self.engine.connect() as conn:
                count_query = text(f"""
                    SELECT COUNT(DISTINCT "{column_name}") 
                    FROM "{self.schema_name}"."{table_name}"
                    WHERE "{column_name}" IS NOT NULL
                """)
                count_result = conn.execute(count_query)
                distinct_count = count_result.scalar() or 0
                
                if distinct_count > self._MAX_DISTINCT_THRESHOLD:
                    logger.debug(f"Skipping {cache_key}: too many distinct values ({distinct_count})")
                    self._distinct_values_cache[cache_key] = []
                    return []
                
                sample_query = text(f"""
                    SELECT DISTINCT "{column_name}"::TEXT 
                    FROM "{self.schema_name}"."{table_name}"
                    WHERE "{column_name}" IS NOT NULL
                    ORDER BY "{column_name}"::TEXT
                    LIMIT :limit
                """)
                result = conn.execute(sample_query, {"limit": limit})
                values = [str(row[0]) for row in result if row[0] is not None]
                
                self._distinct_values_cache[cache_key] = values
                if values:
                    logger.debug(f"Sampled {len(values)} distinct values for {cache_key}")
                
                return values
                
        except Exception as e:
            logger.warning(f"Failed to sample distinct values for {cache_key}: {e}")
            self._distinct_values_cache[cache_key] = []
            return []

    def sample_distinct_values_for_table(self, table_name: str, force_refresh: bool = False) -> Dict[str, List[str]]:
        """Sample distinct values for all categorical columns in a table."""
        if not hasattr(self, '_distinct_values_loaded'):
            self._distinct_values_loaded: Set[str] = set()
        
        if not force_refresh and table_name in self._distinct_values_loaded:
            prefix = f"{table_name}."
            return {
                key.replace(prefix, ""): values
                for key, values in self._distinct_values_cache.items()
                if key.startswith(prefix) and values
            }
        
        categorical_columns = self._get_categorical_columns(table_name)
        result = {}
        
        for col in categorical_columns:
            values = self.sample_distinct_values(table_name, col.name)
            if values:
                result[col.name] = values
        
        self._distinct_values_loaded.add(table_name)
        logger.info(f"Sampled distinct values for {table_name}: {len(result)} categorical columns")
        
        return result

    def get_distinct_values_context(self, tables: Optional[List[str]] = None) -> str:
        """
        Get formatted distinct values context for prompt injection.
        Prevents LLM hallucination by providing actual database values.
        """
        target_tables = tables or list(self._tables.keys())
        parts = []
        
        for table_name in target_tables:
            table_values = self.sample_distinct_values_for_table(table_name)
            
            if table_values:
                table_parts = [f"VALID VALUES FOR {table_name}:"]
                for col_name, values in table_values.items():
                    if len(values) <= 10:
                        values_str = ", ".join(f"'{v}'" for v in values)
                    else:
                        values_str = ", ".join(f"'{v}'" for v in values[:10])
                        values_str += f", ... (+{len(values) - 10} more)"
                    table_parts.append(f"  - {col_name}: {values_str}")
                parts.append("\n".join(table_parts))
        
        if parts:
            header = "CATEGORICAL COLUMN VALUES (use these exact values in WHERE clauses):"
            return header + "\n\n" + "\n\n".join(parts)
        
        return ""
