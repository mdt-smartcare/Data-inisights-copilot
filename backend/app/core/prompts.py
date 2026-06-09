"""
Prompt Loader Utility

Centralized utility for loading prompt templates from markdown files.
All prompts should be stored in agent_spec/prompt_templates/ directory.
"""
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# Base path for prompt templates
_PROMPT_TEMPLATES_DIR: Optional[Path] = None


def _get_templates_dir() -> Path:
    """Get the prompt templates directory path."""
    global _PROMPT_TEMPLATES_DIR
    
    if _PROMPT_TEMPLATES_DIR is not None:
        return _PROMPT_TEMPLATES_DIR
    
    # Try multiple possible locations
    possible_paths = [
        # From backend-modmono/app/core/
        Path(__file__).parent.parent.parent.parent / "agent_spec" / "prompt_templates",
        # From workspace root
        Path.cwd() / "agent_spec" / "prompt_templates",
        # Parent directory
        Path.cwd().parent / "agent_spec" / "prompt_templates",
    ]
    
    for path in possible_paths:
        if path.exists() and path.is_dir():
            _PROMPT_TEMPLATES_DIR = path
            logger.info(f"Prompt templates directory found: {path}")
            return path
    
    # Fallback to first option even if it doesn't exist
    _PROMPT_TEMPLATES_DIR = possible_paths[0]
    logger.warning(f"Prompt templates directory not found, using: {_PROMPT_TEMPLATES_DIR}")
    return _PROMPT_TEMPLATES_DIR


@lru_cache(maxsize=32)
def load_prompt(template_name: str, fallback: Optional[str] = None) -> str:
    """
    Load a prompt template from a markdown file.
    
    Args:
        template_name: Name of the template file (with or without .md extension)
        fallback: Optional fallback text if the file is not found
        
    Returns:
        The prompt template content as a string
        
    Example:
        >>> prompt = load_prompt("sql_generator")
        >>> prompt = load_prompt("intent_router", fallback="You are a helpful assistant.")
    """
    # Ensure .md extension
    if not template_name.endswith(".md"):
        template_name = f"{template_name}.md"
    
    template_path = _get_templates_dir() / template_name
    
    try:
        if template_path.exists():
            content = template_path.read_text(encoding="utf-8")
            logger.debug(f"Loaded prompt template: {template_name}")
            return content
        else:
            logger.warning(f"Prompt template not found: {template_path}")
            if fallback:
                return fallback
            raise FileNotFoundError(f"Prompt template not found: {template_name}")
    except Exception as e:
        logger.error(f"Failed to load prompt template {template_name}: {e}")
        if fallback:
            return fallback
        raise


def clear_prompt_cache():
    """Clear the prompt cache. Useful for testing or hot-reloading."""
    load_prompt.cache_clear()
    logger.info("Prompt cache cleared")


# Convenience functions for commonly used prompts
def get_sql_generator_prompt() -> str:
    """Get the SQL generator prompt."""
    return load_prompt("sql_generator", fallback="You are a Senior Healthcare Data Analyst specializing in FHIR databases. Generate analytical SQL queries for patient data, clinical measurements, and NCD management.")


def get_intent_router_prompt() -> str:
    """Get the intent router prompt."""
    return load_prompt("intent_router", fallback="You are an intent classifier.")


def get_followup_generator_prompt() -> str:
    """Get the follow-up questions generator prompt."""
    return load_prompt("followup_generator", fallback="You are a helpful assistant that suggests follow-up questions.")


def get_data_analyst_prompt() -> str:
    """Get the data analyst response prompt."""
    return load_prompt("data_analyst", fallback="You are a helpful data analyst.")


def get_rag_synthesis_prompt() -> str:
    """Get the RAG synthesis prompt."""
    return load_prompt("rag_synthesis", fallback="You are a helpful assistant. Answer based on the provided context.")


def get_chart_generator_prompt() -> str:
    """Get the chart generation rules prompt."""
    return load_prompt("chart_generator", fallback="Generate chart JSON when data is suitable for visualization.")


def get_query_planner_prompt() -> str:
    """Get the query planner prompt."""
    return load_prompt("query_planner", fallback="You are a SQL Query Planner.")


def get_reflection_critique_prompt() -> str:
    """Get the reflection/critique prompt."""
    return load_prompt("reflection_critique", fallback="You are a Senior SQL Expert and Security Auditor.")


def get_query_rewriter_prompt() -> str:
    """Get the query rewriter prompt."""
    return load_prompt("query_rewriter", fallback="You are a query rewriter.")


def get_base_system_prompt() -> str:
    """Get the base system prompt."""
    return load_prompt("base_system", fallback="You are a helpful AI assistant.")


def get_database_generator_prompt() -> str:
    """Get the database system prompt generator template."""
    return load_prompt("database_generator", fallback="You are a SQL expert for database queries.")


def get_file_generator_prompt() -> str:
    """Get the file/CSV system prompt generator template."""
    return load_prompt("file_generator", fallback="You are a data analyst for file-based data.")


def get_sql_generator_rules_only() -> str:
    """
    Return the SQL generator prompt WITHOUT the FHIR-rules preamble.

    Used when the assembled system prompt already injects FHIR rules as a
    standalone section — avoids ~2KB of duplicated identifier guidance.

    Strips everything up to and including the `## CRITICAL: FHIR Healthcare
    Schema Rules` block; keeps from the generic `## Rules` heading onward.
    """
    full = get_sql_generator_prompt()
    marker = "## Rules"
    idx = full.find(marker)
    if idx < 0:
        return full
    return "# SQL Generation Rules\n\n" + full[idx:]


def get_generic_sql_generator_prompt() -> str:
    """
    Return a schema-agnostic SQL generation prompt for non-clinical agents.

    No FHIR rules, no healthcare table examples, no M&E patterns. Used when
    selected_columns has zero `*_gold` clinical tables (admin / operational
    agents). Keeps generic best-practices: cast types, NO LIMIT by default,
    GREATEST/LEAST, JOIN strategy, exact column names.
    """
    return """\
# SQL Generation Rules (generic)

You generate analytical SQL against the relational database described in the
`# DATA DICTIONARY & SCHEMA` section. You MUST follow these rules.

## Output
1. Return ONLY the SQL query — no explanations, no markdown fences.
2. Use lowercase SQL keywords.
3. Do NOT add `LIMIT` unless the user explicitly asks for top-N / first-N.

## Schema discipline
4. Use ONLY tables and columns that appear in `# DATA DICTIONARY & SCHEMA`.
   Never invent, never guess, never paraphrase column names.
5. Before writing SQL, scan the schema and confirm each column lives on the
   exact table you put it on. If a column appears in only one table, query
   that table.
6. If a question cannot be answered from the provided schema, return:
   `SELECT 'Insufficient data for the requested question' AS error`.

## Data types
7. If a date column is `VARCHAR`, cast before date arithmetic:
   `CAST(col AS TIMESTAMP)` or `col::TIMESTAMP`.
   Example: `DATE_TRUNC('month', CAST(created_at AS TIMESTAMP))`.
8. PostgreSQL `ROUND(value, decimals)` requires `NUMERIC`. Cast first:
   `ROUND(AVG(col)::numeric, 2)`.
9. Some boolean-like flags are stored as VARCHAR (`'true'` / `'false'`).
   Compare with `IS DISTINCT FROM 'true'`, not `= false`.

## Aggregation
10. `COUNT(DISTINCT entity_id)` for unique-entity counts (prevents join
    fan-out double-counts).
11. Filter NULL values from aggregates when zeros aren't meaningful
    (e.g. `WHERE height IS NOT NULL AND height > 0`).
12. For row-wise min/max ACROSS columns, use `GREATEST(c1, c2, c3)` /
    `LEAST(...)` — NOT `MAX()` / `MIN()`.
13. Every non-aggregated column in `SELECT` must appear in `GROUP BY`.

## Joins
14. Use explicit `INNER JOIN` / `LEFT JOIN`, never comma joins.
15. Use `INNER JOIN` when both sides must match; `LEFT JOIN` when the LEFT
    side defines the population to preserve.
16. Apply soft-delete filters on EVERY joined table:
    - `patient_tracker_gold.is_deleted` is **BOOLEAN** — use `is_deleted = false`.
    - `bp_log_gold.is_src_deleted`, `encounter_gold.is_src_deleted` are **VARCHAR** — use `IS DISTINCT FROM 'true'`.
    - Admin tables (`health_facility_admin_gold`, `district_admin_gold`) use BOOLEAN `is_deleted = false`.
17. When joining via a column with a type mismatch (VARCHAR ↔ BIGINT), cast
    on the side that needs it: `CAST(a.col AS BIGINT) = b.col`.

## Domain rules (from agent definition)
- Follow every rule in `# DOMAIN RULES & GUARDRAILS` above as binding.
- Follow `# PRIORITY METRICS` when choosing aggregations.
- Match the patterns demonstrated in `# SAMPLE QUESTIONS THIS AGENT SHOULD
  HANDLE` for any semantically similar question.

## Output format
Return only the SQL statement, no surrounding prose.
"""



def get_reasoning_generator_prompt() -> str:
    """Get the reasoning and example questions generator template."""
    return load_prompt("reasoning_generator", fallback="Generate reasoning and example questions for the data schema.")

def get_duckdb_sql_rules_prompt() -> str:
    """Get the DuckDB-specific SQL rules prompt."""
    return load_prompt("duckdb_sql_rules", fallback="Follow standard SQL best practices for DuckDB.")

def get_sql_correction_prompt() -> str:
    """Get the SQL correction/error fixing prompt."""
    return load_prompt("sql_correction", fallback="""You are a SQL debugging expert. Your task is to fix SQL syntax errors.

Given the original query and the error message, provide a corrected SQL query.

Rules:
1. Only fix the specific error mentioned
2. Preserve the original intent of the query
3. Return ONLY the corrected SQL, no explanations
4. If the error cannot be fixed, return the original query with a comment explaining why
""")


def get_fhir_rules_prompt() -> str:
    """Get the FHIR identifier rules prompt for healthcare schemas."""
    return load_prompt("fhir_rules", fallback="Follow FHIR data model conventions for patient identifiers.")


def get_me_reporting_prompt() -> str:
    """Get the M&E (Monitoring & Evaluation) reporting patterns prompt.
    
    Contains facility hierarchy CTEs, program assignments, and geographic
    breakdown patterns for healthcare M&E dashboards.
    """
    return load_prompt("me_reporting", fallback="")
