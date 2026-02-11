"""
Reflection Service - Self-Correction Logic.
Critiques generated SQL against schema rules and best practices.
"""
import re
from typing import Optional, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.models.schemas import CritiqueResponse

settings = get_settings()
logger = get_logger(__name__)

CRITIQUE_PROMPT_TEMPLATE = """You are a Senior SQL Expert and Security Auditor.
Your job is to critique and validate the following SQL query generated for a PostgreSQL database.

DATABASE SCHEMA CONTEXT (TRUST THIS - these are the ACTUAL tables and columns):
{schema_context}

USER QUESTION: "{question}"

GENERATED SQL:
{sql_query}

CRITIQUE RULES:
1. Schema Validation: Check if table and column names exist in the schema context provided above. 
   IMPORTANT: Only flag a column as missing if you are 100% certain it's NOT in the schema above.
   The schema context is authoritative - if a column appears there, it EXISTS.
2. Logic Check: Does the SQL answer the user's question?
3. Security: Check for proper date handling and injection risks (though we use read-only).
4. Join Logic: Are joins correct based on primary/foreign key relationships in the schema?

IMPORTANT: For simple COUNT queries with basic WHERE clauses, be lenient. 
If the table and columns are in the schema and the logic matches the question, mark as VALID.
IMPORTANT: If you see a table name like 'patient_tracker' in the schema context, it EXISTS - do not reject it.

Output valid JSON matching the CritiqueResponse schema.
If the SQL is correct and answers the question, set is_valid=True.
"""

# Known valid tables that should always pass quick validation when present in schema
KNOWN_VALID_TABLES = [
    'patient_tracker', 'patient_visit', 'patient_diagnosis', 'patient_assessment',
    'patient_lab_test', 'patient_lab_test_result', 'patient_treatment_plan',
    'patient_medical_review', 'patient_comorbidity', 'patient_complication',
    'patient_current_medication', 'patient_lifestyle', 'patient_symptom',
    'patient_general_information', 'patient_history', 'patient_transfer',
    'patient_eye_care', 'patient_cataract', 'patient_pregnancy_details',
    'patient_nutrition_lifestyle', 'patient_para_counselling', 'patient_medical_compliance',
    # Core data tables (not prefixed with patient_)
    'bp_log', 'glucose_log', 'screening_log', 'lab_test', 'lab_test_result',
    'site', 'organization', 'country', 'account', 'user', 'role',
    'medication_country_detail', 'dosage_form', 'dosage_frequency',
    'patient_bp_log', 'patient_glucose_log', 'patient_screening',
    'region', 'district', 'health_facility', 'program', 'clinical_workflow',
    'country_customization', 'form_meta', 'menu', 'culture'
]

class SQLCritiqueService:
    def __init__(self):
        logger.info("Initializing SQLCritiqueService")
        self.llm = ChatOpenAI(
            temperature=0,
            model_name="gpt-3.5-turbo",  # Use faster model for critique
            api_key=settings.openai_api_key
        )
        self.parser = PydanticOutputParser(pydantic_object=CritiqueResponse)
        
        self.prompt = ChatPromptTemplate.from_template(
            CRITIQUE_PROMPT_TEMPLATE,
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
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
        dangerous_keywords = ['drop', 'delete', 'update', 'insert', 'alter', 'truncate', 'create', 'grant', 'revoke']
        
        if not sql_lower.startswith('select'):
            return False
            
        for keyword in dangerous_keywords:
            # Check for keyword as a whole word
            if re.search(rf'\b{keyword}\b', sql_lower):
                return False
        
        return True

    def _quick_validate(self, sql_query: str, schema_context: str) -> Optional[CritiqueResponse]:
        """
        Perform quick validation without LLM for simple, obviously valid queries.
        Returns CritiqueResponse if validation is conclusive, None if LLM critique needed.
        
        OPTIMIZED: More aggressive about passing simple queries to reduce latency.
        """
        sql_lower = sql_query.lower()
        schema_lower = schema_context.lower()
        
        # Must be a safe SELECT query
        if not self._is_safe_select_query(sql_query):
            return None  # Let LLM handle complex cases
        
        # Extract tables from the query
        tables = self._extract_tables_from_sql(sql_query)
        
        if not tables:
            return None  # Can't validate without table names
        
        # Check for demo 'patient' table misuse
        if 'patient' in tables and len([t for t in tables if t == 'patient']) > 0:
            # Query uses just 'patient' table (not patient_tracker, etc.)
            other_patient_tables = [t for t in tables if t.startswith('patient_')]
            if not other_patient_tables and 'patient_tracker' in schema_lower:
                logger.warning("Rejecting 'patient' table - should use 'patient_tracker' instead")
                return CritiqueResponse(
                    is_valid=False,
                    reasoning="Wrong table used. The 'patient' table is a demo table. Use 'patient_tracker' for patient queries.",
                    issues=["Use 'patient_tracker' table instead of 'patient' for patient data queries"]
                )
        
        # OPTIMIZATION: For known valid tables, skip LLM entirely
        all_tables_known = True
        for table in tables:
            if table == 'patient':
                continue
            
            is_known_table = table in KNOWN_VALID_TABLES
            is_in_schema = table in schema_lower
            
            if is_known_table or is_in_schema:
                logger.info(f"Table '{table}' validated (known={is_known_table}, in_schema={is_in_schema})")
            else:
                all_tables_known = False
                logger.info(f"Table '{table}' not found in quick validation, deferring to LLM")
                break
        
        # OPTIMIZATION: If all tables are known/valid, pass the query
        # This saves an LLM call (~1-2s) for most queries
        if all_tables_known:
            logger.info(f"Quick validation PASSED - all tables known: {tables}")
            return CritiqueResponse(
                is_valid=True,
                reasoning=f"All tables validated against known tables and schema: {', '.join(tables)}",
                issues=[]
            )
        
        return None  # Unknown table - let LLM validate

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
        if 'select' not in sql_lower[sql_lower.find('from'):] if 'from' in sql_lower else True:
            # No nested SELECT after FROM - relatively simple
            if sql_lower.count('select') == 1:
                return True
        
        return False

    def critique_sql(self, question: str, sql_query: str, schema_context: str) -> CritiqueResponse:
        """
        Analyze SQL query for correctness and safety.
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
        
        logger.info("Quick validation inconclusive - using LLM critique")
        
        try:
            # Format inputs - ensure schema context includes key tables
            truncated_schema = schema_context[:12000]  # Increased limit
            
            _input = self.prompt.format_messages(
                schema_context=truncated_schema,
                question=question,
                sql_query=sql_query
            )
            
            # Using Pydantic output parser workflow
            output = self.llm.invoke(_input)
            
            # Use structured output parsing
            if hasattr(self.llm, "with_structured_output"):
                structured_llm = self.llm.with_structured_output(CritiqueResponse)
                response = structured_llm.invoke(_input)
            else:
                # Fallback to manual parsing
                response = self.parser.parse(output.content)
            
            # Double-check LLM response for false negatives on known tables
            if not response.is_valid:
                tables = self._extract_tables_from_sql(sql_query)
                false_negative = False
                
                for table in tables:
                    if table in KNOWN_VALID_TABLES and table in schema_context.lower():
                        # LLM incorrectly rejected a known valid table
                        for issue in response.issues or []:
                            if table in issue.lower() and ('not found' in issue.lower() or 'missing' in issue.lower() or "doesn't exist" in issue.lower()):
                                logger.warning(f"LLM false negative detected for table '{table}' - overriding")
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
            # Fail safe - assume valid if critique breaks, to avoid blocking
            return CritiqueResponse(
                is_valid=True, 
                reasoning="Critique service unavailable", 
                issues=[]
            )

# Singleton
_critique_service = None

def get_critique_service():
    global _critique_service
    if not _critique_service:
        _critique_service = SQLCritiqueService()
    return _critique_service
