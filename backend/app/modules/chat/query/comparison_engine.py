"""
Comparison Engine — Auto-generates follow-up comparison queries.

After the primary SQL answer, this engine generates 2-3 comparison questions
with SQL queries, executes them, and synthesizes cross-validated insights.

Inspired by Data Literacy 2.0's `generate_comparison_questions_new` pipeline.
"""
import asyncio
import json
import re
from typing import Optional, List, Dict, Any

from app.core.utils.logging import get_logger
from app.core.prompts import load_prompt

logger = get_logger(__name__)

# Maximum comparison questions to generate
MAX_COMPARISONS = 3

# Fallback prompt if template file not found
_FALLBACK_PROMPT = "Generate 3 SQL comparison questions for cross-validation."

# Common column typos: wrong → correct
_COLUMN_TYPO_CORRECTIONS = {
    r'\bynd\b': 'ymd',           # ynd → ymd (date partition column)
    r'\bpatient_idx\b': 'patient_id',
    r'\bres_idx\b': 'res_id',
    r'\bencounter_idx\b': 'encounter_id',
    r'\bcreated_att\b': 'created_at',
    r'\bupdated_att\b': 'updated_at',
}

# Pattern to fix birth_date calculations on patient_tracker_gold
# patient_tracker_gold has 'age' column directly, not birth_date
_BIRTH_DATE_AGE_PATTERN = re.compile(
    r"EXTRACT\s*\(\s*YEAR\s+FROM\s+AGE\s*\(\s*CURRENT_DATE\s*,\s*pt\.birth_date\s*\)\s*\)",
    re.IGNORECASE
)


def _fix_common_typos(sql: str) -> str:
    """Fix common LLM-generated column name typos."""
    fixed_sql = sql
    for pattern, replacement in _COLUMN_TYPO_CORRECTIONS.items():
        fixed_sql = re.sub(pattern, replacement, fixed_sql, flags=re.IGNORECASE)
    return fixed_sql


# Allowed type tokens following PostgreSQL `::`. Captures the type token and
# an optional `(prec[, scale])` suffix, plus the optional `double precision`
# two-word form. Bounded explicitly so trailing SQL tokens are never slurped.
_PG_CAST_TYPE_RE = re.compile(
    r"::\s*(double\s+precision|[A-Za-z_]\w*)(\s*\([^)]*\))?",
    re.IGNORECASE,
)


def _find_lhs_start(sql: str, cast_pos: int) -> int:
    """Walk backwards from a `::` position to find the start of the LHS expr.

    Handles three shapes:
    - identifier or dotted identifier: `col`, `t.col`
    - function call: `COUNT(*)`, `SUM(x) OVER ()`
    - parenthesised expr: `(a + b)`

    Returns the index where the LHS begins.
    """
    i = cast_pos - 1
    # Skip whitespace immediately before ::
    while i >= 0 and sql[i].isspace():
        i -= 1
    if i < 0:
        return cast_pos

    # If LHS ends with ')', walk back through balanced parens. Repeat to also
    # absorb a function-name token or chained `fn() OVER ()` constructs.
    while i >= 0 and sql[i] == ")":
        depth = 1
        j = i - 1
        while j >= 0 and depth > 0:
            if sql[j] == ")":
                depth += 1
            elif sql[j] == "(":
                depth -= 1
            j -= 1
        if depth != 0:
            return cast_pos  # unbalanced — bail
        # j is now one before the matching '('. Three sub-cases:
        # 1. identifier char abutting '(': function call like COUNT(...)
        # 2. whitespace + window keyword (OVER/FILTER): chained window expr
        # 3. whitespace + anything else: grouping parens — stop at '('
        k = j
        if k >= 0 and (sql[k].isalnum() or sql[k] == "_"):
            while k >= 0 and (sql[k].isalnum() or sql[k] == "_"):
                k -= 1
            i = k
            while i >= 0 and sql[i].isspace():
                i -= 1
        elif k >= 0 and sql[k].isspace():
            # Check for window keyword between '(' and previous token
            m = k
            while m >= 0 and sql[m].isspace():
                m -= 1
            word_end = m + 1
            while m >= 0 and (sql[m].isalnum() or sql[m] == "_"):
                m -= 1
            word = sql[m + 1:word_end].upper()
            if word in {"OVER", "FILTER", "WITHIN"}:
                i = m
                while i >= 0 and sql[i].isspace():
                    i -= 1
            else:
                return j + 1  # grouping parens
        else:
            return j + 1  # punctuation before '(' — grouping
    # If LHS is a plain identifier (possibly dotted), walk back through word
    # chars and dots.
    while i >= 0 and (sql[i].isalnum() or sql[i] in "_."):
        i -= 1
    return i + 1


# VARCHAR flag columns in SPICE Africa Trino/Iceberg that store 'true'/'false' strings,
# not SQL BOOLEAN. The LLM often generates `= true` (boolean literal) which causes
# TYPE_MISMATCH: varchar = boolean. We rewrite to `= 'true'` before execution.
_VARCHAR_FLAG_COLS = {
    # patient_tracker_gold — confirmed VARCHAR by Trino TYPE_MISMATCH errors
    "is_htn_diagnosis",
    "is_diabetes_diagnosis",
    "is_prescribed",
    "is_before_htn_diagnosis",
    "is_old_record",
    "is_regular_smoker",
    "is_patient_referred",
    # encounter_gold
    "is_latest_encounter",
}


def _fix_varchar_flag_columns(sql: str) -> str:
    """Rewrite boolean literals to string literals for known VARCHAR flag columns.

    In the SPICE Africa Iceberg schema, several `is_*` columns are stored as
    VARCHAR('true'/'false') rather than BOOLEAN. The LLM frequently generates
    `col = true` (boolean literal), causing `varchar = boolean` TYPE_MISMATCH.
    This pass converts them to `col = 'true'`/`col = 'false'` (varchar literal).

    `is_deleted` is intentionally excluded — it IS BOOLEAN in patient_tracker_gold.
    """
    fixed = sql
    for col in _VARCHAR_FLAG_COLS:
        # col = true  →  col = 'true'
        fixed = re.sub(
            rf'(\b{col}\s*=\s*)true\b',
            rf"\g<1>'true'",
            fixed,
            flags=re.IGNORECASE,
        )
        # col = false  →  col = 'false'
        fixed = re.sub(
            rf'(\b{col}\s*=\s*)false\b',
            rf"\g<1>'false'",
            fixed,
            flags=re.IGNORECASE,
        )
    return fixed


def _strip_for_trino(sql: str) -> str:
    """Strip Trino-incompatible artefacts: trailing ';', PostgreSQL '::' casts,
    and boolean literals on known-VARCHAR flag columns.

    Trino's parser rejects a trailing semicolon when the statement is the only
    statement in the request, and it does not understand the PostgreSQL
    `expr::type` cast shorthand. We convert those to `CAST(expr AS type)`.
    """
    fixed = sql
    # Repeat to absorb nested casts (e.g. (x::int)::varchar).
    for _ in range(4):
        m = _PG_CAST_TYPE_RE.search(fixed)
        if not m:
            break
        cast_pos = m.start()
        lhs_start = _find_lhs_start(fixed, cast_pos)
        lhs = fixed[lhs_start:cast_pos].strip()
        type_name = m.group(1).upper()
        if m.group(2):
            type_name += m.group(2)
        if not lhs:
            # Couldn't recover an LHS — drop just the `::type` to avoid a
            # parser error on the cast operator itself. Better than a crash.
            fixed = fixed[:cast_pos] + fixed[m.end():]
            continue
        fixed = fixed[:lhs_start] + f"CAST({lhs} AS {type_name})" + fixed[m.end():]
    # Trino uses DOUBLE/DECIMAL, not NUMERIC (PostgreSQL type)
    import re as _re
    fixed = _re.sub(r'\bAS\s+NUMERIC\b', 'AS DOUBLE', fixed, flags=_re.IGNORECASE)
    # Rewrite boolean literals for VARCHAR flag columns
    fixed = _fix_varchar_flag_columns(fixed)
    return fixed.rstrip().rstrip(";").rstrip()


def _fix_birth_date_to_age(sql: str) -> str:
    """
    Fix LLM mistakes where it tries to calculate age from birth_date on patient_tracker_gold.
    patient_tracker_gold has a direct 'age' column, not birth_date.
    """
    # Replace EXTRACT(YEAR FROM AGE(CURRENT_DATE, pt.birth_date)) with pt.age
    fixed_sql = _BIRTH_DATE_AGE_PATTERN.sub("pt.age", sql)
    
    # Also fix direct references to pt.birth_date (e.g., in WHEN clauses)
    # Replace "pt.birth_date IS NULL" with "pt.age IS NULL"
    fixed_sql = re.sub(
        r'\bpt\.birth_date\b',
        'pt.age',
        fixed_sql,
        flags=re.IGNORECASE
    )
    
    return fixed_sql


def _get_comparison_prompt() -> str:
    """Load the comparison generator prompt template."""
    return load_prompt("comparison_generator", fallback=_FALLBACK_PROMPT)


def _column_types_to_annotation(column_types: Dict[str, Dict[str, str]], dialect: str) -> str:
    """Compact column-type block appended to schema_context for comparison generator.

    Tells the LLM the exact verified type for each column so it never writes
    boolean = 'true' or varchar = false.
    """
    if not column_types:
        return ""
    cast_fn = "TRY_CAST" if dialect in ("trino", "duckdb") else "CAST"
    lines = ["", "## VERIFIED COLUMN TYPES (use exactly as shown)", ""]
    for table in sorted(column_types):
        cols = column_types[table]
        if not cols:
            continue
        lines.append(f"### {table}")
        for col in sorted(cols):
            t = cols[col].lower()
            if t == "boolean":
                hint = f"BOOLEAN — use `{col} = true` or `{col} = false` (never quotes)"
            elif t in ("varchar", "text", "character varying", "char", "string"):
                col_l = col.lower()
                if "deleted" in col_l or col_l.startswith("is_"):
                    hint = f"VARCHAR — use `{col} IS DISTINCT FROM 'true'`"
                elif any(kw in col_l for kw in ("date", "_on", "_at", "_time")):
                    hint = f"VARCHAR date — use `{cast_fn}({col} AS DATE)` for date ops"
                else:
                    hint = "VARCHAR — string comparisons only"
            elif t in ("integer", "int", "bigint", "smallint", "tinyint", "int64", "int32"):
                hint = "INTEGER — direct numeric comparison"
            elif t in ("double", "float", "real", "double precision", "float64"):
                hint = "DOUBLE — direct numeric comparison"
            else:
                hint = t.upper()
            lines.append(f"- `{col}`: {hint}")
        lines.append("")
    return "\n".join(lines)


async def generate_comparison_insights(
    original_question: str,
    original_sql: str,
    original_results: str,
    schema_context: str,
    sql_service,
    llm,
    dialect: str = "postgresql",
    column_types: Optional[Dict[str, Dict[str, str]]] = None,
) -> Optional[str]:
    """
    Generate comparison questions, execute them, and synthesize insights.
    
    Args:
        original_question: User's original question
        original_sql: SQL query that answered the original question
        original_results: Formatted results from the original query
        schema_context: Database schema context
        sql_service: SQLService instance for executing comparison queries
        llm: LLM instance for generation
        dialect: SQL dialect (postgresql, duckdb, etc.)
        
    Returns:
        Synthesized comparison insights string, or None if generation fails
    """
    try:
        # Step 1: Generate comparison questions with SQL
        # Append verified column types so the LLM knows exact boolean/varchar/double
        # types and never generates type-mismatched comparisons.
        type_annotation = _column_types_to_annotation(column_types or {}, dialect)
        enriched_schema = (schema_context + type_annotation)[:8000]

        comparison_prompt = _get_comparison_prompt()
        formatted_prompt = comparison_prompt.replace("{original_question}", original_question)
        formatted_prompt = formatted_prompt.replace("{original_sql}", original_sql)
        formatted_prompt = formatted_prompt.replace("{schema_context}", enriched_schema)
        formatted_prompt = formatted_prompt.replace("{dialect}", dialect)
        
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = [
            SystemMessage(content=formatted_prompt),
            HumanMessage(content="Generate comparison questions now.")
        ]
        
        # Use asyncio.to_thread to prevent blocking the event loop during LLM call
        response = await asyncio.to_thread(llm.invoke, messages)
        raw_output = response.content.strip()
        
        # Step 2: Parse the JSON response 
        comparison_data = _parse_comparison_response(raw_output)
        if not comparison_data or not comparison_data.get("questions"):
            logger.warning("Failed to parse comparison questions from LLM response")
            return None
        
        questions = comparison_data["questions"][:MAX_COMPARISONS]
        logger.info(f"Generated {len(questions)} comparison questions")
        
        # Step 3: Execute each comparison query
        comparison_results = []
        for i, item in enumerate(questions):
            q = item.get("question", "")
            sql = item.get("sql_query", "")
            
            if not sql:
                continue
                
            # Fix common LLM typos (e.g., ynd → ymd)
            sql = _fix_common_typos(sql)
            # Fix birth_date → age for patient_tracker_gold
            sql = _fix_birth_date_to_age(sql)
            # Trino: strip trailing ';' and rewrite PostgreSQL '::' casts
            if dialect == "trino":
                sql = _strip_for_trino(sql)
            
            try:
                # Use longer timeout for comparison queries (45s) - they can be complex
                # Use asyncio.to_thread to prevent blocking the event loop during SQL execution
                results, count = await asyncio.to_thread(
                    sql_service.execute_query, sql, timeout_seconds=45
                )
                formatted = sql_service._format_results(results, count)
                comparison_results.append({
                    "question": q,
                    "results": formatted,
                    "success": True
                })
                logger.info(f"Comparison query {i+1} succeeded: {q[:50]}...")
            except Exception as e:
                logger.warning(f"Comparison query {i+1} failed: {e}")
                comparison_results.append({
                    "question": q,
                    "results": f"Query failed: {str(e)[:100]}",
                    "success": False
                })
        
        if not any(r["success"] for r in comparison_results):
            logger.warning("All comparison queries failed")
            return None
        
        # Step 4: Synthesize insights
        insights = _format_comparison_insights(comparison_results)
        logger.info("Successfully generated comparison insights")
        return insights
        
    except Exception as e:
        logger.error(f"Comparison engine failed: {e}")
        return None


def _parse_comparison_response(raw_output: str) -> Optional[Dict[str, Any]]:
    """Parse JSON response from comparison generator LLM."""
    try:
        # Try direct JSON parse
        return json.loads(raw_output)
    except json.JSONDecodeError:
        pass
    
    # Try extracting JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', raw_output, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try finding JSON object in the text
    brace_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return None


def _format_comparison_insights(comparison_results: List[Dict[str, Any]]) -> str:
    """Format comparison results into a readable insights section."""
    parts = ["\n---\n**Additional Insights**\n"]
    
    for i, result in enumerate(comparison_results, 1):
        if result["success"]:
            parts.append(f"**{i}. {result['question']}**")
            parts.append(result["results"])
            parts.append("")
    
    return "\n".join(parts)
