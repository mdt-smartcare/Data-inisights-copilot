"""
Prompt Builder — Dynamic, schema-aware prompt construction.

Replaces static prompt strings with dynamically assembled prompts
that inject only relevant schema context, query plan constraints,
data dictionary rules, and few-shot examples.

This is Stage 2 of the two-stage pipeline:
QueryPlan → Constrained Prompt → SQL
"""
from typing import Optional, List

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class PromptBuilder:
    """
    Assembles schema-aware, constraint-based prompts for SQL generation.
    
    Replaces static prompt templates with dynamically constructed prompts
    tailored to each query's specific schema context and requirements.
    
    Usage:
        builder = PromptBuilder()
        prompt = builder.build(
            question="How many active patients?",
            schema_context="TABLE: patient_tracker ...",
            query_plan_context="QUERY PLAN: ...",
            data_dictionary_context="DEFAULT FILTERS: ...",
            few_shot_examples=["Q: ... SQL: ..."],
            dialect="postgresql"
        )
    """
    
    def build(
        self,
        question: str,
        schema_context: str,
        query_plan_context: str = "",
        data_dictionary_context: str = "",
        system_prompt_rules: str = "",
        few_shot_examples: Optional[List[str]] = None,
        dialect: str = "postgresql",
        sample_data: str = ""
    ) -> str:
        """
        Assemble a complete SQL generation prompt.
        
        Args:
            question: User's natural language question
            schema_context: FK-annotated schema from SchemaGraph
            query_plan_context: Structured plan from QueryPlanner
            data_dictionary_context: Default filters & business definitions
            system_prompt_rules: Domain rules from active system prompt
            few_shot_examples: Query-type-aligned example pairs
            dialect: SQL dialect ("postgresql" or "duckdb")
            sample_data: Sample data rows for context
            
        Returns:
            Complete prompt string for LLM invocation
        """
        sections = []
        
        # 1. Role and Dialect
        sections.append(self._build_role_section(dialect))
        
        # 2. Domain rules from system prompt (if any)
        if system_prompt_rules:
            sections.append(system_prompt_rules)
        
        # 3. Schema context (FK-annotated)
        sections.append(self._build_schema_section(schema_context))
        
        # 4. Sample data (if available)
        if sample_data:
            sections.append(f"SAMPLE DATA:\n{sample_data}")
        
        # 5. Data dictionary context (default filters, business definitions)
        if data_dictionary_context:
            sections.append(data_dictionary_context)
        
        # 6. Query plan (structured decomposition)
        if query_plan_context:
            sections.append(query_plan_context)
        
        # 7. Few-shot examples (query-type aligned)
        if few_shot_examples:
            sections.append(self._build_examples_section(few_shot_examples))
        
        # 8. Hard constraints
        sections.append(self._build_constraints_section(dialect))
        
        # 9. Question and output instruction
        sections.append(self._build_question_section(question))
        
        prompt = "\n\n".join(sections)
        
        logger.info(
            f"PromptBuilder: assembled {len(prompt)} chars "
            f"({dialect}, plan={'yes' if query_plan_context else 'no'}, "
            f"examples={len(few_shot_examples) if few_shot_examples else 0})"
        )
        
        return prompt
    
    def build_for_file_query(
        self,
        question: str,
        schema_context: str,
        sample_data: str = "",
        query_plan_context: str = "",
        data_dictionary_context: str = ""
    ) -> str:
        """
        Build a prompt specifically for DuckDB file queries.
        
        DuckDB uses standard SQL but has some syntax differences.
        """
        return self.build(
            question=question,
            schema_context=schema_context,
            query_plan_context=query_plan_context,
            data_dictionary_context=data_dictionary_context,
            sample_data=sample_data,
            dialect="duckdb"
        )
    
    # =========================================================================
    # Section Builders
    # =========================================================================
    
    def _build_role_section(self, dialect: str) -> str:
        """Build the role/system section of the prompt."""
        if dialect == "duckdb":
            return (
                "You are a DuckDB SQL expert. Generate ONLY a SQL query to answer the question.\n"
                "DuckDB uses standard SQL syntax with some extensions.\n"
                "Use ILIKE for case-insensitive string comparisons."
            )
        else:
            return (
                "You are a PostgreSQL expert. Generate ONLY a SQL query to answer the question.\n"
                "Use PostgreSQL syntax and functions."
            )
    
    def _build_schema_section(self, schema_context: str) -> str:
        """Build the schema context section."""
        return f"DATABASE SCHEMA (use ONLY these tables and columns):\n{schema_context}"
    
    def _build_examples_section(self, examples: List[str]) -> str:
        """Build the few-shot examples section."""
        return "RELEVANT SQL EXAMPLES:\n" + "\n\n".join(examples)
    
    def _build_constraints_section(self, dialect: str) -> str:
        """Build the hard constraints section with DuckDB-specific rules."""
        constraints = [
            "STRICT RULES:",
            "1. Use ONLY the exact column names shown in the schema above",
            "2. Use ONLY the exact table names shown in the schema above",
            "3. Study the sample rows to understand data values and formats",
            "4. Use the FOREIGN KEY RELATIONSHIPS shown above for JOINs",
            "5. Follow the RECOMMENDED JOIN PATHS exactly as specified",
            "6. Apply all MANDATORY DEFAULT FILTERS unless the user explicitly asks otherwise",
            "7. Use proper date filtering with appropriate date functions",
            "8. For aggregation queries, include all non-aggregated columns in GROUP BY",
            "9. If the QUERY PLAN is provided, follow its structure closely",
            "10. Do NOT invent tables or columns that are not in the schema",
        ]
        
        if dialect == "duckdb":
            constraints.extend([
                "",
                "CRITICAL DUCKDB SQL RULES (MUST FOLLOW):",
                "",
                "11. WINDOW FUNCTIONS IN WHERE/GROUP BY - USE CTE PATTERN:",
                "    WRONG: WHERE LAG(col) OVER (...) IS NOT NULL",
                "    WRONG: GROUP BY SUM(CASE WHEN LAG(col) OVER (...) ...)",
                "    CORRECT:",
                "    WITH computed AS (",
                "        SELECT *, LAG(col) OVER (...) AS prev_col",
                "        FROM table",
                "    )",
                "    SELECT * FROM computed WHERE prev_col IS NOT NULL",
                "",
                "12. AGGREGATES IN WHERE - USE SUBQUERY/CTE:",
                "    WRONG: WHERE col > AVG(col) OR WHERE STDDEV(col) > 0",
                "    CORRECT:",
                "    WITH stats AS (SELECT AVG(col) AS avg_val FROM table)",
                "    SELECT * FROM table, stats WHERE col > stats.avg_val",
                "",
                "13. DATE DIFFERENCE:",
                "    WRONG: DATEDIFF(date1, date2)",
                "    CORRECT: DATEDIFF('day', date1, date2) -- 3 arguments required",
                "    ALSO OK: CAST(date2 AS DATE) - CAST(date1 AS DATE)",
                "",
                "14. DATE SUBTRACTION:",
                "    WRONG: DATE_SUB(date, INTERVAL 90 DAY)",
                "    CORRECT: CAST(date AS DATE) - INTERVAL '90 days'",
                "",
                "15. FIRST/LAST VALUE COMPARISON - ALWAYS USE CTE:",
                "    WITH ranked AS (",
                "        SELECT *,",
                "            ROW_NUMBER() OVER (PARTITION BY id ORDER BY date ASC) AS first_rank,",
                "            ROW_NUMBER() OVER (PARTITION BY id ORDER BY date DESC) AS last_rank",
                "        FROM table",
                "    )",
                "    SELECT f.*, l.col AS last_col",
                "    FROM ranked f",
                "    JOIN ranked l ON f.id = l.id",
                "    WHERE f.first_rank = 1 AND l.last_rank = 1",
                "",
                "16. CONSECUTIVE STREAK DETECTION - USE ROW_NUMBER DIFFERENCE:",
                "    WITH ranked AS (",
                "        SELECT *,",
                "            ROW_NUMBER() OVER (PARTITION BY id ORDER BY date) -",
                "            ROW_NUMBER() OVER (PARTITION BY id, category ORDER BY date) AS streak_group",
                "        FROM table",
                "    )",
                "    SELECT id, category, COUNT(*) AS streak_length",
                "    FROM ranked",
                "    GROUP BY id, category, streak_group",
                "",
                "17. Use ILIKE for case-insensitive string comparisons",
                "18. Boolean columns may be stored as strings: use = 'true' or = 'false'",
            ])
        elif dialect == "postgresql":
            constraints.extend([
                "11. Use PostgreSQL syntax (e.g., ILIKE for case-insensitive, ::date for casting)",
                "12. For boolean columns, compare with = true or = false",
            ])
        
        constraints.extend([
            "",
            "SPECIAL QUERY PATTERNS:",
            "- LOOKUP QUERIES: Return ALL relevant columns for the entity",
            "- AGGREGATION BY ENTITY: Filter first, then aggregate",
            "- CARE CASCADE / FUNNEL: Use COUNT with CASE WHEN for sequential stages",
            "- COMPARISON: Use appropriate GROUP BY with aggregation",
        ])
        
        return "\n".join(constraints)

    
    def _build_question_section(self, question: str) -> str:
        """Build the question and output instruction section."""
        return (
            f"QUESTION: {question}\n\n"
            "Return ONLY the SQL query. No markdown, no explanation, no comments.\n\n"
            "SQL Query:"
        )
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def build_fix_prompt(
        self,
        question: str,
        previous_sql: str,
        error_or_critique: str,
        schema_context: str,
        dialect: str = "postgresql"
    ) -> str:
        """
        Build a prompt for SQL correction/fixing.
        
        Used in the validation feedback loop when a query fails.
        """
        return (
            f"The previous SQL query was invalid. Fix it based on the critique.\n\n"
            f"DATABASE SCHEMA:\n{schema_context}\n\n"
            f"CRITIQUE/ERROR:\n{error_or_critique}\n\n"
            f"ORIGINAL QUESTION: {question}\n\n"
            f"PREVIOUS SQL:\n{previous_sql}\n\n"
            f"STRICT RULES:\n"
            f"1. Use ONLY tables and columns from the schema above\n"
            f"2. Follow the FOREIGN KEY RELATIONSHIPS for JOINs\n"
            f"3. Address every issue mentioned in the critique\n\n"
            f"Return ONLY the corrected SQL query."
        )
    
    def build_response_format_prompt(
        self,
        question: str,
        sql_query: str,
        result: str
    ) -> str:
        """
        Build a prompt for formatting SQL results into natural language + chart.
        
        This is a pass-through for the existing format_response logic,
        kept separate from SQL generation prompting.
        """
        return (
            f"QUESTION: {question}\n\n"
            f"SQL QUERY: {sql_query}\n\n"
            f"RESULT:\n{result}\n\n"
            "Format this result as a clear, natural language response."
        )
