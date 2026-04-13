"""
DDL Extraction Utility for Structural Schema Indexing.

Phase 2: DDL Extraction Logic
============================================
Implements functions querying information_schema to extract full CREATE TABLE statements.
Injects primary keys, foreign keys, and column data types into the DDL string.
Outputs exactly one contiguous DDL string per database table.

Features:
- Direct information_schema queries for precise DDL extraction
- Complete CREATE TABLE statements including PKs, FKs, and column data types
- Semantic enrichment with natural language descriptions
- Table-level vectorization-ready documents

Usage:
    from app.core.utils.ddl_extractor import DDLExtractor, extract_ddl_from_information_schema
    
    # Direct information_schema extraction
    ddl_string = extract_ddl_from_information_schema(db_url, "orders")
    
    # Full extractor with enrichment
    extractor = DDLExtractor(db_url="postgresql://user:pass@host:5432/db")
    ddl_documents = extractor.extract_all_tables()
"""
import re
import json
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseDialect(Enum):
    """Supported database dialects."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    DUCKDB = "duckdb"


@dataclass
class ColumnInfo:
    """Column metadata with semantic enrichment."""
    name: str
    data_type: str
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_table: Optional[str] = None
    foreign_key_column: Optional[str] = None
    default_value: Optional[str] = None
    description: Optional[str] = None
    business_logic: Optional[str] = None
    
    def to_ddl_line(self, dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL) -> str:
        """Generate DDL line for this column."""
        parts = [f'"{self.name}"', self.data_type]
        
        if not self.is_nullable:
            parts.append("NOT NULL")
        
        if self.default_value is not None:
            parts.append(f"DEFAULT {self.default_value}")
        
        return " ".join(parts)
    
    def to_enriched_description(self) -> str:
        """Generate natural language description of the column."""
        desc_parts = [f"{self.name} ({self.data_type})"]
        
        if self.is_primary_key:
            desc_parts.append("- PRIMARY KEY")
        
        if self.is_foreign_key and self.foreign_key_table:
            desc_parts.append(f"- References {self.foreign_key_table}.{self.foreign_key_column}")
        
        if self.description:
            desc_parts.append(f"- {self.description}")
        
        if self.business_logic:
            desc_parts.append(f"- Business Logic: {self.business_logic}")
        
        return " ".join(desc_parts)


@dataclass
class TableSchema:
    """Complete table schema with DDL and semantic metadata."""
    table_name: str
    columns: List[ColumnInfo] = field(default_factory=list)
    primary_key_columns: List[str] = field(default_factory=list)
    foreign_keys: List[Dict[str, Any]] = field(default_factory=list)
    indexes: List[Dict[str, Any]] = field(default_factory=list)
    description: Optional[str] = None
    row_count: Optional[int] = None
    
    def get_foreign_key_dependencies(self) -> List[str]:
        """Get list of tables this table depends on via foreign keys."""
        return list(set(fk.get("referred_table", "") for fk in self.foreign_keys if fk.get("referred_table")))
    
    def generate_ddl(self, dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL) -> str:
        """Generate CREATE TABLE statement."""
        lines = [f'CREATE TABLE "{self.table_name}" (']
        
        col_lines = []
        for col in self.columns:
            col_lines.append(f"    {col.to_ddl_line(dialect)}")
        
        if self.primary_key_columns:
            pk_cols = ", ".join(f'"{c}"' for c in self.primary_key_columns)
            col_lines.append(f"    PRIMARY KEY ({pk_cols})")
        
        for fk in self.foreign_keys:
            from_cols = ", ".join(f'"{c}"' for c in fk.get("constrained_columns", []))
            to_table = fk.get("referred_table", "")
            to_cols = ", ".join(f'"{c}"' for c in fk.get("referred_columns", []))
            if from_cols and to_table and to_cols:
                col_lines.append(f'    FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols})')
        
        lines.append(",\n".join(col_lines))
        lines.append(");")
        
        return "\n".join(lines)
    
    def generate_enriched_ddl(self, dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL) -> str:
        """Generate enriched DDL with semantic annotations as comments."""
        lines = []
        
        lines.append(f"-- ============================================")
        lines.append(f"-- Table: {self.table_name}")
        if self.description:
            lines.append(f"-- Description: {self.description}")
        if self.row_count is not None:
            lines.append(f"-- Row Count: {self.row_count:,}")
        
        deps = self.get_foreign_key_dependencies()
        if deps:
            lines.append(f"-- Dependencies: {', '.join(deps)}")
        
        lines.append(f"-- ============================================")
        lines.append("")
        lines.append(f'CREATE TABLE "{self.table_name}" (')
        
        col_lines = []
        for col in self.columns:
            col_ddl = f"    {col.to_ddl_line(dialect)}"
            
            comments = []
            if col.is_primary_key:
                comments.append("PK")
            if col.is_foreign_key and col.foreign_key_table:
                comments.append(f"FK -> {col.foreign_key_table}")
            if col.description:
                comments.append(col.description)
            if col.business_logic:
                comments.append(col.business_logic)
            
            if comments:
                col_ddl += f"  -- {'; '.join(comments)}"
            
            col_lines.append(col_ddl)
        
        if self.primary_key_columns:
            pk_cols = ", ".join(f'"{c}"' for c in self.primary_key_columns)
            col_lines.append(f"    PRIMARY KEY ({pk_cols})")
        
        for fk in self.foreign_keys:
            from_cols = ", ".join(f'"{c}"' for c in fk.get("constrained_columns", []))
            to_table = fk.get("referred_table", "")
            to_cols = ", ".join(f'"{c}"' for c in fk.get("referred_columns", []))
            if from_cols and to_table and to_cols:
                fk_line = f'    FOREIGN KEY ({from_cols}) REFERENCES "{to_table}" ({to_cols})'
                col_lines.append(fk_line)
        
        lines.append(",\n".join(col_lines))
        lines.append(");")
        
        return "\n".join(lines)
    
    def to_vector_document(self, dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL) -> Dict[str, Any]:
        """Convert table schema to a vector store document."""
        enriched_ddl = self.generate_enriched_ddl(dialect)
        
        doc_id = hashlib.sha256(f"ddl_{self.table_name}".encode()).hexdigest()[:16]
        
        column_summaries = []
        for col in self.columns:
            summary = {
                "name": col.name,
                "type": col.data_type,
                "pk": col.is_primary_key,
                "fk": col.is_foreign_key,
            }
            if col.description:
                summary["desc"] = col.description
            column_summaries.append(summary)
        
        # Get FK dependencies as list of table names
        fk_dependencies = self.get_foreign_key_dependencies()
        
        metadata = {
            "doc_type": "ddl_schema",
            "table_name": self.table_name,
            "column_count": len(self.columns),
            "primary_keys": self.primary_key_columns,
            # Store FK dependencies in both keys for compatibility with schema_retriever
            "foreign_keys": fk_dependencies,  # Used by schema_retriever.py for FK resolution
            "foreign_key_dependencies": fk_dependencies,  # Legacy key
            "has_foreign_keys": len(self.foreign_keys) > 0,
            "columns": json.dumps(column_summaries),
        }
        
        if self.description:
            metadata["table_description"] = self.description
        
        if self.row_count is not None:
            metadata["row_count"] = self.row_count
        
        return {
            "id": doc_id,
            "content": enriched_ddl,
            "metadata": metadata,
        }


# =============================================================================
# Phase 2: Direct information_schema DDL Extraction Functions
# =============================================================================

def extract_ddl_from_information_schema(
    db_url: str,
    table_name: str,
    schema_name: str = "public",
) -> str:
    """
    Extract a complete CREATE TABLE DDL statement by querying information_schema directly.
    
    This function queries the database's information_schema to build a precise DDL
    statement including all columns, data types, primary keys, and foreign keys.
    
    Args:
        db_url: Database connection URL
        table_name: Name of the table to extract
        schema_name: Schema name (default: "public" for PostgreSQL)
    
    Returns:
        A single contiguous DDL string for the table
    
    Example:
        >>> ddl = extract_ddl_from_information_schema(
        ...     "postgresql://user:pass@localhost:5432/mydb",
        ...     "orders"
        ... )
        >>> print(ddl)
        CREATE TABLE "orders" (
            "id" INTEGER NOT NULL,
            "customer_id" INTEGER,
            "order_date" TIMESTAMP,
            "total_amount" NUMERIC(10,2),
            PRIMARY KEY ("id"),
            FOREIGN KEY ("customer_id") REFERENCES "customers" ("id")
        );
    """
    db_url = _normalize_db_url(db_url)
    engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
    
    try:
        dialect = _detect_dialect_from_url(db_url)
        
        with engine.connect() as conn:
            columns = _query_columns_from_information_schema(conn, table_name, schema_name, dialect)
            pk_columns = _query_primary_keys_from_information_schema(conn, table_name, schema_name, dialect)
            foreign_keys = _query_foreign_keys_from_information_schema(conn, table_name, schema_name, dialect)
            
            ddl = _build_ddl_string(table_name, columns, pk_columns, foreign_keys)
            
            return ddl
    finally:
        engine.dispose()


def extract_all_ddls_from_information_schema(
    db_url: str,
    schema_name: str = "public",
    include_tables: Optional[List[str]] = None,
    exclude_tables: Optional[List[str]] = None,
) -> Dict[str, str]:
    """
    Extract DDL statements for all tables in a database schema.
    
    Args:
        db_url: Database connection URL
        schema_name: Schema name (default: "public")
        include_tables: Optional list of tables to include (None = all)
        exclude_tables: Optional list of tables to exclude
    
    Returns:
        Dict mapping table names to their DDL strings
    """
    db_url = _normalize_db_url(db_url)
    engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
    
    try:
        dialect = _detect_dialect_from_url(db_url)
        
        with engine.connect() as conn:
            table_names = _query_table_names(conn, schema_name, dialect)
            
            if include_tables:
                table_names = [t for t in table_names if t in include_tables]
            if exclude_tables:
                table_names = [t for t in table_names if t not in exclude_tables]
            
            ddls = {}
            for table_name in table_names:
                try:
                    columns = _query_columns_from_information_schema(conn, table_name, schema_name, dialect)
                    pk_columns = _query_primary_keys_from_information_schema(conn, table_name, schema_name, dialect)
                    foreign_keys = _query_foreign_keys_from_information_schema(conn, table_name, schema_name, dialect)
                    
                    ddl = _build_ddl_string(table_name, columns, pk_columns, foreign_keys)
                    ddls[table_name] = ddl
                    
                    logger.info(f"Extracted DDL for table: {table_name}")
                except Exception as e:
                    logger.error(f"Failed to extract DDL for {table_name}: {e}")
            
            return ddls
    finally:
        engine.dispose()


def _normalize_db_url(url: str) -> str:
    """Normalize common typos in database URLs."""
    url = url.replace("postgressql://", "postgresql://")
    url = url.replace("postgress://", "postgresql://")
    url = url.replace("postgres://", "postgresql://")
    return url


def _detect_dialect_from_url(url: str) -> DatabaseDialect:
    """Detect database dialect from connection URL."""
    url_lower = url.lower()
    if "postgresql" in url_lower or "postgres" in url_lower:
        return DatabaseDialect.POSTGRESQL
    elif "mysql" in url_lower:
        return DatabaseDialect.MYSQL
    elif "sqlite" in url_lower:
        return DatabaseDialect.SQLITE
    elif "duckdb" in url_lower:
        return DatabaseDialect.DUCKDB
    else:
        return DatabaseDialect.POSTGRESQL


def _query_table_names(
    conn,
    schema_name: str,
    dialect: DatabaseDialect,
) -> List[str]:
    """Query all table names from information_schema."""
    if dialect == DatabaseDialect.POSTGRESQL:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = :schema_name 
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """), {"schema_name": schema_name})
    elif dialect == DatabaseDialect.MYSQL:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE()
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """))
    elif dialect == DatabaseDialect.SQLITE:
        result = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type = 'table' 
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """))
    else:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = :schema_name
            ORDER BY table_name
        """), {"schema_name": schema_name})
    
    return [row[0] for row in result.fetchall()]


def _query_columns_from_information_schema(
    conn,
    table_name: str,
    schema_name: str,
    dialect: DatabaseDialect,
) -> List[Dict[str, Any]]:
    """
    Query column information from information_schema.columns.
    
    Returns list of column dicts with: name, data_type, is_nullable, column_default, ordinal_position
    """
    if dialect == DatabaseDialect.POSTGRESQL:
        result = conn.execute(text("""
            SELECT 
                column_name,
                data_type,
                udt_name,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            ORDER BY ordinal_position
        """), {"schema_name": schema_name, "table_name": table_name})
        
        columns = []
        for row in result.fetchall():
            data_type = _build_postgresql_type_string(
                row[1], row[2], row[3], row[4], row[5],
            )
            
            columns.append({
                "name": row[0],
                "data_type": data_type,
                "is_nullable": row[6] == "YES",
                "column_default": row[7],
                "ordinal_position": row[8],
            })
        return columns
    
    elif dialect == DatabaseDialect.MYSQL:
        result = conn.execute(text("""
            SELECT 
                column_name,
                column_type,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
            ORDER BY ordinal_position
        """), {"table_name": table_name})
        
        columns = []
        for row in result.fetchall():
            columns.append({
                "name": row[0],
                "data_type": row[1].upper(),
                "is_nullable": row[2] == "YES",
                "column_default": row[3],
                "ordinal_position": row[4],
            })
        return columns
    
    elif dialect == DatabaseDialect.SQLITE:
        result = conn.execute(text(f'PRAGMA table_info("{table_name}")'))
        
        columns = []
        for row in result.fetchall():
            columns.append({
                "name": row[1],
                "data_type": row[2] or "TEXT",
                "is_nullable": row[3] == 0,
                "column_default": row[4],
                "ordinal_position": row[0],
            })
        return columns
    
    else:
        result = conn.execute(text("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
        """), {"table_name": table_name})
        
        columns = []
        for row in result.fetchall():
            columns.append({
                "name": row[0],
                "data_type": row[1].upper() if row[1] else "TEXT",
                "is_nullable": row[2] == "YES" if row[2] else True,
                "column_default": row[3],
                "ordinal_position": row[4],
            })
        return columns


def _build_postgresql_type_string(
    data_type: str,
    udt_name: str,
    char_max_length: Optional[int],
    numeric_precision: Optional[int],
    numeric_scale: Optional[int],
) -> str:
    """Build precise PostgreSQL data type string with length/precision."""
    data_type_upper = data_type.upper() if data_type else "TEXT"
    
    if data_type_upper == "ARRAY":
        return f"{udt_name.upper()}[]" if udt_name else "TEXT[]"
    
    if data_type_upper == "USER-DEFINED":
        return udt_name.upper() if udt_name else "TEXT"
    
    if data_type_upper in ("CHARACTER VARYING", "VARCHAR"):
        if char_max_length:
            return f"VARCHAR({char_max_length})"
        return "VARCHAR"
    
    if data_type_upper in ("CHARACTER", "CHAR"):
        if char_max_length:
            return f"CHAR({char_max_length})"
        return "CHAR"
    
    if data_type_upper in ("NUMERIC", "DECIMAL"):
        if numeric_precision is not None:
            if numeric_scale is not None and numeric_scale > 0:
                return f"NUMERIC({numeric_precision},{numeric_scale})"
            return f"NUMERIC({numeric_precision})"
        return "NUMERIC"
    
    if "TIMESTAMP" in data_type_upper:
        if "WITH TIME ZONE" in data_type_upper:
            return "TIMESTAMPTZ"
        return "TIMESTAMP"
    
    type_mappings = {
        "INTEGER": "INTEGER",
        "BIGINT": "BIGINT",
        "SMALLINT": "SMALLINT",
        "REAL": "REAL",
        "DOUBLE PRECISION": "DOUBLE PRECISION",
        "BOOLEAN": "BOOLEAN",
        "TEXT": "TEXT",
        "DATE": "DATE",
        "TIME": "TIME",
        "UUID": "UUID",
        "JSON": "JSON",
        "JSONB": "JSONB",
        "BYTEA": "BYTEA",
    }
    
    return type_mappings.get(data_type_upper, data_type_upper)


def _query_primary_keys_from_information_schema(
    conn,
    table_name: str,
    schema_name: str,
    dialect: DatabaseDialect,
) -> List[str]:
    """
    Query primary key columns from information_schema.
    
    Returns list of column names that form the primary key.
    """
    if dialect == DatabaseDialect.POSTGRESQL:
        result = conn.execute(text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = :schema_name
              AND tc.table_name = :table_name
            ORDER BY kcu.ordinal_position
        """), {"schema_name": schema_name, "table_name": table_name})
        
        return [row[0] for row in result.fetchall()]
    
    elif dialect == DatabaseDialect.MYSQL:
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND constraint_name = 'PRIMARY'
            ORDER BY ordinal_position
        """), {"table_name": table_name})
        
        return [row[0] for row in result.fetchall()]
    
    elif dialect == DatabaseDialect.SQLITE:
        result = conn.execute(text(f'PRAGMA table_info("{table_name}")'))
        
        pk_columns = []
        for row in result.fetchall():
            if row[5] > 0:
                pk_columns.append((row[5], row[1]))
        
        pk_columns.sort(key=lambda x: x[0])
        return [col[1] for col in pk_columns]
    
    else:
        try:
            inspector = inspect(conn.engine)
            pk_constraint = inspector.get_pk_constraint(table_name)
            return pk_constraint.get("constrained_columns", []) if pk_constraint else []
        except Exception:
            return []


def _query_foreign_keys_from_information_schema(
    conn,
    table_name: str,
    schema_name: str,
    dialect: DatabaseDialect,
) -> List[Dict[str, Any]]:
    """
    Query foreign key constraints from information_schema.
    
    Returns list of FK dicts with: constraint_name, columns, ref_table, ref_columns
    """
    if dialect == DatabaseDialect.POSTGRESQL:
        result = conn.execute(text("""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                kcu.ordinal_position
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = :schema_name
              AND tc.table_name = :table_name
            ORDER BY tc.constraint_name, kcu.ordinal_position
        """), {"schema_name": schema_name, "table_name": table_name})
        
        fk_dict: Dict[str, Dict[str, Any]] = {}
        for row in result.fetchall():
            constraint_name = row[0]
            if constraint_name not in fk_dict:
                fk_dict[constraint_name] = {
                    "constraint_name": constraint_name,
                    "columns": [],
                    "ref_table": row[2],
                    "ref_columns": [],
                }
            fk_dict[constraint_name]["columns"].append(row[1])
            fk_dict[constraint_name]["ref_columns"].append(row[3])
        
        return list(fk_dict.values())
    
    elif dialect == DatabaseDialect.MYSQL:
        result = conn.execute(text("""
            SELECT
                constraint_name,
                column_name,
                referenced_table_name,
                referenced_column_name,
                ordinal_position
            FROM information_schema.key_column_usage
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
              AND referenced_table_name IS NOT NULL
            ORDER BY constraint_name, ordinal_position
        """), {"table_name": table_name})
        
        fk_dict: Dict[str, Dict[str, Any]] = {}
        for row in result.fetchall():
            constraint_name = row[0]
            if constraint_name not in fk_dict:
                fk_dict[constraint_name] = {
                    "constraint_name": constraint_name,
                    "columns": [],
                    "ref_table": row[2],
                    "ref_columns": [],
                }
            fk_dict[constraint_name]["columns"].append(row[1])
            fk_dict[constraint_name]["ref_columns"].append(row[3])
        
        return list(fk_dict.values())
    
    elif dialect == DatabaseDialect.SQLITE:
        result = conn.execute(text(f'PRAGMA foreign_key_list("{table_name}")'))
        
        fk_dict: Dict[int, Dict[str, Any]] = {}
        for row in result.fetchall():
            fk_id = row[0]
            if fk_id not in fk_dict:
                fk_dict[fk_id] = {
                    "constraint_name": f"fk_{table_name}_{fk_id}",
                    "columns": [],
                    "ref_table": row[2],
                    "ref_columns": [],
                }
            fk_dict[fk_id]["columns"].append(row[3])
            fk_dict[fk_id]["ref_columns"].append(row[4])
        
        return list(fk_dict.values())
    
    else:
        try:
            inspector = inspect(conn.engine)
            fks = inspector.get_foreign_keys(table_name)
            return [
                {
                    "constraint_name": fk.get("name", f"fk_{i}"),
                    "columns": fk.get("constrained_columns", []),
                    "ref_table": fk.get("referred_table"),
                    "ref_columns": fk.get("referred_columns", []),
                }
                for i, fk in enumerate(fks)
            ]
        except Exception:
            return []


def _build_ddl_string(
    table_name: str,
    columns: List[Dict[str, Any]],
    pk_columns: List[str],
    foreign_keys: List[Dict[str, Any]],
) -> str:
    """
    Build a complete, contiguous CREATE TABLE DDL string.
    
    This produces exactly one DDL string per table, including:
    - All column definitions with data types
    - NOT NULL constraints
    - DEFAULT values
    - PRIMARY KEY constraint
    - FOREIGN KEY constraints
    
    Args:
        table_name: Name of the table
        columns: List of column info dicts
        pk_columns: List of primary key column names
        foreign_keys: List of foreign key constraint dicts
    
    Returns:
        A single contiguous DDL string
    """
    lines = [f'CREATE TABLE "{table_name}" (']
    
    col_definitions = []
    for col in columns:
        col_def = f'    "{col["name"]}" {col["data_type"]}'
        
        if not col.get("is_nullable", True):
            col_def += " NOT NULL"
        
        if col.get("column_default") is not None:
            default_val = col["column_default"]
            if isinstance(default_val, str):
                default_val = re.sub(r'::[a-zA-Z\s]+(\[\])?', '', default_val)
            col_def += f" DEFAULT {default_val}"
        
        col_definitions.append(col_def)
    
    if pk_columns:
        pk_cols_str = ", ".join(f'"{col}"' for col in pk_columns)
        col_definitions.append(f"    PRIMARY KEY ({pk_cols_str})")
    
    for fk in foreign_keys:
        fk_cols = ", ".join(f'"{col}"' for col in fk.get("columns", []))
        ref_table = fk.get("ref_table", "")
        ref_cols = ", ".join(f'"{col}"' for col in fk.get("ref_columns", []))
        
        if fk_cols and ref_table and ref_cols:
            col_definitions.append(f'    FOREIGN KEY ({fk_cols}) REFERENCES "{ref_table}" ({ref_cols})')
    
    lines.append(",\n".join(col_definitions))
    lines.append(");")
    
    return "\n".join(lines)


def get_table_ddl_with_metadata(
    db_url: str,
    table_name: str,
    schema_name: str = "public",
    data_dictionary: Optional[Dict[str, str]] = None,
    include_row_count: bool = True,
) -> Dict[str, Any]:
    """
    Extract DDL with additional metadata for embedding.
    
    This is a convenience function that combines DDL extraction with
    metadata collection, suitable for vectorization.
    
    Args:
        db_url: Database connection URL
        table_name: Name of the table
        schema_name: Schema name
        data_dictionary: Optional column descriptions
        include_row_count: Whether to query row count
    
    Returns:
        Dict with 'ddl', 'metadata', and 'enriched_ddl' keys
    """
    db_url = _normalize_db_url(db_url)
    engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
    
    try:
        dialect = _detect_dialect_from_url(db_url)
        
        with engine.connect() as conn:
            columns = _query_columns_from_information_schema(conn, table_name, schema_name, dialect)
            pk_columns = _query_primary_keys_from_information_schema(conn, table_name, schema_name, dialect)
            foreign_keys = _query_foreign_keys_from_information_schema(conn, table_name, schema_name, dialect)
            
            ddl = _build_ddl_string(table_name, columns, pk_columns, foreign_keys)
            
            row_count = None
            if include_row_count:
                try:
                    result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                    row = result.fetchone()
                    row_count = int(row[0]) if row else None
                except Exception as e:
                    logger.warning(f"Failed to get row count for {table_name}: {e}")
            
            enriched_ddl = _build_enriched_ddl_string(
                table_name, columns, pk_columns, foreign_keys,
                data_dictionary or {}, row_count
            )
            
            fk_dependencies = list(set(fk.get("ref_table", "") for fk in foreign_keys if fk.get("ref_table")))
            
            metadata = {
                "table_name": table_name,
                "schema_name": schema_name,
                "column_count": len(columns),
                "primary_key_columns": pk_columns,
                "foreign_key_count": len(foreign_keys),
                "foreign_key_dependencies": fk_dependencies,
                "row_count": row_count,
            }
            
            return {
                "ddl": ddl,
                "enriched_ddl": enriched_ddl,
                "metadata": metadata,
            }
    finally:
        engine.dispose()


def _build_enriched_ddl_string(
    table_name: str,
    columns: List[Dict[str, Any]],
    pk_columns: List[str],
    foreign_keys: List[Dict[str, Any]],
    data_dictionary: Dict[str, str],
    row_count: Optional[int] = None,
) -> str:
    """
    Build enriched DDL with semantic comments for better LLM understanding.
    
    Returns a contiguous DDL string with inline comments.
    """
    fk_lookup = {}
    for fk in foreign_keys:
        ref_table = fk.get("ref_table", "")
        for i, col in enumerate(fk.get("columns", [])):
            ref_cols = fk.get("ref_columns", [])
            fk_lookup[col] = {
                "table": ref_table,
                "column": ref_cols[i] if i < len(ref_cols) else None,
            }
    
    lines = []
    
    lines.append("-- ============================================")
    lines.append(f"-- Table: {table_name}")
    if row_count is not None:
        lines.append(f"-- Row Count: {row_count:,}")
    
    fk_deps = list(set(fk.get("ref_table", "") for fk in foreign_keys if fk.get("ref_table")))
    if fk_deps:
        lines.append(f"-- Dependencies: {', '.join(fk_deps)}")
    
    lines.append("-- ============================================")
    lines.append("")
    lines.append(f'CREATE TABLE "{table_name}" (')
    
    col_definitions = []
    for col in columns:
        col_name = col["name"]
        col_def = f'    "{col_name}" {col["data_type"]}'
        
        if not col.get("is_nullable", True):
            col_def += " NOT NULL"
        
        if col.get("column_default") is not None:
            default_val = col["column_default"]
            if isinstance(default_val, str):
                default_val = re.sub(r'::[a-zA-Z\s]+(\[\])?', '', default_val)
            col_def += f" DEFAULT {default_val}"
        
        comments = []
        if col_name in pk_columns:
            comments.append("PK")
        if col_name in fk_lookup:
            fk_info = fk_lookup[col_name]
            comments.append(f"FK -> {fk_info['table']}")
        
        desc = data_dictionary.get(f"{table_name}.{col_name}") or data_dictionary.get(col_name)
        if desc:
            comments.append(desc)
        
        if comments:
            col_def += f"  -- {'; '.join(comments)}"
        
        col_definitions.append(col_def)
    
    if pk_columns:
        pk_cols_str = ", ".join(f'"{col}"' for col in pk_columns)
        col_definitions.append(f"    PRIMARY KEY ({pk_cols_str})")
    
    for fk in foreign_keys:
        fk_cols = ", ".join(f'"{col}"' for col in fk.get("columns", []))
        ref_table = fk.get("ref_table", "")
        ref_cols = ", ".join(f'"{col}"' for col in fk.get("ref_columns", []))
        
        if fk_cols and ref_table and ref_cols:
            col_definitions.append(f'    FOREIGN KEY ({fk_cols}) REFERENCES "{ref_table}" ({ref_cols})')
    
    lines.append(",\n".join(col_definitions))
    lines.append(");")
    
    return "\n".join(lines)


class DDLExtractor:
    """
    Extracts DDL statements from connected databases with semantic enrichment.
    
    Supports PostgreSQL, MySQL, SQLite, and DuckDB.
    """
    
    def __init__(
        self,
        db_url: Optional[str] = None,
        engine: Optional[Engine] = None,
        data_dictionary: Optional[Dict[str, Any]] = None,
        business_rules: Optional[Dict[str, Dict[str, str]]] = None,
        schema_name: Optional[str] = None,
    ):
        """
        Initialize DDL extractor.
        
        Args:
            db_url: Database connection URL (postgresql://user:pass@host:5432/db)
            engine: Existing SQLAlchemy engine (alternative to db_url)
            data_dictionary: Dict mapping column names to descriptions
            business_rules: Dict mapping table.column to business logic descriptions
            schema_name: Database schema name (default: auto-detect or 'public')
        """
        if engine:
            self.engine = engine
        elif db_url:
            db_url = _normalize_db_url(db_url)
            self.engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
        else:
            raise ValueError("Either db_url or engine must be provided")
        
        self.data_dictionary = data_dictionary or {}
        self.business_rules = business_rules or {}
        self.dialect = self._detect_dialect()
        self.inspector = inspect(self.engine)
        self.schema_name = schema_name  # Will be auto-detected if None
    
    def _detect_dialect(self) -> DatabaseDialect:
        """Detect database dialect from engine."""
        dialect_name = self.engine.dialect.name.lower()
        
        if "postgresql" in dialect_name or "postgres" in dialect_name:
            return DatabaseDialect.POSTGRESQL
        elif "mysql" in dialect_name:
            return DatabaseDialect.MYSQL
        elif "sqlite" in dialect_name:
            return DatabaseDialect.SQLITE
        elif "duckdb" in dialect_name:
            return DatabaseDialect.DUCKDB
        else:
            logger.warning(f"Unknown dialect '{dialect_name}', defaulting to PostgreSQL")
            return DatabaseDialect.POSTGRESQL
    
    def _get_column_description(self, table_name: str, column_name: str) -> Optional[str]:
        """Get description for a column from data dictionary."""
        full_key = f"{table_name}.{column_name}"
        if full_key in self.data_dictionary:
            return self.data_dictionary[full_key]
        
        if column_name in self.data_dictionary:
            return self.data_dictionary[column_name]
        
        return self._infer_column_description(column_name)
    
    def _infer_column_description(self, column_name: str) -> Optional[str]:
        """Infer description from common column naming patterns."""
        name_lower = column_name.lower()
        
        patterns = {
            r"^id$": "Primary identifier",
            r"_id$": "Foreign key reference",
            r"^created_at$": "Record creation timestamp",
            r"^updated_at$": "Last modification timestamp",
            r"^deleted_at$": "Soft deletion timestamp",
            r"^is_": "Boolean flag",
            r"^has_": "Boolean indicator",
            r"^status": "Status indicator",
            r"^email$": "Email address",
            r"^phone": "Phone number",
            r"^address": "Address field",
            r"_count$": "Count/quantity",
            r"_date$": "Date field",
            r"_time$": "Time field",
            r"_amount$": "Monetary amount",
            r"_price$": "Price value",
            r"_total$": "Total/sum value",
        }
        
        for pattern, description in patterns.items():
            if re.search(pattern, name_lower):
                return description
        
        return None
    
    def _get_business_logic(self, table_name: str, column_name: str) -> Optional[str]:
        """Get business logic description for a column."""
        full_key = f"{table_name}.{column_name}"
        return self.business_rules.get(full_key)
    
    def _get_row_count(self, table_name: str) -> Optional[int]:
        """Get approximate row count for a table."""
        # Handle schema-qualified table names (e.g., "rnacen.auth_permission")
        if "." in table_name:
            schema_name, actual_table = table_name.split(".", 1)
            # PostgreSQL requires separate quoting: "schema"."table"
            qualified_name = f'"{schema_name}"."{actual_table}"'
            simple_name = actual_table
        else:
            schema_name = "public"
            qualified_name = f'"{table_name}"'
            simple_name = table_name
        
        try:
            with self.engine.connect() as conn:
                if self.dialect == DatabaseDialect.POSTGRESQL:
                    # Try pg_class estimate first (fast, no table scan)
                    result = conn.execute(text("""
                        SELECT reltuples::bigint AS estimate
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relname = :table_name
                          AND n.nspname = :schema_name
                    """), {"table_name": simple_name, "schema_name": schema_name})
                    row = result.fetchone()
                    if row and row[0] > 0:
                        return int(row[0])
                
                # Fall back to COUNT(*) with properly quoted table name
                result = conn.execute(text(f'SELECT COUNT(*) FROM {qualified_name}'))
                row = result.fetchone()
                return int(row[0]) if row else None
        except Exception as e:
            logger.warning(f"Failed to get row count for {table_name}: {e}")
            return None
    
    def extract_table_schema(self, table_name: str, include_row_count: bool = True) -> TableSchema:
        """
        Extract complete schema for a single table.
        
        Uses information_schema queries which work with limited DB permissions.
        Falls back to inspector only if information_schema fails.
        
        Args:
            table_name: Name of the table to extract
            include_row_count: Whether to query row count (can be slow for large tables)
        
        Returns:
            TableSchema with columns, PKs, FKs, and semantic metadata
        """
        logger.info(f"Extracting schema for table: {table_name}")
        
        # Determine schema name: from table_name if qualified, else use instance schema_name, else 'public'
        if "." in table_name:
            schema_name, actual_table_name = table_name.split(".", 1)
        else:
            schema_name = self.schema_name or "public"
            actual_table_name = table_name
        
        # Build the full qualified name for the TableSchema
        full_table_name = f"{schema_name}.{actual_table_name}" if schema_name != "public" else actual_table_name
        
        try:
            # Use information_schema queries (works with limited permissions)
            with self.engine.connect() as conn:
                columns_data = _query_columns_from_information_schema(conn, actual_table_name, schema_name, self.dialect)
                pk_columns = _query_primary_keys_from_information_schema(conn, actual_table_name, schema_name, self.dialect)
                foreign_keys_data = _query_foreign_keys_from_information_schema(conn, actual_table_name, schema_name, self.dialect)
                
                # Build FK lookup
                fk_column_info = {}
                foreign_keys = []
                for fk in foreign_keys_data:
                    ref_table = fk.get("ref_table")
                    ref_columns = fk.get("ref_columns", [])
                    constrained_columns = fk.get("columns", [])
                    
                    foreign_keys.append({
                        "name": fk.get("constraint_name"),
                        "constrained_columns": constrained_columns,
                        "referred_table": ref_table,
                        "referred_columns": ref_columns,
                    })
                    
                    for i, col in enumerate(constrained_columns):
                        fk_column_info[col] = {
                            "table": ref_table,
                            "column": ref_columns[i] if i < len(ref_columns) else None,
                        }
                
                pk_columns_set = set(pk_columns)
                
                columns = []
                for col_data in columns_data:
                    col_name = col_data["name"]
                    fk_info = fk_column_info.get(col_name, {})
                    
                    column_info = ColumnInfo(
                        name=col_name,
                        data_type=col_data["data_type"],
                        is_nullable=col_data.get("is_nullable", True),
                        is_primary_key=col_name in pk_columns_set,
                        is_foreign_key=col_name in fk_column_info,
                        foreign_key_table=fk_info.get("table"),
                        foreign_key_column=fk_info.get("column"),
                        default_value=str(col_data.get("column_default")) if col_data.get("column_default") else None,
                        description=self._get_column_description(table_name, col_name),
                        business_logic=self._get_business_logic(table_name, col_name),
                    )
                    columns.append(column_info)
                
                row_count = None
                if include_row_count:
                    row_count = self._get_row_count(table_name)
                
                table_description = self.data_dictionary.get(f"_table_{table_name}")
                
                return TableSchema(
                    table_name=full_table_name,
                    columns=columns,
                    primary_key_columns=pk_columns,
                    foreign_keys=foreign_keys,
                    indexes=[],
                    description=table_description,
                    row_count=row_count,
                )
        except Exception as e:
            logger.warning(f"information_schema extraction failed for {table_name}: {e}")
            raise
    
    def extract_all_tables(
        self,
        include_row_counts: bool = True,
        tables_filter: Optional[List[str]] = None,
        max_workers: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Extract DDL documents for all tables in the database using concurrent extraction.
        
        Args:
            include_row_counts: Whether to include row counts in metadata
            tables_filter: Optional list of table names to include (None = all tables).
                          Can be schema-qualified (e.g., 'rnacen.table_name').
            max_workers: Maximum number of concurrent extraction threads (default: 10)
        
        Returns:
            List of vector documents ready for embedding
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        # Auto-detect schema from tables_filter if provided and schema_name not set
        if tables_filter and not self.schema_name:
            for t in tables_filter:
                if "." in t:
                    detected_schema = t.split(".")[0]
                    self.schema_name = detected_schema
                    logger.info(f"Auto-detected database schema: {detected_schema}")
                    break
        
        # Get table names from the correct schema
        if self.schema_name and self.dialect == DatabaseDialect.POSTGRESQL:
            with self.engine.connect() as conn:
                table_names = _query_table_names(conn, self.schema_name, self.dialect)
            logger.info(f"Found {len(table_names)} tables in schema '{self.schema_name}'")
        else:
            table_names = self.inspector.get_table_names()
        
        # Apply filter - handle both qualified and unqualified names
        if tables_filter:
            filter_table_names = set()
            for t in tables_filter:
                if "." in t:
                    filter_table_names.add(t.split(".", 1)[1])
                else:
                    filter_table_names.add(t)
            table_names = [t for t in table_names if t in filter_table_names]
        
        total_tables = len(table_names)
        logger.info(f"Extracting DDL for {total_tables} tables using {max_workers} concurrent workers")
        
        start_time = time.time()
        documents = []
        failed_count = 0
        
        def extract_single_table(table_name: str) -> Optional[Dict[str, Any]]:
            """Worker function to extract a single table's DDL."""
            try:
                qualified_name = f"{self.schema_name}.{table_name}" if self.schema_name else table_name
                schema = self.extract_table_schema(qualified_name, include_row_count=include_row_counts)
                doc = schema.to_vector_document(self.dialect)
                return {"doc": doc, "table": qualified_name, "columns": len(schema.columns)}
            except Exception as e:
                logger.error(f"Failed to extract DDL for {table_name}: {e}")
                return None
        
        # Use ThreadPoolExecutor for concurrent extraction
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_table = {
                executor.submit(extract_single_table, table_name): table_name 
                for table_name in table_names
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_table):
                table_name = future_to_table[future]
                completed += 1
                
                try:
                    result = future.result()
                    if result:
                        documents.append(result["doc"])
                        # Log progress every 20 tables or at the end
                        if completed % 20 == 0 or completed == total_tables:
                            elapsed = time.time() - start_time
                            rate = completed / elapsed if elapsed > 0 else 0
                            logger.info(f"DDL extraction progress: {completed}/{total_tables} tables ({rate:.1f} tables/sec)")
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"Future failed for {table_name}: {e}")
                    failed_count += 1
        
        elapsed = time.time() - start_time
        logger.info(f"DDL extraction complete: {len(documents)} tables in {elapsed:.1f}s ({len(documents)/elapsed:.1f} tables/sec), {failed_count} failed")
        
        return documents
    
    def extract_relationships_document(self) -> Dict[str, Any]:
        """
        Generate a document describing all table relationships.
        
        This provides the LLM with a high-level view of how tables connect,
        which is crucial for generating correct JOINs.
        
        Uses information_schema queries for better performance and compatibility
        with limited database permissions.
        """
        import time
        start_time = time.time()
        
        # Get table names using schema-aware query
        schema_name = self.schema_name or "public"
        with self.engine.connect() as conn:
            table_names = _query_table_names(conn, schema_name, self.dialect)
        
        logger.info(f"Extracting relationships for {len(table_names)} tables in schema '{schema_name}'")
        
        # Query ALL foreign keys in one batch query (much faster than per-table)
        relationships = []
        if self.dialect == DatabaseDialect.POSTGRESQL:
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text("""
                        SELECT
                            tc.table_name AS from_table,
                            kcu.column_name AS from_column,
                            ccu.table_name AS to_table,
                            ccu.column_name AS to_column
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                            ON tc.constraint_name = kcu.constraint_name
                            AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                            ON ccu.constraint_name = tc.constraint_name
                            AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND tc.table_schema = :schema_name
                        ORDER BY tc.table_name, kcu.ordinal_position
                    """), {"schema_name": schema_name})
                    
                    # Group by relationship
                    fk_map = {}
                    for row in result.fetchall():
                        key = f"{row[0]}->{row[2]}"
                        if key not in fk_map:
                            fk_map[key] = {
                                "from_table": row[0],
                                "from_columns": [],
                                "to_table": row[2],
                                "to_columns": [],
                            }
                        fk_map[key]["from_columns"].append(row[1])
                        fk_map[key]["to_columns"].append(row[3])
                    
                    relationships = list(fk_map.values())
                    
            except Exception as e:
                logger.warning(f"Failed to query foreign keys: {e}")
        
        rel_descriptions = []
        for rel in relationships:
            from_cols = ", ".join(rel["from_columns"])
            to_cols = ", ".join(rel["to_columns"])
            rel_descriptions.append(
                f"- {rel['from_table']}.{from_cols} -> {rel['to_table']}.{to_cols}"
            )
        
        content = f"""-- ============================================
-- Database Relationships Overview
-- ============================================
-- Total Tables: {len(table_names)}
-- Total Relationships: {len(relationships)}
-- ============================================

Foreign Key Relationships:
{chr(10).join(rel_descriptions) if rel_descriptions else "No foreign key relationships defined."}

Tables:
{chr(10).join(f"- {t}" for t in sorted(table_names))}
"""
        
        doc_id = hashlib.sha256("ddl_relationships_overview".encode()).hexdigest()[:16]
        
        elapsed = time.time() - start_time
        logger.info(f"Relationships extraction complete: {len(relationships)} FKs in {elapsed:.1f}s")
        
        return {
            "id": doc_id,
            "content": content,
            "metadata": {
                "doc_type": "ddl_relationships",
                "table_count": len(table_names),
                "relationship_count": len(relationships),
                "tables": json.dumps(table_names),
            },
        }
    
    def close(self):
        """Close database connection."""
        if self.engine:
            self.engine.dispose()


class DuckDBDDLExtractor:
    """
    DDL extractor specialized for DuckDB file sources.
    
    Since file uploads don't have traditional foreign keys,
    this focuses on column types and inferred relationships.
    """
    
    def __init__(
        self,
        duckdb_path: str,
        table_name: str,
        data_dictionary: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize DuckDB DDL extractor.
        
        Args:
            duckdb_path: Path to DuckDB file
            table_name: Name of the table to extract
            data_dictionary: Dict mapping column names to descriptions
        """
        import duckdb
        
        self.duckdb_path = duckdb_path
        self.table_name = table_name
        self.data_dictionary = data_dictionary or {}
        
        # Connect without read_only flag to avoid conflicts with other connections
        # DuckDB doesn't allow mixing read_only and read_write connections to same file
        self.conn = duckdb.connect(duckdb_path)
    
    def _get_column_description(self, column_name: str) -> Optional[str]:
        """Get description for a column from data dictionary."""
        full_key = f"{self.table_name}.{column_name}"
        if full_key in self.data_dictionary:
            return self.data_dictionary[full_key]
        if column_name in self.data_dictionary:
            return self.data_dictionary[column_name]
        return None
    
    def extract_table_schema(self) -> TableSchema:
        """Extract schema from DuckDB table."""
        logger.info(f"Extracting DuckDB schema for table: {self.table_name}")
        
        result = self.conn.execute(f'DESCRIBE "{self.table_name}"').fetchall()
        
        columns = []
        for row in result:
            col_name = row[0]
            col_type = row[1]
            is_nullable = row[2] == "YES" if len(row) > 2 else True
            
            column_info = ColumnInfo(
                name=col_name,
                data_type=col_type,
                is_nullable=is_nullable,
                is_primary_key=False,
                is_foreign_key=False,
                description=self._get_column_description(col_name),
            )
            columns.append(column_info)
        
        count_result = self.conn.execute(f'SELECT COUNT(*) FROM "{self.table_name}"').fetchone()
        row_count = count_result[0] if count_result else None
        
        table_description = self.data_dictionary.get(f"_table_{self.table_name}")
        
        return TableSchema(
            table_name=self.table_name,
            columns=columns,
            primary_key_columns=[],
            foreign_keys=[],
            indexes=[],
            description=table_description,
            row_count=row_count,
        )
    
    def extract_ddl_document(self) -> Dict[str, Any]:
        """Extract DDL document for the table."""
        schema = self.extract_table_schema()
        return schema.to_vector_document(DatabaseDialect.DUCKDB)
    
    def close(self):
        """Close DuckDB connection."""
        if self.conn:
            self.conn.close()


def enrich_data_dictionary(
    raw_dictionary: Dict[str, Any],
    common_abbreviations: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Enrich a data dictionary with expanded abbreviations and inferred descriptions.
    
    Args:
        raw_dictionary: Original data dictionary from user input
        common_abbreviations: Common abbreviation mappings
    
    Returns:
        Enriched data dictionary with expanded descriptions
    """
    default_abbreviations = {
        "id": "identifier",
        "qty": "quantity",
        "amt": "amount",
        "dt": "date",
        "tm": "time",
        "ts": "timestamp",
        "num": "number",
        "cnt": "count",
        "desc": "description",
        "addr": "address",
        "tel": "telephone",
        "msg": "message",
        "txt": "text",
        "val": "value",
        "src": "source",
        "dst": "destination",
        "ref": "reference",
        "stat": "status",
        "cat": "category",
        "grp": "group",
        "org": "organization",
        "emp": "employee",
        "cust": "customer",
        "prod": "product",
        "inv": "invoice",
        "txn": "transaction",
        "acct": "account",
        "bal": "balance",
        "pmt": "payment",
        "shp": "shipping",
        "dlv": "delivery",
    }
    
    abbreviations = {**default_abbreviations, **(common_abbreviations or {})}
    enriched = dict(raw_dictionary)
    
    for key, value in list(enriched.items()):
        if value is None or value == "":
            name_parts = re.split(r'[_\s]', key.lower())
            expanded_parts = [abbreviations.get(part, part) for part in name_parts]
            inferred_desc = " ".join(expanded_parts).title()
            enriched[key] = inferred_desc
    
    return enriched


def create_business_rules_from_status_codes(
    status_mappings: Dict[str, Dict[int, str]],
) -> Dict[str, str]:
    """
    Create business rules dictionary from status code mappings.
    
    Args:
        status_mappings: Dict mapping table.column to {code: description}
    
    Returns:
        Business rules dict for DDLExtractor
    """
    rules = {}
    for column_path, codes in status_mappings.items():
        descriptions = [f"{code} = {desc}" for code, desc in sorted(codes.items())]
        rules[column_path] = "; ".join(descriptions)
    return rules
