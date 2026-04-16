"""
Comparison Engine — Auto-generates follow-up comparison queries.

After the primary SQL answer, this engine generates 2-3 comparison questions
with SQL queries, executes them, and synthesizes cross-validated insights.

Inspired by Data Literacy 2.0's `generate_comparison_questions_new` pipeline.
"""
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


def _get_comparison_prompt() -> str:
    """Load the comparison generator prompt template."""
    return load_prompt("comparison_generator", fallback=_FALLBACK_PROMPT)


async def generate_comparison_insights(
    original_question: str,
    original_sql: str,
    original_results: str,
    schema_context: str,
    sql_service,
    llm,
    dialect: str = "postgresql",
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
        comparison_prompt = _get_comparison_prompt()
        formatted_prompt = comparison_prompt.replace("{original_question}", original_question)
        formatted_prompt = formatted_prompt.replace("{original_sql}", original_sql)
        formatted_prompt = formatted_prompt.replace("{schema_context}", schema_context[:8000])
        formatted_prompt = formatted_prompt.replace("{dialect}", dialect)
        
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = [
            SystemMessage(content=formatted_prompt),
            HumanMessage(content="Generate comparison questions now.")
        ]
        
        response = llm.invoke(messages)
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
                
            # Quick syntax auto-correction for DuckDB timezone limitations
            if dialect == "duckdb":
                sql = re.sub(
                    r'CAST\s*\(\s*([a-zA-Z0-9_]+)\s+AS\s+TIMESTAMP(?:TZ)?\s*\)', 
                    r'CAST(SUBSTRING(\1, 1, 19) AS TIMESTAMP)', 
                    sql, 
                    flags=re.IGNORECASE
                )
            
            try:
                results, count = sql_service.execute_query(sql, timeout_seconds=15)
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
    parts = ["\n---\n**📊 Additional Insights**\n"]
    
    for i, result in enumerate(comparison_results, 1):
        if result["success"]:
            parts.append(f"**{i}. {result['question']}**")
            parts.append(result["results"])
            parts.append("")
    
    return "\n".join(parts)
