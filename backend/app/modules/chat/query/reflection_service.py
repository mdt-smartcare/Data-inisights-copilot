"""
Reflection Service - SQL Critique and Self-Correction.

Validates generated SQL queries against schema rules, best practices,
and security constraints. Provides feedback for self-correction.
"""
import re
from typing import Optional, List

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.core.utils.logging import get_logger
from app.core.prompts import get_reflection_critique_prompt
from .models import CritiqueResponse
from .schema_graph import SchemaGraph

logger = get_logger(__name__)


# Default critique prompt
# Load critique prompt from external template file
def _get_critique_system_prompt():
    return get_reflection_critique_prompt()


_CRITIQUE_USER_TEMPLATE = """DATABASE SCHEMA:
{schema_context}

USER QUESTION: {question}

SQL QUERY TO VALIDATE:
{sql_query}

Validate this query and respond with a CritiqueResponse JSON object."""


class ReflectionService:
    """
    SQL critique and validation service with optional LLM-based analysis.
    
    Performs multi-layer validation:
    1. Quick validation: Basic syntax and safety checks
    2. Schema validation: Table/column existence via SchemaGraph
    3. LLM critique: Deep semantic validation for complex queries
    
    Usage:
        service = ReflectionService(schema_graph, llm)
        result = service.critique(question, sql_query, schema_context)
        if not result.is_valid:
            # Use result.issues to fix the query
    """
    
    def __init__(
        self,
        schema_graph: Optional[SchemaGraph] = None,
        llm: Optional[BaseChatModel] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize ReflectionService.
        
        Args:
            schema_graph: SchemaGraph for structural validation
            llm: LLM for semantic critique (optional, used for complex cases)
            system_prompt: Custom critique prompt
        """
        self.schema_graph = schema_graph
        self.llm = llm
        
        if llm:
            self.structured_llm = llm.with_structured_output(CritiqueResponse)
            self.prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt or _get_critique_system_prompt()),
                ("user", _CRITIQUE_USER_TEMPLATE)
            ])
        else:
            self.structured_llm = None
            self.prompt = None
        
        logger.info("ReflectionService initialized")
    
    def critique(
        self,
        question: str,
        sql_query: str,
        schema_context: str,
        use_llm: bool = True
    ) -> CritiqueResponse:
        """
        Analyze SQL query for correctness and safety.
        
        Args:
            question: Original user question
            sql_query: Generated SQL query to validate
            schema_context: Schema context used for generation
            use_llm: Whether to use LLM for deep validation
            
        Returns:
            CritiqueResponse with validation result and issues
        """
        logger.info(f"Critiquing SQL for: '{question[:50]}...'")
        
        # Try quick validation first
        quick_result = self._quick_validate(sql_query, schema_context)
        if quick_result is not None:
            if quick_result.is_valid:
                logger.info("Quick validation PASSED - skipping LLM critique")
            else:
                logger.warning(f"Quick validation FAILED: {quick_result.issues}")
            return quick_result
        
        # Use LLM for deeper validation if available
        if use_llm and self.structured_llm:
            logger.info("Quick validation inconclusive - using LLM critique")
            return self._llm_critique(question, sql_query, schema_context)
        
        # Fallback: assume valid if we can't validate  further
        logger.info("No LLM available for deep validation - assuming valid")
        return CritiqueResponse(
            is_valid=True,
            reasoning="Quick validation passed, LLM validation skipped",
            issues=[]
        )
    
    def _quick_validate(
        self,
        sql_query: str,
        schema_context: str
    ) -> Optional[CritiqueResponse]:
        """
        Perform quick validation without LLM.
        
        Uses SchemaGraph (when available) for precise table/column existence checks.
        Returns None if validation is inconclusive (needs LLM).
        """
        sql_lower = sql_query.lower()
        schema_lower = schema_context.lower()
        
        # Must be a safe SELECT query
        if not self._is_safe_select_query(sql_query):
            return CritiqueResponse(
                is_valid=False,
                reasoning="Query contains potentially dangerous operations",
                issues=["Only SELECT queries are allowed. Remove any INSERT/UPDATE/DELETE/DROP operations."]
            )
        
        # Extract tables from the query
        tables = self._extract_tables_from_sql(sql_query)
        
        if not tables:
            return None  # Can't validate without table names
        
        # === SchemaGraph-based validation (preferred) ===
        if self.schema_graph:
            all_tables_valid = True
            issues = []
            for table in tables:
                if not self.schema_graph.has_table(table):
                    all_tables_valid = False
                    issues.append(f"Table '{table}' not found in database schema")
            
            if not all_tables_valid:
                return CritiqueResponse(
                    is_valid=False,
                    reasoning=f"Schema validation failed: {'; '.join(issues)}",
                    issues=issues
                )
            
            # Validate joins if multiple tables
            join_issues = self._validate_joins(sql_query, tables)
            if join_issues:
                return CritiqueResponse(
                    is_valid=False,
                    reasoning=f"Join validation issues: {'; '.join(join_issues)}",
                    issues=join_issues
                )
            
            # Validate aggregation GROUP BY completeness
            agg_issues = self._validate_aggregation(sql_query)
            if agg_issues:
                return CritiqueResponse(
                    is_valid=False,
                    reasoning=f"Aggregation issues: {'; '.join(agg_issues)}",
                    issues=agg_issues
                )
            
            logger.info(f"SchemaGraph validation PASSED for tables: {tables}")
            return CritiqueResponse(
                is_valid=True,
                reasoning=f"All tables and joins validated against SchemaGraph: {', '.join(tables)}",
                issues=[]
            )
        
        # === Fallback validation using schema context text ===
        all_tables_in_schema = True
        for table in tables:
            if table not in schema_lower:
                all_tables_in_schema = False
                break
        
        if all_tables_in_schema:
            logger.info(f"Schema text validation PASSED - all tables found: {tables}")
            return CritiqueResponse(
                is_valid=True,
                reasoning=f"All tables found in schema context: {', '.join(tables)}",
                issues=[]
            )
        
        return None  # Unknown table - let LLM validate
    
    def _llm_critique(
        self,
        question: str,
        sql_query: str,
        schema_context: str
    ) -> CritiqueResponse:
        """Use LLM for deep semantic validation."""
        try:
            truncated_schema = schema_context[:12000]  # Limit schema size
            
            chain = self.prompt | self.structured_llm
            
            response = chain.invoke({
                "schema_context": truncated_schema,
                "question": question,
                "sql_query": sql_query
            })
            
            # Double-check LLM response for false negatives
            if not response.is_valid and self.schema_graph:
                tables = self._extract_tables_from_sql(sql_query)
                false_negative = False
                
                for table in tables:
                    if self.schema_graph.has_table(table):
                        for issue in response.issues or []:
                            if table in issue.lower() and (
                                'not found' in issue.lower() or 
                                'missing' in issue.lower() or 
                                "doesn't exist" in issue.lower()
                            ):
                                logger.warning(
                                    f"LLM false negative detected for table '{table}' - overriding"
                                )
                                false_negative = True
                                break
                
                if false_negative:
                    logger.info("Overriding LLM critique - tables are valid in schema")
                    return CritiqueResponse(
                        is_valid=True,
                        reasoning="Tables validated against schema (LLM override)",
                        issues=[]
                    )
            
            if not response.is_valid:
                logger.warning(f"Critique Found Issues: {response.issues}")
            else:
                logger.info("SQL Critique Passed")
            
            return response
            
        except Exception as e:
            logger.error(f"Critique failed: {e}")
            # Fail safe - assume valid if critique breaks
            return CritiqueResponse(
                is_valid=True,
                reasoning="Critique service unavailable",
                issues=[]
            )
    
    def _extract_tables_from_sql(self, sql_query: str) -> List[str]:
        """Extract all table names from SQL query."""
        sql_lower = sql_query.lower()
        tables = []
        
        # Match FROM and JOIN clauses
        from_pattern = r'(?:from|join)\s+([a-z_][a-z0-9_]*)'
        matches = re.findall(from_pattern, sql_lower)
        tables.extend(matches)
        
        return list(set(tables))
    
    def _is_safe_select_query(self, sql_query: str) -> bool:
        """Check if query is a safe SELECT statement."""
        sql_lower = sql_query.lower().strip()
        dangerous_keywords = [
            'drop', 'delete', 'update', 'insert', 'alter', 
            'truncate', 'create', 'grant', 'revoke', 'exec'
        ]
        
        if not sql_lower.startswith('select'):
            return False
        
        for keyword in dangerous_keywords:
            # Check for keyword as a whole word
            if re.search(rf'\b{keyword}\b', sql_lower):
                return False
        
        return True
    
    def _validate_joins(self, sql_query: str, tables: List[str]) -> List[str]:
        """
        Validate JOIN conditions against SchemaGraph FK relationships.
        Returns a list of issues (empty if all joins are valid).
        """
        if not self.schema_graph or len(tables) <= 1:
            return []
        
        issues = []
        sql_lower = sql_query.lower()
        
        # Check that multi-table queries have JOIN clauses
        if len(tables) > 1 and 'join' not in sql_lower:
            # Might be using comma-separated FROM with WHERE join
            from_idx = sql_lower.find('from')
            where_idx = sql_lower.find('where') if 'where' in sql_lower else len(sql_lower)
            if from_idx >= 0 and ',' in sql_lower[from_idx:where_idx]:
                logger.info("Using implicit comma join syntax - valid but not recommended")
            else:
                issues.append("Query references multiple tables but has no JOIN clause")
        
        return issues
    
    def _validate_aggregation(self, sql_query: str) -> List[str]:
        """
        Check for common aggregation errors (e.g., missing GROUP BY).
        """
        sql_lower = sql_query.lower()
        issues = []
        
        # Check if query has aggregation functions
        agg_functions = ['count(', 'sum(', 'avg(', 'min(', 'max(']
        has_aggregation = any(agg in sql_lower for agg in agg_functions)
        
        if has_aggregation:
            # Check for non-aggregated columns in SELECT without GROUP BY
            has_group_by = 'group by' in sql_lower
            
            # Heuristic: if using aggregation with non-star select and no GROUP BY
            # and the SELECT has multiple columns, it might be missing GROUP BY
            select_end = sql_lower.find('from')
            if select_end > 0:
                select_clause = sql_lower[6:select_end].strip()
                has_non_agg_columns = False
                for part in select_clause.split(','):
                    part = part.strip()
                    if part and not any(agg in part for agg in agg_functions) and part != '*':
                        has_non_agg_columns = True
                        break
                
                if has_non_agg_columns and not has_group_by:
                    issues.append(
                        "SELECT includes non-aggregated columns alongside aggregation functions "
                        "but has no GROUP BY clause"
                    )
        
        return issues
    
    def _is_simple_query(self, sql_query: str) -> bool:
        """Check if query is simple enough to skip LLM critique."""
        sql_lower = sql_query.lower()
        
        # Simple queries: SELECT with COUNT, GROUP BY, basic WHERE
        simple_patterns = [
            r'select\s+\w+\s*,\s*count\s*\(',  # SELECT col, COUNT(
            r'select\s+count\s*\(',             # SELECT COUNT(
            r'select\s+\*\s+from',              # SELECT * FROM
            r'select\s+\w+\s*,\s*\w+\s+from',   # SELECT col1, col2 FROM
        ]
        
        for pattern in simple_patterns:
            if re.search(pattern, sql_lower):
                return True
        
        # Also consider queries without subqueries as simple
        from_idx = sql_lower.find('from')
        if from_idx >= 0:
            after_from = sql_lower[from_idx:]
            if 'select' not in after_from:
                # No nested SELECT after FROM - relatively simple
                if sql_lower.count('select') == 1:
                    return True
        
        return False
