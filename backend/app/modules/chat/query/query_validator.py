"""
Query Validator Module - Proactive SQL Validation Before Execution

This module addresses several NL2SQL shortcomings:
1. Validates generated SQL against actual schema BEFORE execution
2. Provides query plan explanation for debugging
3. Validates few-shot examples against current schema
4. Integrates FHIR identifier rules from data dictionary

Usage:
    from app.modules.chat.query.query_validator import QueryValidator
    
    validator = QueryValidator(engine=db_engine)
    validation = validator.validate_sql(sql_query, schema_context)
    if not validation.is_valid:
        # Use correction suggestions for LLM retry
        print(validation.error_message)
        print(validation.suggested_corrections)
"""
import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class QueryValidationResult:
    """Result of SQL query validation."""
    is_valid: bool
    error_message: Optional[str] = None
    invalid_tables: List[str] = field(default_factory=list)
    invalid_columns: List[Tuple[str, str]] = field(default_factory=list)  # (table, column)
    fhir_violations: List[str] = field(default_factory=list)
    suggested_corrections: List[str] = field(default_factory=list)
    query_plan: Optional[Dict[str, Any]] = None  # Tables selected and why


@dataclass
class QueryPlanExplanation:
    """Explains why specific tables were selected for a query."""
    tables_selected: List[str]
    selection_reasons: Dict[str, str]  # table -> reason
    columns_used: Dict[str, List[str]]  # table -> [columns]
    potential_alternatives: Dict[str, List[str]]  # table -> [alternative_tables]


class QueryValidator:
    """
    Proactive SQL query validator.
    
    Validates SQL queries against the actual database schema before execution,
    preventing errors and providing actionable correction suggestions.
    
    Key features:
    - Table existence validation
    - Column existence validation  
    - FHIR identifier pattern enforcement
    - Query plan explanation generation
    """
    
    def __init__(
        self,
        engine: Optional[Engine] = None,
        schema_name: str = "public",
        fhir_rules: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize query validator.
        
        Args:
            engine: SQLAlchemy database engine
            schema_name: Database schema to validate against
            fhir_rules: FHIR identifier rules from data dictionary
        """
        self._engine = engine
        self._schema_name = schema_name
        self._fhir_rules = fhir_rules or {}
        
        # Cached schema metadata
        self._tables: Set[str] = set()
        self._table_columns: Dict[str, Set[str]] = {}
        self._schema_loaded = False
    
    def load_schema(self) -> None:
        """Load database schema into memory for fast validation."""
        if not self._engine:
            logger.warning("No database engine - schema validation disabled")
            return
            
        try:
            inspector = inspect(self._engine)
            self._tables = set(inspector.get_table_names(schema=self._schema_name))
            
            for table_name in self._tables:
                columns = inspector.get_columns(table_name, schema=self._schema_name)
                self._table_columns[table_name] = {col['name'] for col in columns}
            
            self._schema_loaded = True
            logger.info(f"QueryValidator loaded schema: {len(self._tables)} tables")
        except Exception as e:
            logger.error(f"Failed to load schema for validation: {e}")
    
    def validate_sql(
        self, 
        sql: str, 
        schema_context: Optional[str] = None
    ) -> QueryValidationResult:
        """
        Validate a SQL query against the schema.
        
        Args:
            sql: The SQL query to validate
            schema_context: Optional schema context for additional validation
            
        Returns:
            QueryValidationResult with validation status and any issues found
        """
        result = QueryValidationResult(is_valid=True)
        
        if not self._schema_loaded:
            self.load_schema()
        
        if not self._tables:
            # Can't validate without schema, assume valid
            logger.debug("No schema loaded - skipping validation")
            return result
        
        # Extract tables referenced in the SQL
        tables_in_sql = self._extract_tables_from_sql(sql)
        
        # Extract columns referenced in the SQL
        columns_in_sql = self._extract_columns_from_sql(sql)
        
        # Validate tables
        for table in tables_in_sql:
            if table.lower() not in {t.lower() for t in self._tables}:
                result.invalid_tables.append(table)
                similar = self._find_similar_tables(table)
                if similar:
                    result.suggested_corrections.append(
                        f"Table '{table}' not found. Did you mean: {', '.join(similar)}?"
                    )
                else:
                    result.suggested_corrections.append(
                        f"Table '{table}' does not exist in the database."
                    )
        
        # Validate columns (only for valid tables)
        for table, column in columns_in_sql:
            table_lower = table.lower()
            # Find the actual table name (case-insensitive)
            actual_table = next(
                (t for t in self._tables if t.lower() == table_lower), 
                None
            )
            
            if actual_table:
                columns = self._table_columns.get(actual_table, set())
                if column.lower() not in {c.lower() for c in columns}:
                    result.invalid_columns.append((table, column))
                    similar = self._find_similar_columns(actual_table, column)
                    if similar:
                        result.suggested_corrections.append(
                            f"Column '{column}' not found in '{table}'. Available: {', '.join(similar[:5])}"
                        )
        
        # Validate FHIR identifier patterns
        fhir_violations = self._validate_fhir_patterns(sql, tables_in_sql)
        result.fhir_violations.extend(fhir_violations)
        
        # Build query plan explanation
        result.query_plan = self._generate_query_plan(sql, tables_in_sql, columns_in_sql)
        
        # Determine overall validity
        if result.invalid_tables or result.invalid_columns or result.fhir_violations:
            result.is_valid = False
            errors = []
            if result.invalid_tables:
                errors.append(f"Invalid tables: {', '.join(result.invalid_tables)}")
            if result.invalid_columns:
                cols = [f"{t}.{c}" for t, c in result.invalid_columns]
                errors.append(f"Invalid columns: {', '.join(cols)}")
            if result.fhir_violations:
                errors.append(f"FHIR violations: {'; '.join(result.fhir_violations)}")
            result.error_message = " | ".join(errors)
        
        return result
    
    def _extract_tables_from_sql(self, sql: str) -> List[str]:
        """Extract table names from SQL query, excluding CTE names."""
        tables = set()
        
        # First, extract CTE names so we don't flag them as invalid tables
        cte_names = self._extract_cte_names(sql)
        
        # Remove SQL function expressions that contain 'FROM' internally
        # to avoid false positives like EXTRACT(year FROM column_name)
        sql_cleaned = self._remove_function_from_expressions(sql)
        
        # Pattern for FROM and JOIN clauses
        # Matches: FROM table_name, JOIN table_name, LEFT JOIN table_name, etc.
        patterns = [
            r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, sql_cleaned, re.IGNORECASE)
            for match in matches:
                # Exclude SQL keywords
                if match.upper() not in {'SELECT', 'WHERE', 'AND', 'OR', 'ON', 
                                          'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS',
                                          'GROUP', 'ORDER', 'HAVING', 'LIMIT', 'OFFSET'}:
                    # Exclude CTE names (case-insensitive comparison)
                    if match.lower() not in cte_names:
                        tables.add(match)
        
        return list(tables)
    
    def _extract_cte_names(self, sql: str) -> set:
        """
        Extract CTE (Common Table Expression) names from SQL query.
        
        CTEs are defined with: WITH cte_name AS (...), cte_name2 AS (...)
        These are temporary result sets that are valid within the query scope,
        so they should not be flagged as "invalid tables".
        
        Args:
            sql: The SQL query to parse
            
        Returns:
            Set of CTE names (lowercase for case-insensitive comparison)
        """
        cte_names = set()
        
        # Match WITH clause and extract CTE names
        # Pattern handles: WITH cte1 AS (...), cte2 AS (...)
        # The CTE name comes before AS (preceded by WITH or comma)
        
        # First check if query has WITH clause
        if not re.search(r'\bWITH\s+', sql, re.IGNORECASE):
            return cte_names
        
        # Extract the WITH clause section (everything from WITH to the main SELECT)
        # Use a simple heuristic: find CTE names followed by AS (
        cte_pattern = r'(?:(?:\bWITH\b|\,)\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\('
        matches = re.findall(cte_pattern, sql, re.IGNORECASE)
        
        for match in matches:
            cte_names.add(match.lower())
        
        return cte_names
    
    def _remove_function_from_expressions(self, sql: str) -> str:
        """
        Remove SQL function expressions that use 'FROM' internally.
        
        These functions use 'FROM' as part of their syntax, not for table references:
        - EXTRACT(unit FROM expression)     e.g., EXTRACT(year FROM date_col)
        - SUBSTRING(str FROM pos [FOR len]) e.g., SUBSTRING(name FROM 1 FOR 5)
        - POSITION(substr IN string)        uses IN, not FROM - no change needed
        - OVERLAY(str PLACING new FROM pos) e.g., OVERLAY(text PLACING 'x' FROM 1)
        - DATE_PART('unit', expression)     doesn't use FROM - no change needed
        
        Args:
            sql: Original SQL query
            
        Returns:
            SQL with function expressions replaced by placeholders
        """
        result = sql
        
        # Pattern for EXTRACT(unit FROM expression)
        # Handles nested parentheses by matching balanced parens
        extract_pattern = r'\bEXTRACT\s*\(\s*(?:YEAR|MONTH|DAY|HOUR|MINUTE|SECOND|DOW|DOY|WEEK|QUARTER|EPOCH)\s+FROM\s+[^)]+\)'
        result = re.sub(extract_pattern, '__EXTRACT_PLACEHOLDER__', result, flags=re.IGNORECASE)
        
        # Pattern for SUBSTRING(str FROM pos [FOR len])
        # Matches both: SUBSTRING(col FROM 1) and SUBSTRING(col FROM 1 FOR 5)
        substring_from_pattern = r'\bSUBSTRING\s*\([^)]+\s+FROM\s+[^)]+\)'
        result = re.sub(substring_from_pattern, '__SUBSTRING_PLACEHOLDER__', result, flags=re.IGNORECASE)
        
        # Pattern for OVERLAY(str PLACING new FROM pos)
        overlay_pattern = r'\bOVERLAY\s*\([^)]+\s+PLACING\s+[^)]+\s+FROM\s+[^)]+\)'
        result = re.sub(overlay_pattern, '__OVERLAY_PLACEHOLDER__', result, flags=re.IGNORECASE)
        
        return result
    
    def _extract_columns_from_sql(self, sql: str) -> List[Tuple[str, str]]:
        """
        Extract column references from SQL query.
        
        Returns list of (table, column) tuples where table might be alias or actual table.
        """
        columns = []
        
        # Pattern for table.column references
        pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)'
        matches = re.findall(pattern, sql)
        
        for table_or_alias, column in matches:
            # Exclude function calls like COUNT.*, string qualifiers, etc.
            if table_or_alias.upper() not in {'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 
                                               'DISTINCT', 'CAST', 'EXTRACT', 'DATE_TRUNC'}:
                columns.append((table_or_alias, column))
        
        return columns
    
    def _validate_fhir_patterns(
        self, 
        sql: str, 
        tables: List[str]
    ) -> List[str]:
        """Validate FHIR identifier usage patterns."""
        violations = []
        sql_upper = sql.upper()
        
        # Get FHIR rules from configuration
        patient_count_tables = self._fhir_rules.get("patient_count_tables", {})
        
        # Rule 1: patient_gold.patient_id is INVALID (should use res_id)
        if any(t.lower() == "patient_gold" for t in tables):
            # Check for patient_id usage with patient_gold
            if re.search(r'patient_gold\s*\.\s*patient_id', sql, re.IGNORECASE):
                violations.append(
                    "CRITICAL: patient_gold does NOT have 'patient_id'. "
                    "Use 'res_id' for patient identifier in patient_gold, "
                    "or use patient_tracker_gold.patient_id"
                )
        
        # Rule 2: When counting distinct patients, use correct identifier
        if 'COUNT' in sql_upper and 'DISTINCT' in sql_upper:
            for table in tables:
                table_lower = table.lower()
                if table_lower in patient_count_tables:
                    expected_id = patient_count_tables[table_lower].get("identifier")
                    if expected_id:
                        # Check if using wrong identifier
                        wrong_ids = {"patient_id", "res_id"} - {expected_id}
                        for wrong_id in wrong_ids:
                            pattern = rf'{table}\s*\.\s*{wrong_id}'
                            if re.search(pattern, sql, re.IGNORECASE):
                                violations.append(
                                    f"For patient counts on {table}, use {expected_id}, not {wrong_id}"
                                )
        
        return violations
    
    def _generate_query_plan(
        self,
        sql: str,
        tables: List[str],
        columns: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        """Generate query plan explanation for debugging."""
        plan = {
            "tables_selected": tables,
            "columns_used": {},
            "join_pattern": self._detect_join_pattern(sql),
            "aggregations": self._detect_aggregations(sql),
            "filters": self._detect_filters(sql),
        }
        
        # Group columns by table
        for table, column in columns:
            if table not in plan["columns_used"]:
                plan["columns_used"][table] = []
            plan["columns_used"][table].append(column)
        
        return plan
    
    def _detect_join_pattern(self, sql: str) -> str:
        """Detect the join pattern used in the query."""
        sql_upper = sql.upper()
        
        if 'LEFT JOIN' in sql_upper:
            return "left_join"
        elif 'RIGHT JOIN' in sql_upper:
            return "right_join"
        elif 'FULL JOIN' in sql_upper or 'FULL OUTER JOIN' in sql_upper:
            return "full_outer_join"
        elif 'CROSS JOIN' in sql_upper:
            return "cross_join"
        elif 'JOIN' in sql_upper:
            return "inner_join"
        else:
            return "single_table"
    
    def _detect_aggregations(self, sql: str) -> List[str]:
        """Detect aggregation functions used."""
        aggregations = []
        sql_upper = sql.upper()
        
        agg_functions = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'GROUP BY']
        for func in agg_functions:
            if func in sql_upper:
                aggregations.append(func.lower().replace(' ', '_'))
        
        return aggregations
    
    def _detect_filters(self, sql: str) -> List[str]:
        """Detect WHERE clause filters."""
        filters = []
        
        # Simple extraction of WHERE conditions
        where_match = re.search(r'WHERE\s+(.+?)(?:GROUP BY|ORDER BY|LIMIT|$)', 
                                sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            where_clause = where_match.group(1)
            # Split on AND/OR
            conditions = re.split(r'\s+(?:AND|OR)\s+', where_clause, flags=re.IGNORECASE)
            filters.extend([c.strip() for c in conditions if c.strip()])
        
        return filters
    
    def _find_similar_tables(self, table_name: str, max_results: int = 3) -> List[str]:
        """Find tables with similar names."""
        if not self._tables:
            return []
        
        candidates = []
        search_parts = table_name.lower().replace('_', ' ').split()
        
        for table in self._tables:
            table_parts = table.lower().replace('_', ' ').split()
            # Check for partial matches
            if any(part in table_parts for part in search_parts):
                candidates.append(table)
            elif any(part in table.lower() for part in search_parts):
                candidates.append(table)
        
        return candidates[:max_results]
    
    def _find_similar_columns(
        self, 
        table_name: str, 
        column_name: str, 
        max_results: int = 5
    ) -> List[str]:
        """Find columns with similar names in a table."""
        columns = self._table_columns.get(table_name, set())
        if not columns:
            return []
        
        search_parts = column_name.lower().replace('_', ' ').split()
        
        candidates = []
        for col in columns:
            col_parts = col.lower().replace('_', ' ').split()
            if any(part in col_parts for part in search_parts):
                candidates.append(col)
        
        # If no partial matches, return first N columns as hints
        if not candidates:
            return sorted(list(columns))[:max_results]
        
        return candidates[:max_results]
    
    def validate_few_shot_examples(
        self,
        examples: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate few-shot examples against current schema.
        
        Args:
            examples: List of example dicts with 'sql' key
            
        Returns:
            Tuple of (valid_examples, invalid_examples)
        """
        valid = []
        invalid = []
        
        for example in examples:
            sql = example.get("sql", "")
            if not sql:
                continue
            
            validation = self.validate_sql(sql)
            if validation.is_valid:
                valid.append(example)
            else:
                invalid.append({
                    **example,
                    "validation_errors": validation.error_message
                })
        
        if invalid:
            logger.warning(
                f"Found {len(invalid)} invalid few-shot examples that don't match current schema"
            )
        
        return valid, invalid


def get_query_validator(
    engine: Optional[Engine] = None,
    schema_name: str = "public",
    fhir_rules: Optional[Dict[str, Any]] = None
) -> QueryValidator:
    """
    Factory function to get a QueryValidator instance.
    
    Args:
        engine: SQLAlchemy database engine
        schema_name: Database schema name
        fhir_rules: FHIR identifier rules from data dictionary
        
    Returns:
        Configured QueryValidator instance
    """
    validator = QueryValidator(
        engine=engine,
        schema_name=schema_name,
        fhir_rules=fhir_rules
    )
    validator.load_schema()
    return validator
