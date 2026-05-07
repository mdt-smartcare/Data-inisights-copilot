"""
Schema Validator for Data Dictionary Validation.

Validates data dictionary entries against the actual database schema to prevent
SQL generation errors caused by schema-dictionary drift.

Key Features:
- Validates table names exist in the database
- Validates column names exist in referenced tables
- Validates FHIR identifier patterns (res_id vs patient_id)
- Returns detailed validation errors for correction

Usage:
    from app.modules.agents.schema_validator import SchemaValidator
    
    validator = SchemaValidator(db_url="postgresql://user:pass@host:5432/db")
    errors = validator.validate_data_dictionary(data_dict_yaml)
    if errors:
        print("Validation errors:", errors)
"""
import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationError:
    """Represents a schema validation error."""
    error_type: str  # 'table_not_found', 'column_not_found', 'invalid_fhir_pattern'
    location: str  # Where in the data dictionary the error was found
    message: str  # Human-readable error message
    suggested_fix: Optional[str] = None  # Suggested correction


@dataclass
class ValidationResult:
    """Complete validation result."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    validated_tables: Set[str] = field(default_factory=set)
    validated_columns: Dict[str, Set[str]] = field(default_factory=dict)


# FHIR Identifier Rules - Critical for healthcare schemas
FHIR_IDENTIFIER_RULES = {
    "patient_gold": {
        "primary_identifier": "res_id",
        "has_patient_id": False,
        "description": "FHIR Patient resource - use res_id for patient counts"
    },
    "patient_tracker_gold": {
        "primary_identifier": "patient_id",
        "has_patient_id": True,
        "description": "Operational patient tracking - use patient_id for counts"
    }
}

# Tables that follow the clinical pattern (res_id as PK, patient_id as FK)
CLINICAL_TABLES_WITH_PATIENT_ID = {
    "bp_log_gold", "bp_log_latest_gold",
    "glucose_log_gold", "glucose_log_latest_gold",
    "appointment_gold", "careplan_gold", "condition_gold",
    "encounter_gold", "prescription_gold", "patient_visit_gold",
    "screening_log_gold", "medication_gold", "observation_gold"
}


class SchemaValidator:
    """
    Validates data dictionaries against actual database schema.
    
    This validator helps prevent NL2SQL errors by ensuring that:
    1. All referenced tables exist in the database
    2. All referenced columns exist in their respective tables
    3. FHIR identifier patterns are correctly applied
    """
    
    def __init__(
        self,
        db_url: Optional[str] = None,
        engine: Optional[Engine] = None,
        schema_name: str = "public"
    ):
        """
        Initialize the validator with a database connection.
        
        Args:
            db_url: Database connection URL
            engine: Existing SQLAlchemy engine (alternative to db_url)
            schema_name: Database schema to validate against
        """
        if engine:
            self._engine = engine
        elif db_url:
            self._engine = create_engine(db_url)
        else:
            self._engine = None
            
        self._schema_name = schema_name
        self._table_columns: Dict[str, Set[str]] = {}
        self._tables: Set[str] = set()
        
    def load_schema(self) -> None:
        """Load the database schema into memory for validation."""
        if not self._engine:
            logger.warning("No database connection - schema validation will be limited")
            return
            
        try:
            inspector = inspect(self._engine)
            self._tables = set(inspector.get_table_names(schema=self._schema_name))
            
            for table_name in self._tables:
                columns = inspector.get_columns(table_name, schema=self._schema_name)
                self._table_columns[table_name] = {col['name'] for col in columns}
                
            logger.info(f"Loaded schema with {len(self._tables)} tables")
        except Exception as e:
            logger.error(f"Failed to load schema: {e}")
            raise
    
    def validate_table_exists(self, table_name: str) -> Optional[ValidationError]:
        """Check if a table exists in the database."""
        if not self._tables:
            return None  # Can't validate without schema
            
        if table_name not in self._tables:
            # Try to find similar tables for suggestions
            similar = self._find_similar_tables(table_name)
            return ValidationError(
                error_type="table_not_found",
                location=f"table: {table_name}",
                message=f"Table '{table_name}' does not exist in the database",
                suggested_fix=f"Did you mean: {', '.join(similar)}" if similar else None
            )
        return None
    
    def validate_column_exists(
        self, 
        table_name: str, 
        column_name: str
    ) -> Optional[ValidationError]:
        """Check if a column exists in a table."""
        if table_name not in self._table_columns:
            return None  # Table validation handles this
            
        columns = self._table_columns.get(table_name, set())
        if column_name not in columns:
            similar = self._find_similar_columns(table_name, column_name)
            return ValidationError(
                error_type="column_not_found",
                location=f"column: {table_name}.{column_name}",
                message=f"Column '{column_name}' does not exist in table '{table_name}'",
                suggested_fix=f"Available columns: {', '.join(sorted(columns)[:10])}" if columns else None
            )
        return None
    
    def validate_fhir_identifier_usage(
        self, 
        table_name: str, 
        identifier_column: str,
        context: str = ""
    ) -> Optional[ValidationError]:
        """
        Validate correct FHIR identifier usage based on table type.
        
        This is CRITICAL for healthcare schemas where:
        - patient_gold uses res_id (NOT patient_id)
        - patient_tracker_gold uses patient_id
        - Clinical tables use patient_id as FK
        """
        # Check patient_gold special case
        if table_name == "patient_gold" and identifier_column == "patient_id":
            return ValidationError(
                error_type="invalid_fhir_pattern",
                location=f"{context or 'usage'}: {table_name}.{identifier_column}",
                message=f"CRITICAL: patient_gold does NOT have a 'patient_id' column. Use 'res_id' instead.",
                suggested_fix="Use 'res_id' for patient identifier in patient_gold table, or use patient_tracker_gold.patient_id for patient counts"
            )
        
        # Check if using res_id where patient_id should be used
        if table_name == "patient_tracker_gold" and identifier_column == "res_id":
            return ValidationError(
                error_type="invalid_fhir_pattern",
                location=f"{context or 'usage'}: {table_name}.{identifier_column}",
                message=f"patient_tracker_gold uses 'patient_id', not 'res_id'",
                suggested_fix="Use 'patient_id' for patient identifier in patient_tracker_gold table"
            )
            
        return None
    
    def validate_data_dictionary(
        self, 
        data_dict: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate a complete data dictionary configuration.
        
        Args:
            data_dict: Parsed YAML data dictionary
            
        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult(is_valid=True)
        
        # Load schema if not already loaded
        if not self._tables and self._engine:
            self.load_schema()
        
        # Validate business_definitions section
        if "business_definitions" in data_dict:
            self._validate_business_definitions(
                data_dict["business_definitions"], 
                result
            )
        
        # Validate synonyms section
        if "synonyms" in data_dict:
            self._validate_synonyms(data_dict["synonyms"], result)
        
        # Validate fhir_identifier_rules if present
        if "fhir_identifier_rules" in data_dict:
            self._validate_fhir_rules(
                data_dict["fhir_identifier_rules"], 
                result
            )
        
        result.is_valid = len(result.errors) == 0
        return result
    
    def _validate_business_definitions(
        self, 
        definitions: Dict[str, Any],
        result: ValidationResult
    ) -> None:
        """Validate all business definition entries."""
        for term, definition in definitions.items():
            if not isinstance(definition, dict):
                continue
                
            table = definition.get("table")
            condition = definition.get("condition", "")
            
            if table:
                # Validate table exists
                error = self.validate_table_exists(table)
                if error:
                    error.location = f"business_definitions.{term}.table"
                    result.errors.append(error)
                else:
                    result.validated_tables.add(table)
                
                # Extract and validate column references from condition
                columns = self._extract_columns_from_condition(condition)
                for col in columns:
                    col_error = self.validate_column_exists(table, col)
                    if col_error:
                        col_error.location = f"business_definitions.{term}.condition"
                        result.errors.append(col_error)
                    else:
                        if table not in result.validated_columns:
                            result.validated_columns[table] = set()
                        result.validated_columns[table].add(col)
                    
                    # Check FHIR identifier patterns
                    if col in ("patient_id", "res_id"):
                        fhir_error = self.validate_fhir_identifier_usage(
                            table, col, f"business_definitions.{term}"
                        )
                        if fhir_error:
                            result.errors.append(fhir_error)
    
    def _validate_synonyms(
        self, 
        synonyms: Dict[str, Any],
        result: ValidationResult
    ) -> None:
        """Validate synonym table and column references."""
        for key, values in synonyms.items():
            # Check if key looks like a table name (ends with _gold)
            if key.endswith("_gold"):
                error = self.validate_table_exists(key)
                if error:
                    error.location = f"synonyms.{key}"
                    # Demote to warning for synonyms
                    result.warnings.append(error)
                else:
                    result.validated_tables.add(key)
    
    def _validate_fhir_rules(
        self, 
        fhir_rules: Dict[str, Any],
        result: ValidationResult
    ) -> None:
        """Validate FHIR identifier rule configurations."""
        patient_count_tables = fhir_rules.get("patient_count_tables", {})
        
        for table, config in patient_count_tables.items():
            error = self.validate_table_exists(table)
            if error:
                error.location = f"fhir_identifier_rules.patient_count_tables.{table}"
                result.errors.append(error)
            else:
                result.validated_tables.add(table)
                
                # Validate the identifier column exists
                identifier = config.get("identifier")
                if identifier:
                    col_error = self.validate_column_exists(table, identifier)
                    if col_error:
                        col_error.location = f"fhir_identifier_rules.patient_count_tables.{table}.identifier"
                        result.errors.append(col_error)
    
    def _extract_columns_from_condition(self, condition: str) -> Set[str]:
        """Extract column names from a SQL-like condition string."""
        if not condition:
            return set()
            
        # Pattern to match potential column names (alphanumeric + underscore)
        # Exclude SQL keywords and functions
        sql_keywords = {
            'and', 'or', 'not', 'in', 'is', 'null', 'true', 'false',
            'count', 'distinct', 'sum', 'avg', 'min', 'max', 'where',
            'select', 'from', 'group', 'by', 'order', 'asc', 'desc',
            'between', 'like', 'ilike', 'current_date', 'interval',
            'date_trunc', 'days', 'months', 'years', 'day', 'month', 'year'
        }
        
        # Find all word-like tokens
        tokens = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', condition)
        
        # Filter out SQL keywords and string literals
        columns = {
            token for token in tokens 
            if token.lower() not in sql_keywords
            and not token.startswith("'")
            and not token.isnumeric()
        }
        
        return columns
    
    def _find_similar_tables(self, table_name: str, max_results: int = 3) -> List[str]:
        """Find tables with similar names."""
        if not self._tables:
            return []
            
        # Simple similarity: tables containing the search term
        candidates = []
        search_parts = table_name.lower().replace('_', ' ').split()
        
        for table in self._tables:
            table_parts = table.lower().replace('_', ' ').split()
            if any(part in table_parts for part in search_parts):
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
            
        # Simple similarity: columns containing the search term
        search_parts = column_name.lower().replace('_', ' ').split()
        
        candidates = []
        for col in columns:
            col_parts = col.lower().replace('_', ' ').split()
            if any(part in col_parts for part in search_parts):
                candidates.append(col)
                
        return candidates[:max_results]


def validate_data_dictionary_file(
    data_dict_path: str,
    db_url: str,
    schema_name: str = "public"
) -> ValidationResult:
    """
    Convenience function to validate a data dictionary YAML file.
    
    Args:
        data_dict_path: Path to the YAML file
        db_url: Database connection URL
        schema_name: Database schema name
        
    Returns:
        ValidationResult with all errors and warnings
    """
    import yaml
    
    with open(data_dict_path, 'r') as f:
        data_dict = yaml.safe_load(f)
    
    validator = SchemaValidator(db_url=db_url, schema_name=schema_name)
    return validator.validate_data_dictionary(data_dict)


def format_validation_report(result: ValidationResult) -> str:
    """Format a validation result as a human-readable report."""
    lines = []
    
    if result.is_valid:
        lines.append("✅ Data Dictionary Validation PASSED")
        lines.append(f"   Validated {len(result.validated_tables)} tables")
    else:
        lines.append("❌ Data Dictionary Validation FAILED")
        lines.append(f"   Found {len(result.errors)} error(s)")
    
    if result.errors:
        lines.append("\n📛 ERRORS:")
        for err in result.errors:
            lines.append(f"   [{err.error_type}] {err.location}")
            lines.append(f"      {err.message}")
            if err.suggested_fix:
                lines.append(f"      💡 {err.suggested_fix}")
    
    if result.warnings:
        lines.append("\n⚠️ WARNINGS:")
        for warn in result.warnings:
            lines.append(f"   [{warn.error_type}] {warn.location}")
            lines.append(f"      {warn.message}")
    
    return "\n".join(lines)
