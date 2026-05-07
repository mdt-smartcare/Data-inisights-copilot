"""
Structured SQL Output Parser — Parses `<thinking>` and `<query>` blocks.

Enforces a structured output format from the LLM that separates:
- <thinking>: Model's reasoning, interpretation, assumptions
- <query>: The actual SQL query

This provides:
1. Better observability (log reasoning separately)
2. Cleaner SQL extraction (no markdown cleanup needed)
3. Fine-tuning data collection (reasoning + SQL pairs)
4. Debugging support (understand why SQL was generated)
"""
import re
from typing import Optional, NamedTuple
from dataclasses import dataclass

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StructuredSQLOutput:
    """Parsed structured SQL output from LLM."""
    thinking: str  # Model's reasoning
    query: str  # SQL query
    raw_response: str  # Original LLM response
    parse_success: bool  # Whether structured parsing succeeded
    
    @property
    def sql(self) -> str:
        """Alias for query (common usage)."""
        return self.query


class StructuredOutputParser:
    """
    Parses LLM responses that follow the `<thinking>/<query>` format.
    
    Expected format:
    ```
    <thinking>
    I need to join patient_tracker with clinical_data_latest...
    Using GROUP BY for aggregation...
    </thinking>
    <query>
    SELECT p.gender, COUNT(*) as count
    FROM patient_tracker p
    JOIN clinical_data_latest c ON p.id = c.patient_id
    GROUP BY p.gender
    </query>
    ```
    
    Falls back to raw SQL extraction if structured format not found.
    """
    
    # Regex patterns for extraction
    THINKING_PATTERN = re.compile(
        r'<thinking>\s*(.*?)\s*</thinking>',
        re.DOTALL | re.IGNORECASE
    )
    QUERY_PATTERN = re.compile(
        r'<query>\s*(.*?)\s*</query>',
        re.DOTALL | re.IGNORECASE
    )
    
    # Fallback: markdown code blocks
    SQL_BLOCK_PATTERN = re.compile(
        r'```sql\s*(.*?)\s*```',
        re.DOTALL | re.IGNORECASE
    )
    CODE_BLOCK_PATTERN = re.compile(
        r'```\s*(.*?)\s*```',
        re.DOTALL
    )
    
    def parse(self, response: str) -> StructuredSQLOutput:
        """
        Parse LLM response into structured components.
        
        Args:
            response: Raw LLM response text
            
        Returns:
            StructuredSQLOutput with thinking, query, and parse status
        """
        response = response.strip()
        
        # Try structured format first
        thinking_match = self.THINKING_PATTERN.search(response)
        query_match = self.QUERY_PATTERN.search(response)
        
        if query_match:
            # Structured format found
            query = query_match.group(1).strip()
            thinking = thinking_match.group(1).strip() if thinking_match else ""
            
            logger.debug(
                f"Parsed structured output: thinking={len(thinking)} chars, query={len(query)} chars"
            )
            
            return StructuredSQLOutput(
                thinking=thinking,
                query=self._clean_sql(query),
                raw_response=response,
                parse_success=True
            )
        
        # Fallback: try to extract SQL from markdown blocks or raw text
        sql = self._extract_sql_fallback(response)
        
        if sql:
            logger.debug(f"Extracted SQL via fallback: {len(sql)} chars")
            return StructuredSQLOutput(
                thinking="",  # No thinking section found
                query=sql,
                raw_response=response,
                parse_success=False  # Structured parsing failed
            )
        
        # Last resort: assume entire response is SQL
        logger.warning("Could not parse structured output, using raw response as SQL")
        return StructuredSQLOutput(
            thinking="",
            query=self._clean_sql(response),
            raw_response=response,
            parse_success=False
        )
    
    def _extract_sql_fallback(self, response: str) -> Optional[str]:
        """Extract SQL using fallback patterns (markdown blocks, etc.)."""
        # Try SQL code block
        sql_match = self.SQL_BLOCK_PATTERN.search(response)
        if sql_match:
            return self._clean_sql(sql_match.group(1))
        
        # Try generic code block
        code_match = self.CODE_BLOCK_PATTERN.search(response)
        if code_match:
            content = code_match.group(1).strip()
            # Check if it looks like SQL
            if self._looks_like_sql(content):
                return self._clean_sql(content)
        
        # Try to find SELECT statement
        select_match = re.search(
            r'\b(SELECT\s+.+?)(?:;|\Z)',
            response,
            re.DOTALL | re.IGNORECASE
        )
        if select_match:
            return self._clean_sql(select_match.group(1))
        
        # Try WITH clause (CTE)
        with_match = re.search(
            r'\b(WITH\s+.+?)(?:;|\Z)',
            response,
            re.DOTALL | re.IGNORECASE
        )
        if with_match:
            return self._clean_sql(with_match.group(1))
        
        return None
    
    def _clean_sql(self, sql: str) -> str:
        """Clean up SQL string."""
        # Remove markdown formatting
        sql = re.sub(r'^```sql\s*', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'^```\s*', '', sql)
        sql = re.sub(r'\s*```$', '', sql)
        
        # Remove trailing semicolons (we add them when needed)
        sql = sql.strip().rstrip(';').strip()
        
        # Normalize whitespace
        sql = re.sub(r'\n{3,}', '\n\n', sql)
        
        return sql
    
    @staticmethod
    def _looks_like_sql(text: str) -> bool:
        """Check if text looks like SQL."""
        sql_keywords = [
            'SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY',
            'ORDER BY', 'WITH', 'HAVING', 'UNION', 'INSERT',
            'UPDATE', 'DELETE', 'CREATE', 'ALTER'
        ]
        text_upper = text.upper()
        return any(kw in text_upper for kw in sql_keywords)


# Prompt instructions for structured output
STRUCTURED_OUTPUT_INSTRUCTIONS = """
OUTPUT FORMAT (VERY IMPORTANT):
You MUST respond in the following format:

<thinking>
[Explain your reasoning briefly:
- How you interpreted the user's question
- Which tables and columns you chose and why
- How you applied filters and joins
- How you handled dates, aggregations, or special cases]
</thinking>

<query>
[Write a single valid SQL SELECT statement here.
No backticks, no markdown, no comments, no explanation.
Just the raw SQL query.]
</query>

Do NOT include anything outside these tags.
Do NOT include natural language outside <thinking> and <query>.
"""


def get_structured_output_instructions() -> str:
    """Get the prompt instructions for structured output format."""
    return STRUCTURED_OUTPUT_INSTRUCTIONS


# Global parser instance
_parser: Optional[StructuredOutputParser] = None


def get_structured_parser() -> StructuredOutputParser:
    """Get the global structured output parser."""
    global _parser
    if _parser is None:
        _parser = StructuredOutputParser()
    return _parser
