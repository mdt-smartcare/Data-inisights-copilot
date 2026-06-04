"""
CTE Rewriter — Deterministic SQL transformation layer for FHIR healthcare data.

Inspired by  Rust engine, this module transforms semantic SQL
into executable database SQL by:
1. Parsing user SQL (sqlglot)
2. Identifying referenced semantic models (patient_tracker, encounter, etc.)
3. Injecting CTEs with default filters and joins
4. Transpiling to target dialect (PostgreSQL, DuckDB, etc.)

This is the key to accuracy: instead of hoping the LLM writes correct SQL,
the LLM writes simple semantic SQL, and we deterministically expand it.

Example (FHIR Healthcare):
    User writes:   SELECT COUNT(*) FROM patient_tracker WHERE enrollment_status = 'active'
    We expand to:  WITH "patient_tracker" AS (
                     SELECT * FROM public.patient_tracker
                     WHERE is_deleted = false AND is_active = true
                   )
                   SELECT COUNT(*) FROM patient_tracker WHERE enrollment_status = 'active'

Performance: ~5-20ms for parsing + transformation (vs 1-3s for LLM)
"""
import re
from typing import Optional, List, Dict, Set, Tuple, Any
from enum import Enum
from dataclasses import dataclass

from app.core.utils.logging import get_logger
from .schema_manifest import SchemaManifest, ManifestModel

logger = get_logger(__name__)

# Try to import sqlglot for SQL parsing
try:
    import sqlglot
    from sqlglot import exp, parse_one, transpile
    from sqlglot.errors import ParseError
    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False
    logger.warning("sqlglot not installed. CTE rewriting will use regex fallback.")


class SQLDialect(str, Enum):
    """Supported SQL dialects."""
    POSTGRES = "postgres"
    DUCKDB = "duckdb"
    MYSQL = "mysql"
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"
    SQLITE = "sqlite"
    TRINO = "trino"


@dataclass
class RewriteResult:
    """Result of SQL rewriting."""
    original_sql: str
    rewritten_sql: str
    referenced_tables: List[str]
    injected_ctes: Dict[str, str]  # model_name → CTE SQL
    applied_filters: Dict[str, List[str]]  # table → [filters]
    dialect: SQLDialect
    parse_time_ms: float
    rewrite_time_ms: float
    is_valid: bool
    errors: List[str]


class CTERewriter:
    """
    Deterministic SQL transformation engine.
    
    Like  Rust engine, this transforms semantic SQL to executable SQL
    by injecting CTEs for semantic models.
    
    Usage:
        rewriter = CTERewriter(manifest, dialect=SQLDialect.POSTGRES)
        result = rewriter.rewrite("SELECT * FROM patients")
        
        if result.is_valid:
            execute(result.rewritten_sql)
    """
    
    # SQL patterns that should be blocked
    DANGEROUS_PATTERNS = [
        r'\bDROP\s+',
        r'\bDELETE\s+FROM\b',
        r'\bTRUNCATE\s+',
        r'\bALTER\s+TABLE\b',
        r'\bCREATE\s+',
        r'\bINSERT\s+INTO\b',
        r'\bUPDATE\s+\w+\s+SET\b',
        r'\bGRANT\s+',
        r'\bREVOKE\s+',
        r';\s*--',  # SQL injection attempt
    ]
    
    def __init__(
        self,
        manifest: SchemaManifest,
        dialect: SQLDialect = SQLDialect.POSTGRES,
        strict_mode: bool = True
    ):
        """
        Initialize CTERewriter.
        
        Args:
            manifest: Pre-compiled schema manifest
            dialect: Target SQL dialect for transpilation
            strict_mode: If True, reject queries with undefined tables
        """
        self.manifest = manifest
        self.dialect = dialect
        self.strict_mode = strict_mode
        
        # Pre-compile dangerous patterns
        self._dangerous_regex = re.compile(
            '|'.join(self.DANGEROUS_PATTERNS),
            re.IGNORECASE
        )
    
    def rewrite(
        self,
        sql: str,
        skip_filters: Optional[List[str]] = None,
        extra_filters: Optional[Dict[str, List[str]]] = None
    ) -> RewriteResult:
        """
        Rewrite semantic SQL to executable SQL.
        
        Args:
            sql: User's SQL query (may reference semantic models)
            skip_filters: Table names to skip default filters for
            extra_filters: Additional filters to apply per table
            
        Returns:
            RewriteResult with rewritten SQL and metadata
        """
        import time
        start = time.time()
        
        errors = []
        
        # Step 1: Validate SQL safety
        safety_errors = self._validate_safety(sql)
        if safety_errors:
            return RewriteResult(
                original_sql=sql,
                rewritten_sql="",
                referenced_tables=[],
                injected_ctes={},
                applied_filters={},
                dialect=self.dialect,
                parse_time_ms=0,
                rewrite_time_ms=0,
                is_valid=False,
                errors=safety_errors
            )
        
        parse_start = time.time()
        
        # Step 2: Extract referenced tables
        if SQLGLOT_AVAILABLE:
            referenced_tables, parse_errors = self._extract_tables_sqlglot(sql)
        else:
            referenced_tables, parse_errors = self._extract_tables_regex(sql)
        
        parse_time_ms = (time.time() - parse_start) * 1000
        errors.extend(parse_errors)
        
        # Step 3: Validate tables against manifest (strict mode)
        if self.strict_mode:
            for table in referenced_tables:
                if not self.manifest.get_model(table):
                    errors.append(f"Unknown table/model: {table}")
        
        if errors:
            return RewriteResult(
                original_sql=sql,
                rewritten_sql=sql,
                referenced_tables=referenced_tables,
                injected_ctes={},
                applied_filters={},
                dialect=self.dialect,
                parse_time_ms=parse_time_ms,
                rewrite_time_ms=0,
                is_valid=False,
                errors=errors
            )
        
        rewrite_start = time.time()
        
        # Step 4: Build CTEs for each referenced model
        ctes, applied_filters = self._build_ctes(
            referenced_tables,
            skip_filters=skip_filters or [],
            extra_filters=extra_filters or {}
        )
        
        # Step 5: Inject CTEs and transpile
        rewritten_sql = self._inject_ctes_and_transpile(sql, ctes)
        
        rewrite_time_ms = (time.time() - rewrite_start) * 1000
        total_time_ms = (time.time() - start) * 1000
        
        logger.info(
            f"SQL rewritten in {total_time_ms:.1f}ms "
            f"(parse={parse_time_ms:.1f}ms, rewrite={rewrite_time_ms:.1f}ms): "
            f"{len(referenced_tables)} tables, {len(ctes)} CTEs"
        )
        
        return RewriteResult(
            original_sql=sql,
            rewritten_sql=rewritten_sql,
            referenced_tables=referenced_tables,
            injected_ctes=ctes,
            applied_filters=applied_filters,
            dialect=self.dialect,
            parse_time_ms=parse_time_ms,
            rewrite_time_ms=rewrite_time_ms,
            is_valid=True,
            errors=[]
        )
    
    def _validate_safety(self, sql: str) -> List[str]:
        """Check SQL for dangerous patterns."""
        errors = []
        
        match = self._dangerous_regex.search(sql)
        if match:
            errors.append(f"Dangerous SQL pattern detected: {match.group()}")
        
        # Check manifest denied patterns
        for pattern in self.manifest.denied_patterns:
            if pattern.lower() in sql.lower():
                errors.append(f"Denied pattern: {pattern}")
        
        return errors
    
    def _extract_tables_sqlglot(self, sql: str) -> Tuple[List[str], List[str]]:
        """Extract referenced tables using sqlglot."""
        errors = []
        tables = set()
        
        try:
            # Map our dialect to sqlglot dialect
            dialect_map = {
                SQLDialect.POSTGRES: "postgres",
                SQLDialect.DUCKDB: "duckdb",
                SQLDialect.MYSQL: "mysql",
                SQLDialect.BIGQUERY: "bigquery",
                SQLDialect.SNOWFLAKE: "snowflake",
                SQLDialect.SQLITE: "sqlite"
            }
            dialect = dialect_map.get(self.dialect, "postgres")
            
            # Parse SQL
            parsed = parse_one(sql, dialect=dialect)
            
            # Find all table references
            for table in parsed.find_all(exp.Table):
                table_name = table.name
                if table_name:
                    # Remove quotes if present
                    table_name = table_name.strip('"').strip("'")
                    tables.add(table_name)
            
        except ParseError as e:
            errors.append(f"SQL parse error: {e}")
        except Exception as e:
            errors.append(f"Unexpected parse error: {e}")
            # Fall back to regex
            tables, regex_errors = self._extract_tables_regex(sql)
            errors.extend(regex_errors)
        
        return list(tables), errors
    
    def _extract_tables_regex(self, sql: str) -> Tuple[List[str], List[str]]:
        """Fallback table extraction using regex."""
        tables = set()
        
        # Pattern to match FROM/JOIN table references
        patterns = [
            r'\bFROM\s+(["\']?\w+["\']?)',
            r'\bJOIN\s+(["\']?\w+["\']?)',
            r'\bINTO\s+(["\']?\w+["\']?)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            for match in matches:
                # Clean up quotes
                table_name = match.strip('"').strip("'")
                # Skip SQL keywords that might match
                if table_name.upper() not in {'SELECT', 'WHERE', 'AND', 'OR', 'ON'}:
                    tables.add(table_name)
        
        return list(tables), []
    
    def _build_ctes(
        self,
        tables: List[str],
        skip_filters: List[str],
        extra_filters: Dict[str, List[str]]
    ) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Build CTE definitions for each table."""
        ctes = {}
        applied_filters = {}
        
        for table_name in tables:
            model = self.manifest.get_model(table_name)
            if not model:
                continue
            
            # Determine filters to apply
            filters = []
            if table_name not in skip_filters:
                filters.extend(model.default_filters)
            if table_name in extra_filters:
                filters.extend(extra_filters[table_name])
            
            applied_filters[table_name] = filters
            
            # Build CTE SQL
            cte_sql = self._build_model_cte(model, filters)
            ctes[table_name] = cte_sql
        
        return ctes, applied_filters
    
    def _build_model_cte(self, model: ManifestModel, filters: List[str]) -> str:
        """Build CTE SQL for a model with filters."""
        # Select all columns
        columns = [col.name for col in model.columns]
        
        # Add calculated fields
        calc_expressions = []
        for calc_name, calc_expr in model.calculated_fields.items():
            calc_expressions.append(f"({calc_expr}) AS {calc_name}")
        
        # Build SELECT
        select_parts = columns + calc_expressions
        select_clause = ", ".join(select_parts) if select_parts else "*"
        
        # Build FROM with proper quoting
        if self.dialect == SQLDialect.POSTGRES:
            from_clause = f'"{model.schema_name}"."{model.table_reference}"'
        elif self.dialect == SQLDialect.MYSQL:
            from_clause = f"`{model.schema_name}`.`{model.table_reference}`"
        else:
            from_clause = f"{model.schema_name}.{model.table_reference}"
        
        sql = f"SELECT {select_clause} FROM {from_clause}"
        
        # Add WHERE clause
        if filters:
            where_clause = " AND ".join(filters)
            sql += f" WHERE {where_clause}"
        
        return sql
    
    def _inject_ctes_and_transpile(
        self,
        sql: str,
        ctes: Dict[str, str]
    ) -> str:
        """Inject CTEs into SQL and transpile to target dialect."""
        if not ctes:
            return sql
        
        # Build CTE block
        cte_parts = []
        for name, cte_sql in ctes.items():
            # Quote the CTE name properly
            if self.dialect == SQLDialect.POSTGRES:
                quoted_name = f'"{name}"'
            elif self.dialect == SQLDialect.MYSQL:
                quoted_name = f"`{name}`"
            else:
                quoted_name = name
            cte_parts.append(f"{quoted_name} AS (\n  {cte_sql}\n)")
        
        cte_block = "WITH " + ",\n".join(cte_parts)
        
        # Check if SQL already has WITH clause
        sql_stripped = sql.strip()
        if sql_stripped.upper().startswith("WITH "):
            # Merge CTE blocks
            # Find the end of existing WITH clause
            match = re.match(r'WITH\s+(.+?)\s+SELECT', sql_stripped, re.IGNORECASE | re.DOTALL)
            if match:
                existing_ctes = match.group(1)
                # Insert our CTEs before existing ones
                cte_block = "WITH " + ",\n".join(cte_parts) + ",\n" + existing_ctes
                sql = re.sub(r'WITH\s+.+?\s+SELECT', cte_block + "\nSELECT", sql_stripped, 1, re.IGNORECASE | re.DOTALL)
            else:
                sql = cte_block + "\n" + sql
        else:
            sql = cte_block + "\n" + sql
        
        # Transpile to target dialect if sqlglot available
        if SQLGLOT_AVAILABLE:
            try:
                dialect_map = {
                    SQLDialect.POSTGRES: "postgres",
                    SQLDialect.DUCKDB: "duckdb",
                    SQLDialect.MYSQL: "mysql",
                    SQLDialect.BIGQUERY: "bigquery",
                    SQLDialect.SNOWFLAKE: "snowflake",
                    SQLDialect.SQLITE: "sqlite"
                }
                target = dialect_map.get(self.dialect, "postgres")
                
                # Transpile (normalize quoting, function names, etc.)
                transpiled = transpile(sql, read=target, write=target, pretty=True)
                if transpiled:
                    sql = transpiled[0]
            except Exception as e:
                logger.warning(f"Transpilation failed, using original: {e}")
        
        return sql
    
    def dry_plan(self, sql: str) -> str:
        """
        Return the rewritten SQL without executing.
        
        Useful for debugging and showing users what will run.
        """
        result = self.rewrite(sql)
        if result.is_valid:
            return result.rewritten_sql
        else:
            raise ValueError(f"SQL rewrite failed: {result.errors}")
    
    def validate(self, sql: str) -> Tuple[bool, List[str]]:
        """
        Validate SQL without rewriting.
        
        Returns (is_valid, errors).
        """
        result = self.rewrite(sql)
        return result.is_valid, result.errors


class QueryExpander:
    """
    Expands semantic queries to full SQL.
    
    This is a higher-level API that combines:
    1. Schema linking (which tables to use)
    2. CTE rewriting (inject filters/joins)
    3. Dialect transpilation
    
    Usage:
        expander = QueryExpander(manifest, schema_linker)
        full_sql = expander.expand("SELECT * FROM patients", question="How many active patients?")
    """
    
    def __init__(
        self,
        manifest: SchemaManifest,
        rewriter: Optional[CTERewriter] = None,
        dialect: SQLDialect = SQLDialect.POSTGRES
    ):
        self.manifest = manifest
        self.rewriter = rewriter or CTERewriter(manifest, dialect)
        self.dialect = dialect
    
    def expand(
        self,
        sql: str,
        question: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> RewriteResult:
        """
        Expand semantic SQL to executable SQL.
        
        Args:
            sql: Semantic SQL from LLM
            question: Original user question (for context)
            context: Additional context (user_id, tenant_id, etc.)
            
        Returns:
            RewriteResult with expanded SQL
        """
        # Apply context-based filters if provided
        extra_filters = {}
        if context:
            # Example: multi-tenant filter
            if "tenant_id" in context:
                for model_name in self.manifest.models:
                    model = self.manifest.models[model_name]
                    # Check if model has tenant_id column
                    if any(col.name == "tenant_id" for col in model.columns):
                        if model_name not in extra_filters:
                            extra_filters[model_name] = []
                        extra_filters[model_name].append(f"tenant_id = {context['tenant_id']}")
        
        return self.rewriter.rewrite(sql, extra_filters=extra_filters)
    
    def expand_with_joins(
        self,
        sql: str,
        tables: List[str]
    ) -> RewriteResult:
        """
        Expand SQL and automatically add necessary joins.
        
        If SQL references multiple tables but no explicit joins,
        inject joins from manifest relationships.
        """
        # First, do basic rewrite
        result = self.rewriter.rewrite(sql)
        
        if not result.is_valid or len(tables) <= 1:
            return result
        
        # Check if joins are already present
        if "JOIN" in sql.upper():
            return result
        
        # Build join chain from manifest
        join_clauses = []
        for i, t1 in enumerate(tables[:-1]):
            t2 = tables[i + 1]
            path = self.manifest.get_join_path(t1, t2)
            if path:
                for rel in path:
                    join_clauses.append(rel.join_clause)
        
        if join_clauses:
            # Inject joins into SQL
            # Find FROM clause and append joins
            modified_sql = result.rewritten_sql
            for join_clause in join_clauses:
                # Simple injection after FROM table
                # In practice, you'd want smarter insertion
                if "WHERE" in modified_sql.upper():
                    insert_point = modified_sql.upper().index("WHERE")
                    modified_sql = (
                        modified_sql[:insert_point] +
                        join_clause + " " +
                        modified_sql[insert_point:]
                    )
                else:
                    modified_sql += " " + join_clause
            
            result.rewritten_sql = modified_sql
        
        return result
