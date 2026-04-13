"""
DDL Extraction Utility for Structural Schema Indexing.

Phase 1: Ingestion & Knowledge Base Redesign
============================================
Replaces naive token chunking with table-level structural indexing.
Token chunks destroy relational boundaries; the LLM needs complete DDL statements.

Features:
- Extract exact CREATE TABLE statements including PKs, FKs, and column data types
- Enrich schemas semantically with natural language descriptions
- Prepare enriched DDL for table-level vectorization

Usage:
    from app.core.utils.ddl_extractor import DDLExtractor
    
    extractor = DDLExtractor(db_url="postgresql://user:pass@host:5432/db")
    ddl_documents = extractor.extract_all_tables()
    
    # Each document contains:
    # - Complete DDL statement
    # - Semantic metadata (table name, FK dependencies, column descriptions)
    # - Business logic annotations from data dictionary
"""
import re
import json
import hashlib
from typing import Dict, List, Any, Optional
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
    description: Optional[str] = None  # Natural language description
    business_logic: Optional[str] = None  # e.g., "status_code = 4 means Completed"
    
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
    description: Optional[str] = None  # Table-level description
    row_count: Optional[int] = None
    
    def get_foreign_key_dependencies(self) -> List[str]:
        """Get list of tables this table depends on via foreign keys."""
        return list(set(fk.get("referred_table", "") for fk in self.foreign_keys if fk.get("referred_table")))
    
    def generate_ddl(self, dialect: DatabaseDialect = DatabaseDialect.POSTGRESQL) -> str:
        """Generate CREATE TABLE statement."""
        lines = [f'CREATE TABLE "{self.table_name}" (']
        
        # Column definitions
        col_lines = []
        for col in self.columns:
            col_lines.append(f"    {col.to_ddl_line(dialect)}")
        
        # Primary key constraint
        if self.primary_key_columns:
            pk_cols = ", ".join(f'"{c}"' for c in self.primary_key_columns)
            col_lines.append(f"    PRIMARY KEY ({pk_cols})")
        
        # Foreign key constraints
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
        """
        Generate enriched DDL with semantic annotations as comments.
        
        This format preserves the exact DDL structure while adding
        natural language context that helps the LLM understand the schema.
        """
        lines = []
        
        # Table header comment with description
        lines.append(f"-- ============================================")
        lines.append(f"-- Table: {self.table_name}")
        if self.description:
            lines.append(f"-- Description: {self.description}")
        if self.row_count is not None:
            lines.append(f"-- Row Count: {self.row_count:,}")
        
        # Foreign key dependencies
        deps = self.get_foreign_key_dependencies()
        if deps:
            lines.append(f"-- Dependencies: {', '.join(deps)}")
        
        lines.append(f"-- ============================================")
        lines.append("")
        
        # DDL statement
        lines.append(f'CREATE TABLE "{self.table_name}" (')
        
        # Column definitions with inline comments
        col_lines = []
        for col in self.columns:
            col_ddl = f"    {col.to_ddl_line(dialect)}"
            
            # Add semantic comment
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
        
        # Primary key constraint
        if self.primary_key_columns:
            pk_cols = ", ".join(f'"{c}"' for c in self.primary_key_columns)
            col_lines.append(f"    PRIMARY KEY ({pk_cols})")
        
        # Foreign key constraints with descriptive comments
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
        """
        Convert table schema to a vector store document.
        
        Returns a document dict with:
        - id: Unique identifier for the table
        - content: Enriched DDL statement
        - metadata: Structured metadata for filtering and retrieval
        """
        enriched_ddl = self.generate_enriched_ddl(dialect)
        
        # Generate stable document ID
        doc_id = hashlib.sha256(f"ddl_{self.table_name}".encode()).hexdigest()[:16]
        
        # Build column summaries for metadata
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
        
        metadata = {
            "doc_type": "ddl_schema",
            "table_name": self.table_name,
            "column_count": len(self.columns),
            "primary_keys": self.primary_key_columns,
            "foreign_key_dependencies": self.get_foreign_key_dependencies(),
            "has_foreign_keys": len(self.foreign_keys) > 0,
            "columns": json.dumps(column_summaries),  # JSON string for vector store compatibility
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
    ):
        """
        Initialize DDL extractor.
        
        Args:
            db_url: Database connection URL (postgresql://user:pass@host:5432/db)
            engine: Existing SQLAlchemy engine (alternative to db_url)
            data_dictionary: Dict mapping column names to descriptions
                             e.g., {"patient_id": "Unique patient identifier"}
            business_rules: Dict mapping table.column to business logic descriptions
                            e.g., {"orders.status_code": "4 = Completed, 3 = Shipped"}
        """
        if engine:
            self.engine = engine
        elif db_url:
            # Normalize common URL typos
            db_url = self._normalize_db_url(db_url)
            self.engine = create_engine(db_url, pool_pre_ping=True, pool_size=1)
        else:
            raise ValueError("Either db_url or engine must be provided")
        
        self.data_dictionary = data_dictionary or {}
        self.business_rules = business_rules or {}
        self.dialect = self._detect_dialect()
        self.inspector = inspect(self.engine)
    
    def _normalize_db_url(self, url: str) -> str:
        """Normalize common typos in database URLs."""
        url = url.replace("postgressql://", "postgresql://")
        url = url.replace("postgress://", "postgresql://")
        url = url.replace("postgres://", "postgresql://")
        return url
    
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
        # Try table.column first
        full_key = f"{table_name}.{column_name}"
        if full_key in self.data_dictionary:
            return self.data_dictionary[full_key]
        
        # Try just column name
        if column_name in self.data_dictionary:
            return self.data_dictionary[column_name]
        
        # Try to infer from column name patterns
        return self._infer_column_description(column_name)
    
    def _infer_column_description(self, column_name: str) -> Optional[str]:
        """Infer description from common column naming patterns."""
        name_lower = column_name.lower()
        
        # Common patterns
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
        try:
            with self.engine.connect() as conn:
                if self.dialect == DatabaseDialect.POSTGRESQL:
                    # Use pg_class for fast approximate count
                    result = conn.execute(text(f"""
                        SELECT reltuples::bigint AS estimate
                        FROM pg_class
                        WHERE relname = :table_name
                    """), {"table_name": table_name})
                    row = result.fetchone()
                    if row and row[0] > 0:
                        return int(row[0])
                
                # Fallback to exact count (slower for large tables)
                result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                row = result.fetchone()
                return int(row[0]) if row else None
        except Exception as e:
            logger.warning(f"Failed to get row count for {table_name}: {e}")
            return None
    
    def extract_table_schema(self, table_name: str, include_row_count: bool = True) -> TableSchema:
        """
        Extract complete schema for a single table.
        
        Args:
            table_name: Name of the table to extract
            include_row_count: Whether to query row count (can be slow for large tables)
        
        Returns:
            TableSchema with columns, PKs, FKs, and semantic metadata
        """
        logger.info(f"Extracting schema for table: {table_name}")
        
        # Get primary key columns
        pk_constraint = self.inspector.get_pk_constraint(table_name)
        pk_columns = set(pk_constraint.get("constrained_columns", []) if pk_constraint else [])
        
        # Get foreign keys
        foreign_keys = self.inspector.get_foreign_keys(table_name)
        
        # Build FK column lookup
        fk_column_info = {}
        for fk in foreign_keys:
            ref_table = fk.get("referred_table")
            ref_columns = fk.get("referred_columns", [])
            constrained_columns = fk.get("constrained_columns", [])
            
            for i, col in enumerate(constrained_columns):
                fk_column_info[col] = {
                    "table": ref_table,
                    "column": ref_columns[i] if i < len(ref_columns) else None,
                }
        
        # Get columns
        columns = []
        for col in self.inspector.get_columns(table_name):
            col_name = col["name"]
            
            # Check if this is a FK column
            fk_info = fk_column_info.get(col_name, {})
            
            column_info = ColumnInfo(
                name=col_name,
                data_type=str(col["type"]),
                is_nullable=col.get("nullable", True),
                is_primary_key=col_name in pk_columns,
                is_foreign_key=col_name in fk_column_info,
                foreign_key_table=fk_info.get("table"),
                foreign_key_column=fk_info.get("column"),
                default_value=str(col.get("default")) if col.get("default") else None,
                description=self._get_column_description(table_name, col_name),
                business_logic=self._get_business_logic(table_name, col_name),
            )
            columns.append(column_info)
        
        # Get indexes
        indexes = []
        try:
            for idx in self.inspector.get_indexes(table_name):
                indexes.append({
                    "name": idx.get("name"),
                    "columns": idx.get("column_names", []),
                    "unique": idx.get("unique", False),
                })
        except Exception as e:
            logger.warning(f"Failed to get indexes for {table_name}: {e}")
        
        # Get row count
        row_count = None
        if include_row_count:
            row_count = self._get_row_count(table_name)
        
        # Get table description from data dictionary
        table_description = self.data_dictionary.get(f"_table_{table_name}")
        
        return TableSchema(
            table_name=table_name,
            columns=columns,
            primary_key_columns=list(pk_columns),
            foreign_keys=foreign_keys,
            indexes=indexes,
            description=table_description,
            row_count=row_count,
        )
    
    def extract_all_tables(
        self,
        include_row_counts: bool = True,
        tables_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extract DDL documents for all tables in the database.
        
        Args:
            include_row_counts: Whether to include row counts in metadata
            tables_filter: Optional list of table names to include (None = all tables)
        
        Returns:
            List of vector documents ready for embedding
        """
        table_names = self.inspector.get_table_names()
        
        if tables_filter:
            table_names = [t for t in table_names if t in tables_filter]
        
        logger.info(f"Extracting DDL for {len(table_names)} tables")
        
        documents = []
        for table_name in table_names:
            try:
                schema = self.extract_table_schema(table_name, include_row_count=include_row_counts)
                doc = schema.to_vector_document(self.dialect)
                documents.append(doc)
                logger.info(f"Extracted DDL for {table_name}: {len(schema.columns)} columns")
            except Exception as e:
                logger.error(f"Failed to extract DDL for {table_name}: {e}")
        
        return documents
    
    def extract_relationships_document(self) -> Dict[str, Any]:
        """
        Generate a document describing all table relationships.
        
        This provides the LLM with a high-level view of how tables connect,
        which is crucial for generating correct JOINs.
        """
        table_names = self.inspector.get_table_names()
        
        relationships = []
        for table_name in table_names:
            try:
                foreign_keys = self.inspector.get_foreign_keys(table_name)
                for fk in foreign_keys:
                    ref_table = fk.get("referred_table")
                    if ref_table:
                        relationships.append({
                            "from_table": table_name,
                            "from_columns": fk.get("constrained_columns", []),
                            "to_table": ref_table,
                            "to_columns": fk.get("referred_columns", []),
                        })
            except Exception as e:
                logger.warning(f"Failed to get FKs for {table_name}: {e}")
        
        # Generate human-readable relationship descriptions
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
        self.conn = duckdb.connect(duckdb_path, read_only=True)
    
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
        
        # Get column info
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
                is_primary_key=False,  # DuckDB tables from files typically don't have PKs
                is_foreign_key=False,
                description=self._get_column_description(col_name),
            )
            columns.append(column_info)
        
        # Get row count
        count_result = self.conn.execute(f'SELECT COUNT(*) FROM "{self.table_name}"').fetchone()
        row_count = count_result[0] if count_result else None
        
        # Get table description
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
                              e.g., {"qty": "quantity", "amt": "amount"}
    
    Returns:
        Enriched data dictionary with expanded descriptions
    """
    # Default common abbreviations in technical/business contexts
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
    
    # Expand abbreviations in column names that don't have descriptions
    for key, value in list(enriched.items()):
        if value is None or value == "":
            # Try to infer description from column name
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
                         e.g., {"orders.status": {1: "Pending", 2: "Processing", 4: "Completed"}}
    
    Returns:
        Business rules dict for DDLExtractor
    """
    rules = {}
    for column_path, codes in status_mappings.items():
        descriptions = [f"{code} = {desc}" for code, desc in sorted(codes.items())]
        rules[column_path] = "; ".join(descriptions)
    return rules
