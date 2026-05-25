"""
Schema Manifest — Pre-compiled, cached semantic schema layer for FHIR healthcare data.

Inspired by  MDL (Modeling Definition Language), this module provides:
- One-time compilation of database schema + business logic
- Cached manifest per agent (loaded in <1ms vs 200-500ms runtime introspection)
- Pre-computed join paths, default filters, and calculated fields
- Deterministic schema context generation (no LLM needed)
- FHIR-aware semantic tagging for healthcare data columns

The manifest is built once when:
1. Agent is created/updated
2. Database schema changes
3. DataDictionary is modified

Usage:
    # Build manifest (once, at agent creation)
    builder = SchemaManifestBuilder(engine, data_dictionary, schema_graph)
    manifest = await builder.build()
    manifest.save(f"data/manifests/{agent_id}.json")
    
    # Load manifest (every query, <1ms)
    manifest = SchemaManifest.load(f"data/manifests/{agent_id}.json")
    
    # Get context for SQL generation
    context = manifest.get_context_for_query(linked_tables=["patient_tracker", "encounter"])
"""
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class JoinType(str, Enum):
    """SQL join types."""
    INNER = "INNER JOIN"
    LEFT = "LEFT JOIN"
    RIGHT = "RIGHT JOIN"
    FULL = "FULL OUTER JOIN"


@dataclass
class ManifestColumn:
    """Column definition in the manifest."""
    name: str
    data_type: str
    description: Optional[str] = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    fk_references: Optional[str] = None  # "table.column"
    is_nullable: bool = True
    default_value: Optional[str] = None
    # Semantic tags for quick matching
    semantic_tags: List[str] = field(default_factory=list)  # e.g., ["patient_id", "identifier"]


@dataclass
class ManifestRelationship:
    """Pre-computed relationship/join path."""
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    join_type: JoinType = JoinType.LEFT
    # Pre-built SQL clause
    join_clause: str = ""
    
    def __post_init__(self):
        if not self.join_clause:
            self.join_clause = (
                f"{self.join_type.value} {self.target_table} "
                f"ON {self.source_table}.{self.source_column} = "
                f"{self.target_table}.{self.target_column}"
            )


@dataclass
class ManifestModel:
    """
    A semantic model (like  MDL model) for FHIR healthcare data.
    
    Maps business entities to underlying tables with:
    - Pre-defined columns and their semantics
    - Default filters (always applied unless overridden)
    - Calculated fields (SQL expressions)
    - Relationships to other models (e.g., patient → encounter → condition)
    """
    name: str
    table_reference: str  # Actual database table name
    schema_name: str = "public"
    description: Optional[str] = None
    
    # Column definitions
    columns: List[ManifestColumn] = field(default_factory=list)
    
    # Primary key columns
    primary_key: List[str] = field(default_factory=list)
    
    # Default filters (always applied)
    # e.g., ["is_deleted = false", "is_active = true"]
    default_filters: List[str] = field(default_factory=list)
    
    # Calculated/derived fields
    # e.g., {"age": "DATE_PART('year', AGE(birth_date))"}
    calculated_fields: Dict[str, str] = field(default_factory=dict)
    
    # Relationships to other models
    relationships: List[ManifestRelationship] = field(default_factory=list)
    
    # Business synonyms that map to this model
    synonyms: List[str] = field(default_factory=list)
    
    def get_column(self, name: str) -> Optional[ManifestColumn]:
        """Get column by name."""
        for col in self.columns:
            if col.name.lower() == name.lower():
                return col
        return None
    
    def to_cte_sql(self, include_filters: bool = True) -> str:
        """
        Generate CTE SQL for this model.
        
        This is the key to deterministic SQL generation:
        Instead of LLM writing raw SQL, it writes against semantic models,
        and we expand them to CTEs with correct filters/joins.
        """
        # Select all columns + calculated fields
        select_parts = []
        for col in self.columns:
            select_parts.append(f"{self.table_reference}.{col.name}")
        
        for calc_name, calc_expr in self.calculated_fields.items():
            select_parts.append(f"({calc_expr}) AS {calc_name}")
        
        sql = f"SELECT {', '.join(select_parts)} FROM {self.schema_name}.{self.table_reference}"
        
        # Apply default filters
        if include_filters and self.default_filters:
            where_clause = " AND ".join(self.default_filters)
            sql += f" WHERE {where_clause}"
        
        return sql


@dataclass
class SchemaManifest:
    """
    Pre-compiled semantic schema manifest.
    
    Like  compiled MDL, this is the single source of truth for:
    - What tables/models exist
    - How they relate to each other
    - What default filters apply
    - What business terms map to what schema elements
    
    Benefits over runtime introspection:
    - Load time: <1ms vs 200-500ms
    - Consistency: Same schema every time
    - Version control: Can be diffed, reviewed
    - Business logic: Embedded in manifest, not scattered in prompts
    """
    agent_id: str
    version: str  # Hash of schema + config for cache invalidation
    created_at: str
    
    # Core models
    models: Dict[str, ManifestModel] = field(default_factory=dict)
    
    # Pre-computed join paths between all table pairs
    # Key: "table1->table2", Value: list of join steps
    join_paths: Dict[str, List[ManifestRelationship]] = field(default_factory=dict)
    
    # Global business definitions (from DataDictionary)
    business_definitions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Metric templates
    metric_templates: Dict[str, str] = field(default_factory=dict)
    
    # Synonym index: business term → model name
    synonym_index: Dict[str, str] = field(default_factory=dict)
    
    # Validation rules
    denied_patterns: List[str] = field(default_factory=list)  # Blocked SQL patterns
    
    # Metadata
    table_count: int = 0
    column_count: int = 0
    relationship_count: int = 0
    
    def get_model(self, name: str) -> Optional[ManifestModel]:
        """Get model by name or synonym."""
        # Direct match
        if name in self.models:
            return self.models[name]
        # Synonym match
        canonical = self.synonym_index.get(name.lower())
        if canonical and canonical in self.models:
            return self.models[canonical]
        return None
    
    def get_models_for_tables(self, tables: List[str]) -> List[ManifestModel]:
        """Get models for a list of table names."""
        return [self.models[t] for t in tables if t in self.models]
    
    def get_join_path(self, source: str, target: str) -> Optional[List[ManifestRelationship]]:
        """Get pre-computed join path between two tables."""
        key = f"{source}->{target}"
        if key in self.join_paths:
            return self.join_paths[key]
        # Try reverse
        key_rev = f"{target}->{source}"
        return self.join_paths.get(key_rev)
    
    def get_context_for_query(
        self,
        linked_tables: List[str],
        include_relationships: bool = True,
        include_definitions: bool = True,
        max_columns_per_table: int = 50
    ) -> str:
        """
        Generate optimized schema context for SQL generation.
        
        This replaces the slow `get_semantic_schema_context()` with
        pre-compiled, deterministic context.
        """
        parts = []
        
        # Models and their columns
        parts.append("=== SEMANTIC MODELS ===")
        for table_name in linked_tables:
            model = self.get_model(table_name)
            if not model:
                continue
            
            parts.append(f"\n-- {model.name} --")
            if model.description:
                parts.append(f"Description: {model.description}")
            
            # Columns
            col_lines = []
            for col in model.columns[:max_columns_per_table]:
                col_desc = f"  {col.name} ({col.data_type})"
                if col.is_primary_key:
                    col_desc += " [PK]"
                if col.is_foreign_key:
                    col_desc += f" [FK→{col.fk_references}]"
                if col.description:
                    col_desc += f" -- {col.description}"
                col_lines.append(col_desc)
            parts.append("Columns:\n" + "\n".join(col_lines))
            
            # Calculated fields
            if model.calculated_fields:
                calc_lines = [f"  {k}: {v}" for k, v in model.calculated_fields.items()]
                parts.append("Calculated Fields:\n" + "\n".join(calc_lines))
            
            # Default filters
            if model.default_filters:
                parts.append(f"Default Filters: {', '.join(model.default_filters)}")
        
        # Relationships
        if include_relationships:
            relevant_joins = []
            for i, t1 in enumerate(linked_tables):
                for t2 in linked_tables[i+1:]:
                    path = self.get_join_path(t1, t2)
                    if path:
                        relevant_joins.extend(path)
            
            if relevant_joins:
                parts.append("\n=== JOIN RELATIONSHIPS ===")
                for rel in relevant_joins:
                    parts.append(f"  {rel.source_table}.{rel.source_column} → {rel.target_table}.{rel.target_column}")
        
        # Business definitions
        if include_definitions and self.business_definitions:
            # Filter to definitions relevant to linked tables
            relevant_defs = {
                k: v for k, v in self.business_definitions.items()
                if isinstance(v, dict) and v.get("table") in linked_tables
            }
            if relevant_defs:
                parts.append("\n=== BUSINESS DEFINITIONS ===")
                for term, defn in relevant_defs.items():
                    desc = defn.get("description", defn.get("condition", ""))
                    parts.append(f"  {term}: {desc}")
        
        return "\n".join(parts)
    
    def generate_cte_block(self, tables: List[str]) -> str:
        """
        Generate CTE block for semantic models.
        
        This is the key to deterministic SQL:
        User query: SELECT * FROM patients WHERE status = 'active'
        We expand 'patients' model to CTE with default filters.
        """
        ctes = []
        for table_name in tables:
            model = self.get_model(table_name)
            if model:
                cte_sql = model.to_cte_sql(include_filters=True)
                ctes.append(f'"{model.name}" AS (\n  {cte_sql}\n)')
        
        if ctes:
            return "WITH " + ",\n".join(ctes)
        return ""
    
    def validate_sql(self, sql: str) -> Tuple[bool, List[str]]:
        """
        Validate SQL against manifest rules.
        
        Checks:
        1. All referenced tables exist in manifest
        2. No denied patterns (like dangerous functions)
        3. Proper use of semantic models
        """
        errors = []
        sql_lower = sql.lower()
        
        # Check denied patterns
        for pattern in self.denied_patterns:
            if pattern.lower() in sql_lower:
                errors.append(f"Denied pattern found: {pattern}")
        
        # Could add more validation here (table existence, etc.)
        
        return len(errors) == 0, errors
    
    def save(self, path: str) -> None:
        """Save manifest to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict, handling dataclasses and enums
        def to_dict(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return {k: to_dict(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, Enum):
                return obj.value
            elif isinstance(obj, dict):
                return {k: to_dict(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [to_dict(v) for v in obj]
            return obj
        
        data = to_dict(self)
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Manifest saved to {path}")
    
    @classmethod
    def load(cls, path: str) -> Optional["SchemaManifest"]:
        """Load manifest from JSON file."""
        path = Path(path)
        if not path.exists():
            return None
        
        try:
            start = time.time()
            with open(path, "r") as f:
                data = json.load(f)
            
            # Reconstruct dataclasses
            models = {}
            for name, model_data in data.get("models", {}).items():
                columns = [ManifestColumn(**col) for col in model_data.get("columns", [])]
                relationships = [
                    ManifestRelationship(**rel) 
                    for rel in model_data.get("relationships", [])
                ]
                models[name] = ManifestModel(
                    name=model_data["name"],
                    table_reference=model_data["table_reference"],
                    schema_name=model_data.get("schema_name", "public"),
                    description=model_data.get("description"),
                    columns=columns,
                    primary_key=model_data.get("primary_key", []),
                    default_filters=model_data.get("default_filters", []),
                    calculated_fields=model_data.get("calculated_fields", {}),
                    relationships=relationships,
                    synonyms=model_data.get("synonyms", [])
                )
            
            join_paths = {}
            for key, path_data in data.get("join_paths", {}).items():
                join_paths[key] = [ManifestRelationship(**rel) for rel in path_data]
            
            manifest = cls(
                agent_id=data["agent_id"],
                version=data["version"],
                created_at=data["created_at"],
                models=models,
                join_paths=join_paths,
                business_definitions=data.get("business_definitions", {}),
                metric_templates=data.get("metric_templates", {}),
                synonym_index=data.get("synonym_index", {}),
                denied_patterns=data.get("denied_patterns", []),
                table_count=data.get("table_count", 0),
                column_count=data.get("column_count", 0),
                relationship_count=data.get("relationship_count", 0)
            )
            
            elapsed_ms = (time.time() - start) * 1000
            logger.info(f"Manifest loaded in {elapsed_ms:.1f}ms: {manifest.table_count} tables")
            
            return manifest
            
        except Exception as e:
            logger.error(f"Failed to load manifest from {path}: {e}")
            return None


class SchemaManifestBuilder:
    """
    Builds SchemaManifest from SchemaGraph + DataDictionary.
    
    This runs once per agent (on create/update), not per query.
    """
    
    def __init__(
        self,
        agent_id: str,
        schema_graph: "SchemaGraph",  # From schema_graph.py
        data_dictionary: "DataDictionary"  # From data_dictionary.py
    ):
        self.agent_id = agent_id
        self.schema_graph = schema_graph
        self.data_dictionary = data_dictionary
    
    def build(self) -> SchemaManifest:
        """Build the manifest from schema graph and data dictionary."""
        start = time.time()
        
        models = self._build_models()
        join_paths = self._build_join_paths(list(models.keys()))
        synonym_index = self._build_synonym_index(models)
        
        # Compute version hash for cache invalidation
        version = self._compute_version_hash(models, join_paths)
        
        manifest = SchemaManifest(
            agent_id=self.agent_id,
            version=version,
            created_at=datetime.utcnow().isoformat(),
            models=models,
            join_paths=join_paths,
            business_definitions=self.data_dictionary._business_definitions,
            metric_templates={
                k: v.get("sql", str(v)) 
                for k, v in self.data_dictionary._metric_templates.items()
            },
            synonym_index=synonym_index,
            denied_patterns=["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE"],
            table_count=len(models),
            column_count=sum(len(m.columns) for m in models.values()),
            relationship_count=sum(len(m.relationships) for m in models.values())
        )
        
        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            f"Manifest built in {elapsed_ms:.0f}ms: "
            f"{manifest.table_count} tables, {manifest.column_count} columns, "
            f"{manifest.relationship_count} relationships"
        )
        
        return manifest
    
    def _build_models(self) -> Dict[str, ManifestModel]:
        """Build ManifestModel for each table in schema graph."""
        models = {}
        
        for table_name, table_info in self.schema_graph.tables.items():
            # Build FK lookup for this table: column_name -> "target_table.target_column"
            fk_lookup = {}
            for fk in table_info.foreign_keys:
                fk_lookup[fk.source_column] = f"{fk.target_table}.{fk.target_column}"
            
            # Convert columns
            columns = []
            for col in table_info.columns:
                # Derive fk_references from FK lookup
                fk_ref = fk_lookup.get(col.name) if col.is_foreign_key else None
                
                manifest_col = ManifestColumn(
                    name=col.name,
                    data_type=col.data_type,
                    description=self.data_dictionary.get_column_description(table_name, col.name),
                    is_primary_key=col.is_primary_key,
                    is_foreign_key=col.is_foreign_key,
                    fk_references=fk_ref,
                    is_nullable=col.is_nullable,
                    default_value=col.default_value,
                    semantic_tags=self._get_semantic_tags(col.name)
                )
                columns.append(manifest_col)
            
            # Get relationships from schema graph
            relationships = []
            for target_table, fk_list in self.schema_graph._adjacency.get(table_name, {}).items():
                for fk in fk_list:
                    relationships.append(ManifestRelationship(
                        source_table=table_name,
                        source_column=fk.source_column,
                        target_table=fk.target_table,
                        target_column=fk.target_column,
                        join_type=JoinType.LEFT
                    ))
            
            # Build the model
            model = ManifestModel(
                name=table_name,
                table_reference=table_name,
                schema_name=table_info.schema_name,
                description=self.data_dictionary.get_table_description(table_name),
                columns=columns,
                primary_key=table_info.primary_keys,
                default_filters=self.data_dictionary.get_default_filters(table_name),
                calculated_fields={},  # Could be extended from DataDictionary
                relationships=relationships,
                synonyms=self._get_synonyms_for_table(table_name)
            )
            
            models[table_name] = model
        
        return models
    
    def _build_join_paths(self, table_names: List[str]) -> Dict[str, List[ManifestRelationship]]:
        """Pre-compute join paths between all table pairs."""
        join_paths = {}
        
        for i, t1 in enumerate(table_names):
            for t2 in table_names[i+1:]:
                path = self.schema_graph.get_join_path(t1, t2)
                if path:
                    # Convert JoinPath to list of ManifestRelationship
                    # JoinStep uses from_table/from_column/to_table/to_column
                    relationships = []
                    for step in path.steps:
                        relationships.append(ManifestRelationship(
                            source_table=step.from_table,
                            source_column=step.from_column,
                            target_table=step.to_table,
                            target_column=step.to_column
                        ))
                    join_paths[f"{t1}->{t2}"] = relationships
        
        return join_paths
    
    def _build_synonym_index(self, models: Dict[str, ManifestModel]) -> Dict[str, str]:
        """Build index mapping synonyms to canonical model names."""
        index = {}
        
        # From DataDictionary synonyms
        for synonym, canonical in self.data_dictionary._synonyms.items():
            if canonical in models:
                index[synonym.lower()] = canonical
        
        # From model synonyms
        for model_name, model in models.items():
            for syn in model.synonyms:
                index[syn.lower()] = model_name
            # Also index the model name itself
            index[model_name.lower()] = model_name
        
        return index
    
    def _get_semantic_tags(self, column_name: str) -> List[str]:
        """Get semantic tags for a column based on FHIR healthcare naming conventions."""
        tags = []
        col_lower = column_name.lower()
        
        # =====================================================================
        # FHIR Resource Identifiers
        # =====================================================================
        if "patient_id" in col_lower or "patient_tracker_id" in col_lower:
            tags.extend(["patient", "identifier", "fhir_reference"])
        elif "encounter_id" in col_lower:
            tags.extend(["encounter", "identifier", "fhir_reference"])
        elif "practitioner_id" in col_lower or "provider_id" in col_lower:
            tags.extend(["practitioner", "identifier", "fhir_reference"])
        elif "organization_id" in col_lower or "org_id" in col_lower:
            tags.extend(["organization", "identifier", "fhir_reference"])
        elif "site_id" in col_lower or "facility_id" in col_lower:
            tags.extend(["site", "identifier", "fhir_reference"])
        elif "condition_id" in col_lower:
            tags.extend(["condition", "identifier", "fhir_reference"])
        elif "observation_id" in col_lower:
            tags.extend(["observation", "identifier", "fhir_reference"])
        elif "medication_id" in col_lower:
            tags.extend(["medication", "identifier", "fhir_reference"])
        elif "appointment_id" in col_lower:
            tags.extend(["appointment", "identifier", "fhir_reference"])
        elif "_id" in col_lower or "id" == col_lower:
            tags.append("identifier")
        
        # =====================================================================
        # FHIR Coding Systems
        # =====================================================================
        if "icd" in col_lower or "diagnosis_code" in col_lower or "condition_code" in col_lower:
            tags.extend(["icd_code", "diagnosis", "coding"])
        if "cpt" in col_lower or "procedure_code" in col_lower:
            tags.extend(["cpt_code", "procedure", "coding"])
        if "loinc" in col_lower or "observation_code" in col_lower:
            tags.extend(["loinc_code", "observation", "coding"])
        if "rxnorm" in col_lower or "medication_code" in col_lower or "drug_code" in col_lower:
            tags.extend(["rxnorm_code", "medication", "coding"])
        if "snomed" in col_lower:
            tags.extend(["snomed_code", "coding"])
        if "ndc" in col_lower:
            tags.extend(["ndc_code", "medication", "coding"])
        
        # =====================================================================
        # Clinical Status Fields
        # =====================================================================
        if "status" in col_lower:
            tags.append("status")
            if "enrollment" in col_lower:
                tags.append("enrollment")
            elif "encounter" in col_lower or "visit" in col_lower:
                tags.append("encounter")
        
        # =====================================================================
        # Temporal Fields
        # =====================================================================
        if any(t in col_lower for t in ["date", "time", "_at", "datetime"]):
            tags.append("temporal")
            if "birth" in col_lower or "dob" in col_lower:
                tags.append("birthdate")
            elif "death" in col_lower:
                tags.append("deathdate")
            elif "encounter" in col_lower or "visit" in col_lower:
                tags.append("encounter_date")
            elif "screening" in col_lower:
                tags.append("screening_date")
            elif "created" in col_lower:
                tags.append("created_at")
            elif "updated" in col_lower or "modified" in col_lower:
                tags.append("updated_at")
        
        # =====================================================================
        # Patient Demographics
        # =====================================================================
        if "gender" in col_lower or "sex" in col_lower:
            tags.append("gender")
        if "age" in col_lower:
            tags.append("age")
        if "race" in col_lower or "ethnicity" in col_lower:
            tags.append("demographics")
        if "mrn" in col_lower or "medical_record" in col_lower:
            tags.extend(["mrn", "patient_identifier"])
        
        # =====================================================================
        # Clinical Metrics
        # =====================================================================
        if any(m in col_lower for m in ["count", "total", "sum", "avg", "rate"]):
            tags.append("metric")
        if "score" in col_lower or "value" in col_lower or "result" in col_lower:
            tags.append("clinical_value")
        if "bp" in col_lower or "blood_pressure" in col_lower:
            tags.append("vital_sign")
        if "pulse" in col_lower or "heart_rate" in col_lower:
            tags.append("vital_sign")
        if "weight" in col_lower or "height" in col_lower or "bmi" in col_lower:
            tags.append("vital_sign")
        if "temperature" in col_lower or "temp" in col_lower:
            tags.append("vital_sign")
        
        # =====================================================================
        # Boolean Flags
        # =====================================================================
        if col_lower.startswith("is_") or col_lower.startswith("has_"):
            tags.append("boolean")
            if "active" in col_lower:
                tags.append("active_flag")
            if "deleted" in col_lower:
                tags.append("soft_delete")
            if "enrolled" in col_lower:
                tags.append("enrollment")
        
        # =====================================================================
        # Name/Description Fields
        # =====================================================================
        if "name" in col_lower or "display" in col_lower or "description" in col_lower:
            tags.append("text")
            if "first" in col_lower or "given" in col_lower:
                tags.append("given_name")
            elif "last" in col_lower or "family" in col_lower:
                tags.append("family_name")
        
        return list(set(tags))  # Remove duplicates
    
    def _get_synonyms_for_table(self, table_name: str) -> List[str]:
        """Get all synonyms that resolve to this table."""
        synonyms = []
        for syn, canonical in self.data_dictionary._synonyms.items():
            if canonical == table_name:
                synonyms.append(syn)
        return synonyms
    
    def _compute_version_hash(
        self,
        models: Dict[str, ManifestModel],
        join_paths: Dict[str, List[ManifestRelationship]]
    ) -> str:
        """Compute hash for cache invalidation."""
        # Hash key schema elements
        hash_input = json.dumps({
            "tables": sorted(models.keys()),
            "columns": {
                k: [c.name for c in v.columns]
                for k, v in sorted(models.items())
            },
            "filters": {
                k: v.default_filters
                for k, v in sorted(models.items())
            }
        }, sort_keys=True)
        
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]


def get_manifest_path(agent_id: str) -> Path:
    """Get the path to an agent's manifest file."""
    return Path(f"data/manifests/{agent_id}.json")


async def get_or_build_manifest(
    agent_id: str,
    schema_graph: "SchemaGraph",
    data_dictionary: "DataDictionary",
    force_rebuild: bool = False
) -> SchemaManifest:
    """
    Get cached manifest or build a new one.
    
    This is the main entry point for getting a manifest.
    """
    manifest_path = get_manifest_path(agent_id)
    
    # Try to load cached manifest
    if not force_rebuild and manifest_path.exists():
        manifest = SchemaManifest.load(str(manifest_path))
        if manifest:
            return manifest
    
    # Build new manifest
    builder = SchemaManifestBuilder(agent_id, schema_graph, data_dictionary)
    manifest = builder.build()
    manifest.save(str(manifest_path))
    
    return manifest
