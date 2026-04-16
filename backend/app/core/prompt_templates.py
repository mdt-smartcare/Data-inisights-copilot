"""
SQL Generation Prompt Templates.

Phase 4: Retrieval Chain Update
===============================
Provides system prompt templates that format injected context as raw 
CREATE TABLE blocks for optimal LLM understanding.

The prompt structure:
1. System instructions with SQL rules
2. Raw CREATE TABLE blocks (schema context)
3. Few-shot examples (if available)
4. User question
"""
from typing import List, Dict, Any, Optional

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# SQL Generation System Prompt
# =============================================================================

SQL_GENERATOR_SYSTEM_PROMPT = """You are an expert SQL developer. Your task is to convert natural language questions into precise, executable SQL queries.

## STRICT RULES - FOLLOW EXACTLY
1. Generate SQL using ONLY the tables and columns provided in the schema below
2. Return ONLY valid SQL - no explanations, no markdown, no code blocks
3. NEVER invent or assume tables/columns that are not explicitly listed
4. If the question cannot be answered with the provided schema, respond with: "-- ERROR: Cannot answer with available schema"

## SQL Best Practices
- Use explicit JOIN syntax (INNER JOIN, LEFT JOIN) - never comma joins
- Include appropriate WHERE clauses for filtering
- Use proper NULL handling with COALESCE or IS NULL
- Add meaningful column aliases for clarity
- Check column data types before operations

{dialect_rules}

{business_context}

## DATABASE SCHEMA
The following CREATE TABLE statements define the ONLY tables and columns you may use:

{retrieved_ddls}

{few_shot_examples}

## FINAL REMINDER
Generate SQL using ONLY the provided schemas. Return ONLY valid SQL.
"""


# =============================================================================
# Dialect-Specific Rules
# =============================================================================

POSTGRESQL_RULES = """## PostgreSQL-Specific Rules
- Use DATE_TRUNC('month', date_col) for date truncation
- Use INTERVAL '90 days' for date arithmetic
- Window functions work in SELECT and ORDER BY, NOT in WHERE
- Use :: for type casting (e.g., column::timestamp)
- String concatenation uses || operator
- Use COALESCE for NULL handling in calculations
"""

DUCKDB_RULES = """## DuckDB-Specific Rules (CRITICAL)
1. Window functions (LAG, LEAD, ROW_NUMBER) CANNOT be used in WHERE - use CTE pattern
2. Window functions CANNOT be used in GROUP BY - use CTE pattern
3. Aggregate functions (COUNT, SUM) CANNOT be used in WHERE - use HAVING or CTE
4. Date difference: Use DATEDIFF('day', start_date, end_date) with 3 arguments
5. Use DATE_TRUNC('month', date_col) for date truncation
6. Use INTERVAL '90 days' syntax for date arithmetic
7. For consecutive streaks, use ROW_NUMBER difference technique in CTEs
8. **VARCHAR DATE COLUMNS**: If date column is VARCHAR, CAST before operations:
   - CAST(column AS TIMESTAMP) or column::TIMESTAMP
   - DATE_TRUNC('month', CAST(created_at AS TIMESTAMP))
9. **GREATEST/LEAST for row-wise min/max across columns (NOT aggregate min/max)**
10. Boolean values are TRUE/FALSE, not 1/0
"""

MYSQL_RULES = """## MySQL-Specific Rules
- Use DATE_FORMAT() instead of DATE_TRUNC()
- Use INTERVAL 30 DAY syntax (no quotes around number)
- Use CURDATE() instead of CURRENT_DATE
- Window functions require MySQL 8.0+
- String concatenation uses CONCAT() function
- Use IFNULL() or COALESCE() for null handling
"""

SQLSERVER_RULES = """## SQL Server-Specific Rules
- Use TOP N instead of LIMIT N
- Use DATETRUNC() (SQL Server 2022+) or DATEPART/DATEFROMPARTS
- Use DATEADD(day, N, date) instead of INTERVAL
- Use CAST(GETDATE() AS DATE) instead of CURRENT_DATE
- String concatenation uses + operator or CONCAT()
"""

DIALECT_RULES_MAP = {
    "postgresql": POSTGRESQL_RULES,
    "postgres": POSTGRESQL_RULES,
    "duckdb": DUCKDB_RULES,
    "mysql": MYSQL_RULES,
    "sqlserver": SQLSERVER_RULES,
    "mssql": SQLSERVER_RULES,
}


# =============================================================================
# Schema Context Formatting
# =============================================================================

def format_schema_context(ddl_blocks: str) -> str:
    """
    Format DDL blocks as schema context section.
    
    Args:
        ddl_blocks: Raw CREATE TABLE statements
    
    Returns:
        Formatted schema context section
    """
    if not ddl_blocks or not ddl_blocks.strip():
        return ""
    
    return ddl_blocks


def format_few_shot_examples(examples: List[Dict[str, Any]]) -> str:
    """
    Format few-shot examples for prompt injection.
    
    Args:
        examples: List of example dicts with question, sql, category, score
    
    Returns:
        Formatted few-shot section
    """
    if not examples:
        return ""
    
    lines = [
        "## Similar SQL Examples",
        "Use these verified patterns as reference:\n"
    ]
    
    for i, ex in enumerate(examples, 1):
        question = ex.get("question", "")
        sql = ex.get("sql", "")
        category = ex.get("category", "general")
        
        lines.append(f"### Example {i} ({category})")
        lines.append(f"**Question:** {question}")
        lines.append("**SQL:**")
        lines.append("```sql")
        lines.append(sql)
        lines.append("```")
        lines.append("")
    
    return "\n".join(lines)


def build_sql_generation_prompt(
    schema_context: str,
    dialect: str = "postgresql",
    few_shot_examples: Optional[List[Dict[str, Any]]] = None,
    additional_rules: Optional[str] = None,
    business_context: Optional[str] = None,
) -> str:
    """
    Build the complete SQL generation system prompt.
    
    This is the main entry point for constructing the LLM prompt
    with schema context formatted as raw CREATE TABLE blocks.
    
    Args:
        schema_context: DDL blocks (retrieved_ddls) from schema retriever
        dialect: Target SQL dialect
        few_shot_examples: Optional list of similar examples
        additional_rules: Optional additional SQL rules
        business_context: Optional business glossary/definitions context
    
    Returns:
        Complete system prompt string
    """
    # Get dialect-specific rules
    dialect_rules = DIALECT_RULES_MAP.get(dialect.lower(), POSTGRESQL_RULES)
    
    if additional_rules:
        dialect_rules = f"{dialect_rules}\n\n{additional_rules}"
    
    # Format schema context (raw DDLs)
    formatted_ddls = format_schema_context(schema_context)
    
    # Format few-shot examples
    formatted_examples = ""
    if few_shot_examples:
        formatted_examples = format_few_shot_examples(few_shot_examples)
    
    # Format business context
    formatted_business = ""
    if business_context:
        formatted_business = f"## BUSINESS CONTEXT\n{business_context}"
    
    # Build final prompt with dynamic injection
    prompt = SQL_GENERATOR_SYSTEM_PROMPT.format(
        dialect_rules=dialect_rules,
        retrieved_ddls=formatted_ddls,
        few_shot_examples=formatted_examples,
        business_context=formatted_business,
    )
    
    return prompt.strip()


# =============================================================================
# RAW DDL Block Templates
# =============================================================================

RAW_DDL_HEADER = """-- ============================================
-- DATABASE SCHEMA CONTEXT
-- Tables retrieved for: {query_summary}
-- ============================================
"""

RAW_DDL_PRIMARY_SECTION = """
-- PRIMARY TABLES (directly relevant to query)
"""

RAW_DDL_DEPENDENCY_SECTION = """
-- RELATED TABLES (for JOIN paths via foreign keys)
"""

RAW_DDL_RELATIONSHIPS_SECTION = """
-- FOREIGN KEY RELATIONSHIPS
"""


def format_raw_ddl_context(
    primary_tables: List[Dict[str, Any]],
    dependency_tables: List[Dict[str, Any]],
    query_summary: str = "user query",
) -> str:
    """
    Format tables as raw CREATE TABLE blocks with section headers.
    
    This produces the exact format expected by the LLM:
    - Clear section headers
    - Raw DDL statements (no excessive comments)
    - FK relationship summary
    
    Args:
        primary_tables: Tables from semantic search
            Each dict: {"table_name": str, "ddl": str, "foreign_keys": list}
        dependency_tables: Tables from FK resolution
        query_summary: Brief summary of user query
    
    Returns:
        Formatted raw DDL context string
    """
    sections = []
    
    # Header
    sections.append(RAW_DDL_HEADER.format(query_summary=query_summary[:50]))
    
    # Primary tables
    if primary_tables:
        sections.append(RAW_DDL_PRIMARY_SECTION)
        
        for table in primary_tables:
            ddl = table.get("ddl", "")
            
            # Extract just the CREATE TABLE statement
            raw_ddl = _extract_raw_ddl(ddl)
            sections.append(raw_ddl)
            sections.append("")
    
    # Dependency tables
    if dependency_tables:
        sections.append(RAW_DDL_DEPENDENCY_SECTION)
        
        for table in dependency_tables:
            ddl = table.get("ddl", "")
            raw_ddl = _extract_raw_ddl(ddl)
            sections.append(raw_ddl)
            sections.append("")
    
    # FK relationships summary
    all_tables = primary_tables + dependency_tables
    relationships = []
    
    for table in all_tables:
        table_name = table.get("table_name", "")
        foreign_keys = table.get("foreign_keys", [])
        
        for fk in foreign_keys:
            relationships.append(f"-- {table_name} -> {fk}")
    
    if relationships:
        sections.append(RAW_DDL_RELATIONSHIPS_SECTION)
        sections.extend(relationships)
        sections.append("")
    
    return "\n".join(sections)


def _extract_raw_ddl(enriched_ddl: str) -> str:
    """
    Extract raw CREATE TABLE statement from enriched DDL.
    
    Removes header comments but preserves inline column comments.
    """
    lines = enriched_ddl.split('\n')
    result_lines = []
    in_ddl = False
    
    for line in lines:
        # Start capturing at CREATE TABLE
        if line.strip().startswith('CREATE TABLE'):
            in_ddl = True
        
        if in_ddl:
            result_lines.append(line)
        
        # Stop at closing semicolon
        if in_ddl and line.strip().endswith(';'):
            break
    
    if result_lines:
        return '\n'.join(result_lines)
    
    # Fallback: return original
    return enriched_ddl


# =============================================================================
# Convenience Functions
# =============================================================================

def get_dialect_rules(dialect: str) -> str:
    """Get SQL rules for a specific dialect."""
    return DIALECT_RULES_MAP.get(dialect.lower(), POSTGRESQL_RULES)


def estimate_prompt_tokens(prompt: str) -> int:
    """Estimate token count for a prompt (rough approximation)."""
    return len(prompt) // 4
