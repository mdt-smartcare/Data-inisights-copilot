"""
Data Dictionary — Semantic enrichment layer for SQL generation.

Maps business terms, synonyms, metric templates, and default filters
to database schema elements. Loaded from a YAML configuration file.

This enables the system to:
- Resolve business terms to schema elements (e.g., "active patient" → WHERE clause)
- Apply mandatory filters automatically (e.g., is_active = true)
- Provide metric templates for common calculations
- Map synonyms from user language to column/table names
"""
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class DataDictionary:
    """
    Semantic enrichment layer mapping business terms to schema elements.
    
    Loaded from YAML config. Provides:
    - Business definitions (e.g., "active patient" → SQL condition)
    - Metric templates (e.g., "screening rate" → SQL expression)
    - Synonym resolution (user term → column/table name)
    - Default filters per table (e.g., always filter is_deleted = false)
    - Column semantics (descriptions for important columns)
    
    Usage:
        dd = DataDictionary()
        
        # Resolve a business term
        definition = dd.resolve_term("active patient")
        # → {"table": "patient_tracker", "condition": "is_active = true AND is_deleted = false"}
        
        # Get default filters for a table
        filters = dd.get_default_filters("patient_tracker")
        # → ["is_active = true", "is_deleted = false"]
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize DataDictionary from YAML config.
        
        Args:
            config_path: Path to data_dictionary.yaml. Creates empty dict if not provided.
        """
        self._config_path = Path(config_path) if config_path else None
        
        # Core data structures
        self._business_definitions: Dict[str, Dict[str, Any]] = {}
        self._metric_templates: Dict[str, Dict[str, Any]] = {}
        self._synonyms: Dict[str, str] = {}  # synonym → canonical schema element
        self._default_filters: Dict[str, List[str]] = {}  # table → [filter_conditions]
        self._column_semantics: Dict[str, Dict[str, str]] = {}  # table → {column → description}
        self._table_descriptions: Dict[str, str] = {}  # table → description
        
        self._load()
    
    def _load(self):
        """Load data dictionary from YAML config file."""
        if not self._config_path or not self._config_path.exists():
            logger.info(
                "Data dictionary config not provided or not found. "
                "Using empty dictionary. Create a config file to enable semantic enrichment."
            )
            return
        
        try:
            import yaml
            with open(self._config_path, "r") as f:
                config = yaml.safe_load(f) or {}
            
            self._business_definitions = config.get("business_definitions", {})
            self._metric_templates = config.get("metric_templates", {})
            self._default_filters = config.get("default_filters", {})
            self._column_semantics = config.get("column_semantics", {})
            self._table_descriptions = config.get("table_descriptions", {})
            
            # Build synonym index (lowercase for case-insensitive matching)
            raw_synonyms = config.get("synonyms", {})
            for canonical, aliases in raw_synonyms.items():
                if isinstance(aliases, list):
                    for alias in aliases:
                        self._synonyms[alias.lower()] = canonical
                elif isinstance(aliases, str):
                    self._synonyms[aliases.lower()] = canonical
                # Also index the canonical term itself
                self._synonyms[canonical.lower()] = canonical
            
            logger.info(
                f"DataDictionary loaded: {len(self._business_definitions)} definitions, "
                f"{len(self._metric_templates)} metric templates, "
                f"{len(self._synonyms)} synonyms, "
                f"{sum(len(v) for v in self._default_filters.values())} default filters"
            )
            
        except ImportError:
            logger.warning(
                "PyYAML not installed. Install with: pip install pyyaml. "
                "DataDictionary will use empty config."
            )
        except Exception as e:
            logger.error(f"Failed to load data dictionary: {e}")
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def resolve_term(self, term: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a business term to its schema mapping.
        
        Args:
            term: Business term (e.g., "active patient", "screening rate")
            
        Returns:
            Dictionary with schema mapping, or None if not found.
            e.g., {"table": "patient_tracker", "condition": "is_active = true"}
        """
        term_lower = term.lower()
        
        # Direct match in business definitions
        if term_lower in self._business_definitions:
            return self._business_definitions[term_lower]
        
        # Synonym resolution
        canonical = self._synonyms.get(term_lower)
        if canonical and canonical.lower() in self._business_definitions:
            return self._business_definitions[canonical.lower()]
        
        # Partial match - find definitions containing the term
        for key, definition in self._business_definitions.items():
            if term_lower in key or key in term_lower:
                return definition
        
        return None
    
    def resolve_synonym(self, term: str) -> Optional[str]:
        """
        Resolve a synonym to its canonical schema element.
        
        Args:
            term: User-facing term (e.g., "HbA1c", "blood sugar")
            
        Returns:
            Canonical schema reference (e.g., "patient_lab_test.lab_test_name")
        """
        return self._synonyms.get(term.lower())
    
    def get_metric_template(self, metric_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a metric template definition.
        
        Args:
            metric_name: Name of the metric (e.g., "screening_rate")
            
        Returns:
            Metric template with SQL expression and description
        """
        return self._metric_templates.get(metric_name.lower())
    
    def get_default_filters(self, table_name: str) -> List[str]:
        """
        Get mandatory default filters for a table.
        
        Args:
            table_name: Table name
            
        Returns:
            List of SQL conditions that should always be applied
        """
        return self._default_filters.get(table_name, [])
    
    def get_all_default_filters(self, tables: List[str]) -> Dict[str, List[str]]:
        """
        Get default filters for multiple tables.
        
        Args:
            tables: List of table names
            
        Returns:
            Dict mapping table name → list of default filter conditions
        """
        result = {}
        for table in tables:
            filters = self.get_default_filters(table)
            if filters:
                result[table] = filters
        return result
    
    def get_column_description(self, table_name: str, column_name: str) -> Optional[str]:
        """
        Get the semantic description for a column.
        
        Args:
            table_name: Table name
            column_name: Column name
            
        Returns:
            Human-readable description of what the column represents
        """
        table_cols = self._column_semantics.get(table_name, {})
        return table_cols.get(column_name)
    
    def get_table_description(self, table_name: str) -> Optional[str]:
        """Get the description for a table."""
        return self._table_descriptions.get(table_name)
    
    def find_tables_for_term(self, term: str) -> List[str]:
        """
        Find tables that are associated with a business term.
        
        Checks business definitions, synonyms, and column semantics.
        
        Args:
            term: Business term to search for
            
        Returns:
            List of table names associated with this term
        """
        term_lower = term.lower()
        tables = set()
        
        # Check business definitions
        definition = self.resolve_term(term)
        if definition and "table" in definition:
            table = definition["table"]
            if isinstance(table, list):
                tables.update(table)
            else:
                tables.add(table)
        
        # Check column semantics
        for table_name, columns in self._column_semantics.items():
            for col_name, description in columns.items():
                if term_lower in description.lower():
                    tables.add(table_name)
        
        return list(tables)
    
    def to_prompt_context(self, tables: Optional[List[str]] = None) -> str:
        """
        Render relevant data dictionary entries as prompt context.
        
        Args:
            tables: If provided, only include entries relevant to these tables.
            
        Returns:
            Formatted text for prompt injection
        """
        parts = []
        
        # Default filters
        relevant_filters = self.get_all_default_filters(tables) if tables else self._default_filters
        if relevant_filters:
            parts.append("MANDATORY DEFAULT FILTERS (always apply unless explicitly asked otherwise):")
            for table, filters in relevant_filters.items():
                for f in filters:
                    parts.append(f"  - {table}: {f}")
        
        # Business definitions relevant to the tables
        if tables:
            relevant_defs = {}
            for key, defn in self._business_definitions.items():
                if isinstance(defn, dict):
                    def_table = defn.get("table", "")
                    if isinstance(def_table, str) and def_table in tables:
                        relevant_defs[key] = defn
                    elif isinstance(def_table, list) and any(t in tables for t in def_table):
                        relevant_defs[key] = defn
            
            if relevant_defs:
                parts.append("\nBUSINESS DEFINITIONS:")
                for key, defn in relevant_defs.items():
                    desc = defn.get("description", defn.get("condition", str(defn)))
                    parts.append(f"  - {key}: {desc}")
        
        # Metric templates
        if self._metric_templates:
            relevant_metrics = {}
            for name, template in self._metric_templates.items():
                if not tables or any(t in str(template) for t in tables):
                    relevant_metrics[name] = template
            
            if relevant_metrics:
                parts.append("\nMETRIC TEMPLATES:")
                for name, template in relevant_metrics.items():
                    expr = template.get("expression", str(template))
                    desc = template.get("description", "")
                    parts.append(f"  - {name}: {expr}")
                    if desc:
                        parts.append(f"    ({desc})")
        
        return "\n".join(parts) if parts else ""
    
    def reload(self):
        """Reload the data dictionary from the config file."""
        self._business_definitions.clear()
        self._metric_templates.clear()
        self._synonyms.clear()
        self._default_filters.clear()
        self._column_semantics.clear()
        self._table_descriptions.clear()
        self._load()
        logger.info("DataDictionary reloaded")


# =============================================================================
# Singleton
# =============================================================================

_data_dictionary: Optional[DataDictionary] = None

# Default config path relative to this file
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "core" / "config" / "data_dictionary.yaml"


def get_data_dictionary(config_path: Optional[str] = None) -> DataDictionary:
    """
    Get or create the global DataDictionary instance.
    
    Args:
        config_path: Optional path to data_dictionary.yaml. 
                     If not provided, uses the default path at app/core/config/data_dictionary.yaml
    
    Returns:
        DataDictionary singleton instance
    """
    global _data_dictionary
    if _data_dictionary is None:
        if config_path is None and _DEFAULT_CONFIG_PATH.exists():
            config_path = str(_DEFAULT_CONFIG_PATH)
            logger.info(f"Loading data dictionary from default path: {config_path}")
        _data_dictionary = DataDictionary(config_path)
    return _data_dictionary


def reset_data_dictionary() -> None:
    """Reset the data dictionary singleton (mainly for testing)."""
    global _data_dictionary
    _data_dictionary = None

