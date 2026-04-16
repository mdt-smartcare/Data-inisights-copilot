"""
Data Dictionary — Semantic enrichment layer for SQL generation.

Maps business terms, synonyms, metric templates, and default filters
to database schema elements.

LOADING SOURCES (in priority order):
1. Per-agent JSON config from database (prompt_configs.data_dictionary)
2. YAML configuration file (fallback for global defaults)
3. Empty dictionary (if no config available)

This enables the system to:
- Resolve business terms to schema elements (e.g., "active patient" → WHERE clause)
- Apply mandatory filters automatically (e.g., is_active = true)
- Provide metric templates for common calculations
- Map synonyms from user language to column/table names
"""
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class DataDictionary:
    """
    Semantic enrichment layer mapping business terms to schema elements.
    
    Can be loaded from:
    - JSON string (per-agent config from database)
    - YAML file (global defaults)
    - Dict (programmatic initialization)
    
    Provides:
    - Business definitions (e.g., "active patient" → SQL condition)
    - Metric templates (e.g., "screening rate" → SQL expression)
    - Synonym resolution (user term → column/table name)
    - Default filters per table (e.g., always filter is_deleted = false)
    - Column semantics (descriptions for important columns)
    
    Usage:
        # Per-agent from database
        dd = DataDictionary.from_json(config_json, agent_id="uuid")
        
        # From YAML file
        dd = DataDictionary(config_path="/path/to/data_dictionary.yaml")
        
        # Resolve a business term
        definition = dd.resolve_term("active patient")
        # → {"table": "patient_tracker", "condition": "is_active = true AND is_deleted = false"}
    """
    
    def __init__(
        self, 
        config_path: Optional[str] = None,
        config_dict: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None
    ):
        """
        Initialize DataDictionary.
        
        Args:
            config_path: Path to data_dictionary.yaml file
            config_dict: Pre-loaded config dictionary (takes priority over file)
            agent_id: Agent ID this dictionary belongs to (for logging/debugging)
        """
        self._config_path = Path(config_path) if config_path else None
        self._agent_id = agent_id
        
        # Core data structures
        self._business_definitions: Dict[str, Dict[str, Any]] = {}
        self._metric_templates: Dict[str, Dict[str, Any]] = {}
        self._synonyms: Dict[str, str] = {}  # synonym → canonical schema element
        self._default_filters: Dict[str, List[str]] = {}  # table → [filter_conditions]
        self._column_semantics: Dict[str, Dict[str, str]] = {}  # table → {column → description}
        self._table_descriptions: Dict[str, str] = {}  # table → description
        self._business_glossary: List[str] = []  # free-form domain jargon/terms
        
        if config_dict:
            self._load_from_dict(config_dict)
        else:
            self._load_from_file()
    
    @classmethod
    def from_json(cls, json_str: str, agent_id: Optional[str] = None) -> "DataDictionary":
        """
        Create DataDictionary from a JSON string.
        
        This is the preferred method for per-agent configuration loaded from the database.
        
        Args:
            json_str: JSON string containing the data dictionary config
            agent_id: Agent ID for logging/debugging
            
        Returns:
            DataDictionary instance
        """
        try:
            config_dict = json.loads(json_str) if json_str else {}
            return cls(config_dict=config_dict, agent_id=agent_id)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse data dictionary JSON for agent {agent_id}: {e}")
            return cls(agent_id=agent_id)  # Return empty dictionary
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any], agent_id: Optional[str] = None) -> "DataDictionary":
        """
        Create DataDictionary from a dictionary.
        
        Args:
            config_dict: Dictionary containing the data dictionary config
            agent_id: Agent ID for logging/debugging
            
        Returns:
            DataDictionary instance
        """
        return cls(config_dict=config_dict, agent_id=agent_id)
    
    def _load_from_dict(self, config: Dict[str, Any]) -> None:
        """Load data dictionary from a dictionary."""
        self._business_definitions = config.get("business_definitions", {})
        self._metric_templates = config.get("metric_templates", {})
        self._default_filters = config.get("default_filters", {})
        self._column_semantics = config.get("column_semantics", {})
        self._table_descriptions = config.get("table_descriptions", {})
        self._business_glossary = config.get("business_glossary", [])
        
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
            f"DataDictionary loaded from dict: {len(self._business_definitions)} definitions, "
            f"{len(self._metric_templates)} metric templates, "
            f"{len(self._synonyms)} synonyms, "
            f"{sum(len(v) for v in self._default_filters.values())} default filters, "
            f"{len(self._business_glossary)} glossary terms",
            agent_id=self._agent_id
        )
    
    def _load_from_file(self) -> None:
        """Load data dictionary from YAML config file."""
        if not self._config_path or not self._config_path.exists():
            logger.info(
                "Data dictionary config not provided or not found. "
                "Using empty dictionary.",
                agent_id=self._agent_id
            )
            return
        
        try:
            import yaml
            with open(self._config_path, "r") as f:
                config = yaml.safe_load(f) or {}
            
            self._load_from_dict(config)
            
        except ImportError:
            logger.warning(
                "PyYAML not installed. Install with: pip install pyyaml. "
                "DataDictionary will use empty config."
            )
        except Exception as e:
            logger.error(f"Failed to load data dictionary from file: {e}")
    
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
        """Resolve a synonym to its canonical schema element."""
        return self._synonyms.get(term.lower())
    
    def get_metric_template(self, metric_name: str) -> Optional[Dict[str, Any]]:
        """Get a metric template definition."""
        return self._metric_templates.get(metric_name.lower())
    
    def get_default_filters(self, table_name: str) -> List[str]:
        """Get mandatory default filters for a table."""
        return self._default_filters.get(table_name, [])
    
    def get_all_default_filters(self, tables: List[str]) -> Dict[str, List[str]]:
        """Get default filters for multiple tables."""
        result = {}
        for table in tables:
            filters = self.get_default_filters(table)
            if filters:
                result[table] = filters
        return result
    
    def get_column_description(self, table_name: str, column_name: str) -> Optional[str]:
        """Get the semantic description for a column."""
        table_cols = self._column_semantics.get(table_name, {})
        return table_cols.get(column_name)
    
    def get_table_description(self, table_name: str) -> Optional[str]:
        """Get the description for a table."""
        return self._table_descriptions.get(table_name)
    
    def find_tables_for_term(self, term: str) -> List[str]:
        """Find tables that are associated with a business term."""
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
        
        # Business glossary (free-form domain jargon)
        if self._business_glossary:
            parts.append("\nBUSINESS GLOSSARY (domain-specific terminology):")
            for term in self._business_glossary:
                parts.append(f"  - {term}")
        
        return "\n".join(parts) if parts else ""
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Export the data dictionary as a dictionary.
        
        Useful for serialization to JSON for database storage.
        """
        # Reverse the synonym index back to canonical → [aliases] format
        reverse_synonyms: Dict[str, List[str]] = {}
        for alias, canonical in self._synonyms.items():
            if canonical not in reverse_synonyms:
                reverse_synonyms[canonical] = []
            if alias != canonical.lower():
                reverse_synonyms[canonical].append(alias)
        
        return {
            "business_definitions": self._business_definitions,
            "metric_templates": self._metric_templates,
            "synonyms": reverse_synonyms,
            "default_filters": self._default_filters,
            "column_semantics": self._column_semantics,
            "table_descriptions": self._table_descriptions,
            "business_glossary": self._business_glossary
        }
    
    def to_json(self) -> str:
        """Export the data dictionary as a JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    def merge_with(self, other: "DataDictionary") -> "DataDictionary":
        """
        Merge another DataDictionary into this one.
        
        The other dictionary's entries take precedence on conflicts.
        Useful for combining agent-specific config with global defaults.
        
        Args:
            other: Another DataDictionary to merge
            
        Returns:
            New merged DataDictionary
        """
        merged_config = self.to_dict()
        other_config = other.to_dict()
        
        # Deep merge each section
        for key in ["business_definitions", "metric_templates", "default_filters", 
                    "column_semantics", "table_descriptions", "business_glossary"]:
            if key in other_config:
                if key not in merged_config:
                    merged_config[key] = {}
                merged_config[key].update(other_config[key])
        
        # Merge synonyms (list merge)
        if "synonyms" in other_config:
            if "synonyms" not in merged_config:
                merged_config["synonyms"] = {}
            for canonical, aliases in other_config["synonyms"].items():
                if canonical in merged_config["synonyms"]:
                    merged_config["synonyms"][canonical].extend(aliases)
                else:
                    merged_config["synonyms"][canonical] = aliases
        
        return DataDictionary.from_dict(merged_config, agent_id=self._agent_id)
    
    def reload(self) -> None:
        """Reload the data dictionary from the config file."""
        self._business_definitions.clear()
        self._metric_templates.clear()
        self._synonyms.clear()
        self._default_filters.clear()
        self._column_semantics.clear()
        self._table_descriptions.clear()
        self._business_glossary.clear()
        self._load_from_file()
        logger.info("DataDictionary reloaded", agent_id=self._agent_id)
    
    @property
    def agent_id(self) -> Optional[str]:
        """Get the agent ID this dictionary belongs to."""
        return self._agent_id
    
    @property
    def is_empty(self) -> bool:
        """Check if the data dictionary is empty."""
        return (
            not self._business_definitions and
            not self._metric_templates and
            not self._synonyms and
            not self._default_filters
        )


# =============================================================================
# Per-Agent Data Dictionary Cache
# =============================================================================

_data_dictionary_cache: Dict[Optional[str], DataDictionary] = {}
_data_dictionary_lock = __import__('threading').Lock()

# Default config path relative to this file
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "core" / "config" / "data_dictionary.yaml"


def get_data_dictionary(
    agent_id: Optional[str] = None,
    config_json: Optional[str] = None,
    config_path: Optional[str] = None,
    use_cache: bool = True
) -> DataDictionary:
    """
    Get a DataDictionary instance, optionally for a specific agent.
    
    Loading priority:
    1. config_json parameter (per-agent from database)
    2. config_path parameter (explicit file path)
    3. Default YAML file (global defaults)
    4. Empty dictionary
    
    Args:
        agent_id: Agent ID for per-agent config. None = global.
        config_json: JSON string with data dictionary config (from database)
        config_path: Path to YAML config file
        use_cache: Whether to use cached instances
    
    Returns:
        DataDictionary instance
    """
    global _data_dictionary_cache
    
    cache_key = agent_id
    
    with _data_dictionary_lock:
        # Return cached if available and caching enabled
        if use_cache and cache_key in _data_dictionary_cache:
            return _data_dictionary_cache[cache_key]
        
        # Create new instance
        if config_json:
            # Per-agent config from database
            dd = DataDictionary.from_json(config_json, agent_id=agent_id)
        elif config_path:
            # Explicit file path
            dd = DataDictionary(config_path=config_path, agent_id=agent_id)
        elif _DEFAULT_CONFIG_PATH.exists():
            # Default YAML file
            logger.info(f"Loading data dictionary from default path: {_DEFAULT_CONFIG_PATH}")
            dd = DataDictionary(config_path=str(_DEFAULT_CONFIG_PATH), agent_id=agent_id)
        else:
            # Empty dictionary
            dd = DataDictionary(agent_id=agent_id)
        
        # Cache if enabled
        if use_cache:
            _data_dictionary_cache[cache_key] = dd
        
        return dd


def get_agent_data_dictionary(
    agent_id: str,
    config_json: Optional[str] = None,
    merge_with_global: bool = True
) -> DataDictionary:
    """
    Get a DataDictionary for a specific agent.
    
    If merge_with_global is True, merges agent-specific config with global defaults.
    Agent-specific entries take precedence.
    
    Args:
        agent_id: Agent ID
        config_json: JSON config from database (prompt_configs.data_dictionary)
        merge_with_global: Whether to include global defaults
        
    Returns:
        DataDictionary instance for the agent
    """
    # Get agent-specific dictionary
    if config_json:
        agent_dd = DataDictionary.from_json(config_json, agent_id=agent_id)
    else:
        agent_dd = DataDictionary(agent_id=agent_id)
    
    # Optionally merge with global defaults
    if merge_with_global and not agent_dd.is_empty:
        global_dd = get_data_dictionary(agent_id=None)
        if not global_dd.is_empty:
            return global_dd.merge_with(agent_dd)
    
    return agent_dd


def reset_data_dictionary(agent_id: Optional[str] = None) -> None:
    """
    Reset the data dictionary cache.
    
    Args:
        agent_id: Specific agent to reset. If None, resets ALL cached dictionaries.
    """
    global _data_dictionary_cache
    
    with _data_dictionary_lock:
        if agent_id is None:
            _data_dictionary_cache.clear()
            logger.info("All DataDictionary instances reset")
        elif agent_id in _data_dictionary_cache:
            del _data_dictionary_cache[agent_id]
            logger.info(f"DataDictionary reset for agent: {agent_id}")
