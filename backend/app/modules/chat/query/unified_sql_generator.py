"""
Unified SQL Generator — Single LLM call for intent + relevance + SQL.

Collapses the multi-step LLM pipeline into a single structured output call:
- Intent classification (sql, vector, hybrid, general)
- Relevance check (is this a data question?)
- SQL generation (if applicable)

Benefits:
- Latency: 1 LLM call (~1s) vs 3-4 calls (~3-4s)
- Cost: 1 API call vs 3-4
- Consistency: All decisions made with full context

Uses Pydantic for structured output to ensure reliable parsing.
"""
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field
import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class QueryIntent(str, Enum):
    """Classification of user query intent."""
    SQL = "sql"  # Needs database query
    VECTOR = "vector"  # Needs document/RAG search
    HYBRID = "hybrid"  # Needs both SQL and vector
    GENERAL = "general"  # General conversation, no data access
    CLARIFICATION = "clarification"  # User is clarifying previous query


class UnifiedResponse(BaseModel):
    """
    Structured response from single LLM call.
    
    Combines intent, relevance, and SQL generation.
    """
    # Intent classification
    intent: Literal["sql", "vector", "hybrid", "general", "clarification"] = Field(
        description="The type of query: sql (database), vector (documents), hybrid (both), general (conversation), clarification (follow-up)"
    )
    
    # Relevance assessment
    is_relevant: bool = Field(
        description="Whether this question is relevant to the available data/schema"
    )
    
    # Reasoning (for debugging/transparency)
    reasoning: str = Field(
        description="Brief explanation of the classification decision"
    )
    
    # SQL query (if intent is sql or hybrid)
    sql_query: Optional[str] = Field(
        default=None,
        description="The SQL query to execute, or null if not applicable"
    )
    
    # Tables referenced (for validation)
    tables_used: List[str] = Field(
        default_factory=list,
        description="List of table names referenced in the SQL query"
    )
    
    # Confidence score (0-1)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the response (0-1)"
    )
    
    # Suggested clarification (if intent is clarification or low confidence)
    clarification_needed: Optional[str] = Field(
        default=None,
        description="If clarification is needed, what to ask the user"
    )
    
    # Alternative interpretations
    alternatives: List[str] = Field(
        default_factory=list,
        description="Alternative interpretations of the question (if ambiguous)"
    )


class UnifiedSQLGenerator:
    """
    Single-call LLM service for intent + relevance + SQL.
    
    Replaces the multi-step pipeline:
    - IntentClassifier.classify() → included in UnifiedResponse.intent
    - RelevanceChecker.check() → included in UnifiedResponse.is_relevant
    - SQLService.generate() → included in UnifiedResponse.sql_query
    
    Usage:
        generator = UnifiedSQLGenerator(llm, schema_context)
        response = await generator.generate(
            question="How many active patients were screened last month?",
            few_shot_examples=examples
        )
        
        if response.intent == "sql" and response.sql_query:
            execute(response.sql_query)
    """
    
    SYSTEM_PROMPT_TEMPLATE = '''You are an expert healthcare data analyst specializing in FHIR (Fast Healthcare Interoperability Resources) data. You classify questions and generate SQL queries for clinical and operational healthcare data.

## Your Task
For each user question, you must:
1. **Classify the intent**: Is this a SQL query, document search, or general conversation?
2. **Check relevance**: Is this question answerable with the available healthcare data?
3. **Generate SQL**: If it's a SQL question, write the query.

## Available Schema
{schema_context}

## Business Definitions
{business_definitions}

## Few-Shot Examples
{few_shot_examples}

## FHIR Healthcare Data Context
Common FHIR resources and their purposes:
- **Patient**: Demographics, identifiers (MRN, SSN), contact info
- **Encounter**: Clinical visits, admissions, telehealth sessions
- **Condition**: Diagnoses, problems (ICD-10 codes)
- **Observation**: Vital signs, lab results, assessments (LOINC codes)
- **MedicationRequest**: Prescriptions, medication orders (RxNorm codes)
- **Procedure**: Clinical procedures performed (CPT/SNOMED codes)
- **Appointment**: Scheduled visits, booking status
- **Practitioner**: Healthcare providers, specialties
- **Organization**: Hospitals, clinics, sites
- **DiagnosticReport**: Lab reports, imaging results

## SQL Generation Rules
1. Write DuckDB-compatible SQL (similar to PostgreSQL)
2. Use double quotes for identifiers: "patient_tracker", "encounter"
3. Apply table-specific soft-delete filters:
   - patient_tracker_gold: WHERE is_deleted = false
   - patient_gold: WHERE res_deleted_at IS NULL
   - bp_log_gold: WHERE is_src_deleted IS DISTINCT FROM 'true' (is_src_deleted is VARCHAR, not boolean!)
   - bp_log_latest_gold: No filter needed (pre-filtered to latest records)
   - glucose_log_gold: No is_deleted filter (use date filters)
   - health_facility_admin_gold: WHERE is_deleted = FALSE
4. Use appropriate aggregations (COUNT, SUM, AVG) for analytical questions
5. Limit results to reasonable sizes (default LIMIT 100 for patient lists)
6. Include ORDER BY for any "top N" or trending questions
7. For date ranges, use CURRENT_DATE, DATE_TRUNC, INTERVAL appropriately
8. Handle PHI carefully - only return necessary identifiers

## Response Format
Respond with a JSON object containing:
- intent: "sql" | "vector" | "hybrid" | "general" | "clarification"
- is_relevant: true/false
- reasoning: Brief explanation
- sql_query: The SQL query (or null)
- tables_used: List of tables in the query
- confidence: 0.0 to 1.0
- clarification_needed: What to ask if unclear (or null)
- alternatives: Alternative interpretations if ambiguous

## Examples of Intent Classification
- "How many patients were screened last month?" → sql
- "Patients by enrollment status" → sql
- "Show encounters by type" → sql
- "What does the clinical protocol say about hypertension?" → vector
- "Show patients with their care plan documents" → hybrid
- "Hello, how are you?" → general
- "No, I meant diabetic patients only" → clarification

## Example SQL Queries
Question: "How many active patients by site?"
SQL: SELECT site_id, COUNT(*) as patient_count FROM "patient_tracker" WHERE is_active = true GROUP BY 1 ORDER BY 2 DESC

Question: "Screenings completed this month"
SQL: SELECT COUNT(*) FROM "screening" WHERE status = 'completed' AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)

Question: "Top 10 conditions by frequency"
SQL: SELECT condition_code, condition_display, COUNT(*) as count FROM "condition" GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10'''

    def __init__(
        self,
        llm: BaseChatModel,
        schema_context: str,
        business_definitions: Optional[str] = None,
        dialect: str = "duckdb"
    ):
        """
        Initialize UnifiedSQLGenerator.
        
        Args:
            llm: LangChain LLM instance
            schema_context: Pre-compiled schema context from manifest
            business_definitions: Business glossary/definitions
            dialect: SQL dialect (duckdb, postgres, etc.)
        """
        self.llm = llm
        self.schema_context = schema_context
        self.business_definitions = business_definitions or ""
        self.dialect = dialect
        
        # Check if LLM supports structured output
        self._supports_structured = hasattr(llm, 'with_structured_output')
    
    async def generate(
        self,
        question: str,
        few_shot_examples: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> UnifiedResponse:
        """
        Generate unified response for a question.
        
        Args:
            question: User's question
            few_shot_examples: Formatted few-shot examples from QueryMemory
            conversation_history: Previous messages for context
            context: Additional context (user_id, tenant_id, etc.)
            
        Returns:
            UnifiedResponse with intent, relevance, and SQL
        """
        start = time.time()
        
        # Build system prompt
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            schema_context=self.schema_context,
            business_definitions=self.business_definitions,
            few_shot_examples=few_shot_examples or "No examples available."
        )
        
        # Build messages
        messages = [SystemMessage(content=system_prompt)]
        
        # Add conversation history if provided
        if conversation_history:
            for msg in conversation_history[-5:]:  # Last 5 messages
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                # Could add assistant messages too
        
        # Add current question
        messages.append(HumanMessage(content=f"Question: {question}"))
        
        try:
            if self._supports_structured:
                # Use structured output for reliable parsing
                structured_llm = self.llm.with_structured_output(UnifiedResponse)
                response = await structured_llm.ainvoke(messages)
            else:
                # Fallback to JSON parsing
                response = await self._generate_with_json_parsing(messages)
            
            elapsed_ms = (time.time() - start) * 1000
            logger.info(
                f"UnifiedSQLGenerator completed in {elapsed_ms:.0f}ms: "
                f"intent={response.intent}, relevant={response.is_relevant}, "
                f"confidence={response.confidence:.2f}"
            )
            
            return response
            
        except Exception as e:
            logger.error(f"UnifiedSQLGenerator failed: {e}")
            # Return safe fallback
            return UnifiedResponse(
                intent="general",
                is_relevant=False,
                reasoning=f"Error during generation: {str(e)}",
                sql_query=None,
                confidence=0.0
            )
    
    async def _generate_with_json_parsing(
        self,
        messages: List
    ) -> UnifiedResponse:
        """Fallback generation with manual JSON parsing."""
        import json
        import re
        
        # Add instruction to return JSON
        messages[-1].content += "\n\nRespond with valid JSON only."
        
        response = await self.llm.ainvoke(messages)
        content = response.content
        
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return UnifiedResponse(**data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse JSON response: {e}")
        
        # Fallback: try to extract intent from text
        content_lower = content.lower()
        intent = "general"
        if "select" in content_lower or "sql" in content_lower:
            intent = "sql"
        
        # Try to find SQL in the response
        sql_match = re.search(r'```sql\s*([\s\S]*?)```', content)
        sql_query = sql_match.group(1).strip() if sql_match else None
        
        return UnifiedResponse(
            intent=intent,
            is_relevant=sql_query is not None,
            reasoning="Parsed from unstructured response",
            sql_query=sql_query,
            confidence=0.5
        )
    
    def generate_sync(
        self,
        question: str,
        few_shot_examples: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> UnifiedResponse:
        """Synchronous version of generate()."""
        import asyncio
        return asyncio.run(self.generate(
            question,
            few_shot_examples,
            conversation_history
        ))


class UnifiedSQLGeneratorFactory:
    """
    Factory for creating UnifiedSQLGenerator instances.
    
    Handles caching and configuration.
    """
    
    _instances: Dict[str, UnifiedSQLGenerator] = {}
    
    @classmethod
    def get_generator(
        cls,
        agent_id: str,
        llm: BaseChatModel,
        manifest: "SchemaManifest",
        linked_tables: Optional[List[str]] = None
    ) -> UnifiedSQLGenerator:
        """
        Get or create a UnifiedSQLGenerator for an agent.
        
        Args:
            agent_id: Agent ID
            llm: LangChain LLM instance
            manifest: Pre-compiled schema manifest
            linked_tables: Tables to include in context (or all if None)
            
        Returns:
            UnifiedSQLGenerator instance
        """
        # Generate schema context from manifest
        tables = linked_tables or list(manifest.models.keys())
        schema_context = manifest.get_context_for_query(tables)
        
        # Format business definitions
        business_defs = ""
        if manifest.business_definitions:
            parts = []
            for term, defn in manifest.business_definitions.items():
                if isinstance(defn, dict):
                    desc = defn.get("description", defn.get("condition", str(defn)))
                else:
                    desc = str(defn)
                parts.append(f"- {term}: {desc}")
            business_defs = "\n".join(parts)
        
        return UnifiedSQLGenerator(
            llm=llm,
            schema_context=schema_context,
            business_definitions=business_defs
        )


class QueryTemplateEngine:
    """
    Template-based SQL generation for common FHIR healthcare query patterns.
    
    Skips LLM entirely for recognizable query patterns.
    This is the fastest path: ~5ms vs ~1000ms for LLM.
    
    Usage:
        engine = QueryTemplateEngine(manifest)
        result = engine.match("How many patients by status?")
        
        if result:
            sql = result["sql"]  # Instant SQL, no LLM needed
    """
    
    # FHIR Healthcare query patterns with SQL templates
    # NOTE: More specific patterns MUST come before generic ones!
    # CRITICAL: BP patterns with conditions MUST be checked BEFORE generic patient patterns!
    TEMPLATES = {
        # =====================================================================
        # Blood Pressure / Hypertension Patterns (MUST BE FIRST!)
        # These are more specific and must match before generic "total patients"
        # =====================================================================
        "patients_high_bp_month_year": {
            "patterns": [
                # Most specific patterns first - "bp > X/Y in month year"
                # Handle variations like "in april 2024" OR "in the month of april 2024"
                r"(?:total\s+)?(?:number\s+of\s+)?patients?\s+(?:with\s+)?(?:high\s+)?(?:bp|blood\s+pressure)\s*(?:>|greater\s+than|above|over)\s*(\d+)\s*/\s*(\d+)\s+in\s+(?:the\s+month\s+of\s+)?(\w+)\s+(\d{4})",
                r"(?:how\s+many\s+)?patients?\s+(?:with\s+)?(?:high\s+)?(?:bp|blood\s+pressure)\s*(?:>|greater\s+than|above)\s*(\d+)\s*/\s*(\d+)\s+in\s+(?:the\s+month\s+of\s+)?(\w+)\s+(\d{4})",
                r"(?:bp|blood\s+pressure)\s*(?:>|greater\s+than|above|over)\s*(\d+)\s*/\s*(\d+)\s+(?:patients?)?\s*(?:in\s+)?(?:the\s+month\s+of\s+)?(\w+)\s+(\d{4})",
                r"patients?\s+(?:whose\s+)?(?:bp|blood\s+pressure)\s*(?:is\s+)?(?:>|greater\s+than|above|over)\s*(\d+)\s*/\s*(\d+)\s+in\s+(?:the\s+month\s+of\s+)?(\w+)\s+(\d{4})",
                # Additional patterns for "during april 2024" or "for april 2024"
                r"(?:total\s+)?(?:number\s+of\s+)?patients?\s+(?:with\s+)?(?:high\s+)?(?:bp|blood\s+pressure)\s*(?:>|greater\s+than|above|over)\s*(\d+)\s*/\s*(\d+)\s+(?:during|for)\s+(\w+)\s+(\d{4})"
            ],
            "sql_template": "SELECT COUNT(DISTINCT patient_id) as high_bp_patients FROM bp_log_gold WHERE is_src_deleted IS DISTINCT FROM 'true' AND (avg_systolic > {systolic} OR avg_diastolic > {diastolic}) AND DATE_TRUNC('month', bp_taken_on) = DATE '{year}-{month_num:02d}-01'",
            "extract_table": False,
            "params": ["systolic", "diastolic", "month", "year"],
            "month_param": True
        },
        "patients_high_bp": {
            "patterns": [
                r"(?:total\s+)?(?:number\s+of\s+)?patients?\s+(?:with\s+)?(?:high\s+)?(?:bp|blood\s+pressure)\s*(?:>|greater\s+than|above|over)\s*(\d+)\s*/\s*(\d+)",
                r"(?:how\s+many\s+)?patients?\s+(?:with\s+)?(?:high\s+)?(?:bp|blood\s+pressure)\s*(?:>|greater\s+than|above)\s*(\d+)\s*/\s*(\d+)",
                r"hypertensive patients?\s*(?:>|with bp above)?\s*(\d+)\s*/\s*(\d+)"
            ],
            "sql_template": "SELECT COUNT(DISTINCT patient_id) as high_bp_patients FROM bp_log_gold WHERE is_src_deleted IS DISTINCT FROM 'true' AND (avg_systolic > {systolic} OR avg_diastolic > {diastolic})",
            "extract_table": False,
            "params": ["systolic", "diastolic"]
        },
        "uncontrolled_bp_patients": {
            "patterns": [
                r"uncontrolled (?:bp|blood pressure|hypertension) patients?",
                r"patients? with uncontrolled (?:bp|blood pressure|hypertension)",
                r"(?:how many\s+)?uncontrolled hypertensive patients?"
            ],
            "sql": "SELECT COUNT(DISTINCT patient_id) as uncontrolled_bp_patients FROM bp_log_latest_gold WHERE avg_systolic >= 140 OR avg_diastolic >= 90",
            "extract_table": False
        },
        "controlled_bp_patients": {
            "patterns": [
                r"controlled (?:bp|blood pressure|hypertension) patients?",
                r"patients? with controlled (?:bp|blood pressure|hypertension)",
                r"bp under control"
            ],
            "sql": "SELECT COUNT(DISTINCT patient_id) as controlled_bp_patients FROM bp_log_latest_gold WHERE avg_systolic < 140 AND avg_diastolic < 90",
            "extract_table": False
        },
        "bp_by_risk_level": {
            "patterns": [
                r"(?:bp|blood pressure) by risk\s*(?:level)?",
                r"(?:average|avg)\s+(?:bp|blood pressure) by risk"
            ],
            "sql": "SELECT bll.cvd_risk_level, ROUND(AVG(bll.avg_systolic)::numeric, 1) as avg_systolic, ROUND(AVG(bll.avg_diastolic)::numeric, 1) as avg_diastolic, COUNT(DISTINCT bll.patient_id) as patient_count FROM bp_log_latest_gold bll WHERE bll.cvd_risk_level IS NOT NULL GROUP BY 1 ORDER BY patient_count DESC",
            "extract_table": False
        },
        "recent_bp_readings": {
            "patterns": [
                r"recent (?:bp|blood pressure) (?:readings?|logs?|measurements?)",
                r"latest (?:bp|blood pressure) (?:readings?|logs?)"
            ],
            "sql": "SELECT patient_id, bp_taken_on, avg_systolic, avg_diastolic, avg_pulse, cvd_risk_level FROM bp_log_gold ORDER BY bp_taken_on DESC LIMIT 50",
            "extract_table": False
        },
        
        # =====================================================================
        # Generic Patient Patterns (AFTER specific patterns)
        # =====================================================================
        "total_active_patients": {
            "patterns": [
                r"total (?:number of\s+)?active patients?",
                r"(?:how many|count|number of)\s+(?:total\s+)?active patients?",
                r"active patient(?:s)?\s+(?:count|total)",
                r"all active patients?"
            ],
            "sql": 'SELECT COUNT(DISTINCT patient_id) as total_active_patients FROM patient_tracker_gold WHERE is_deleted = false',
            "extract_table": False
        },
        "total_patients": {
            "patterns": [
                r"^total (?:number of\s+)?patients?$",
                r"^(?:how many|count|number of)\s+(?:total\s+)?patients?\s*\??$",
                r"^patient(?:s)?\s+(?:count|total)$"
            ],
            "sql": 'SELECT COUNT(DISTINCT patient_id) as total_patients FROM patient_tracker_gold WHERE is_deleted = false',
            "extract_table": False
        },
        "patients_by_status": {
            "patterns": [
                r"patients? by (?:enrollment\s+)?status",
                r"patient (?:enrollment\s+)?status breakdown",
                r"how many patients? (?:are\s+)?(?:enrolled|inactive)"
            ],
            "sql": 'SELECT patient_status, COUNT(DISTINCT patient_id) as patient_count FROM patient_tracker_gold WHERE is_deleted = false GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "patients_by_site": {
            "patterns": [
                r"patients? (?:by|per|at each) site",
                r"site.?wise patient (?:count|distribution)",
                r"how many patients? at each (?:site|facility|clinic)"
            ],
            "sql": 'SELECT site_id, COUNT(DISTINCT patient_id) as patient_count FROM patient_tracker_gold WHERE is_deleted = false GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "patients_by_organization": {
            "patterns": [
                r"patients? (?:by|per) organization",
                r"organization.?wise patient"
            ],
            "sql": 'SELECT organization_id, COUNT(DISTINCT patient_id) as patient_count FROM patient_tracker_gold WHERE is_deleted = false GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "patients_by_gender": {
            "patterns": [
                r"patients? by gender",
                r"gender.?wise patient",
                r"male (?:and|vs) female patients?"
            ],
            "sql": 'SELECT gender, COUNT(DISTINCT patient_id) as patient_count FROM patient_tracker_gold WHERE is_deleted = false GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "patients_by_risk_level": {
            "patterns": [
                r"patients? by risk\s*(?:level)?",
                r"risk level breakdown",
                r"high risk patients?"
            ],
            "sql": 'SELECT risk_level, COUNT(DISTINCT patient_id) as patient_count FROM patient_tracker_gold WHERE is_deleted = false GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        
        # =====================================================================
        # Enrollment Date Patterns
        # =====================================================================
        "patients_enrolled_between": {
            "patterns": [
                r"patients? enrolled between (\d{4})(?:\s*[-–]\s*|\s+(?:and|to)\s+)(\d{4})",
                r"patients? enrolled (?:from|in) (\d{4}) (?:to|through|until|-) (\d{4})",
                r"how many patients? (?:were\s+)?enrolled (?:between|from) (\d{4})(?:\s*[-–]\s*|\s+(?:and|to)\s+)(\d{4})"
            ],
            "sql_template": "SELECT COUNT(DISTINCT patient_id) as enrolled_patients FROM patient_tracker_gold WHERE is_deleted = false AND enrollment_at >= '{start_year}-01-01' AND enrollment_at < '{end_year_plus_one}-01-01'",
            "extract_table": False,
            "params": ["start_year", "end_year"]
        },
        "patients_enrolled_in_year": {
            "patterns": [
                r"patients? enrolled in (\d{4})",
                r"how many patients? (?:were\s+)?enrolled in (\d{4})",
                r"(\d{4}) enrollment(?:s)?",
                r"enrollment(?:s)? in (\d{4})"
            ],
            "sql_template": "SELECT COUNT(DISTINCT patient_id) as enrolled_patients FROM patient_tracker_gold WHERE is_deleted = false AND EXTRACT(YEAR FROM enrollment_at) = {year}",
            "extract_table": False,
            "params": ["year"]
        },
        "enrollment_by_year": {
            "patterns": [
                r"enrollment(?:s)? by year",
                r"yearly enrollment(?:s)?",
                r"annual enrollment (?:count|breakdown|trend)"
            ],
            "sql": "SELECT EXTRACT(YEAR FROM enrollment_at)::INTEGER as year, COUNT(DISTINCT patient_id) as enrolled_patients FROM patient_tracker_gold WHERE is_deleted = false AND enrollment_at IS NOT NULL GROUP BY 1 ORDER BY 1",
            "extract_table": False
        },
        "enrollment_by_month": {
            "patterns": [
                r"enrollment(?:s)? by month",
                r"monthly enrollment(?:s)?",
                r"enrollment (?:count|breakdown|trend) by month"
            ],
            "sql": "SELECT DATE_TRUNC('month', enrollment_at) as month, COUNT(DISTINCT patient_id) as enrolled_patients FROM patient_tracker_gold WHERE is_deleted = false AND enrollment_at IS NOT NULL GROUP BY 1 ORDER BY 1",
            "extract_table": False
        },
        "recent_enrollments": {
            "patterns": [
                r"recent enrollment(?:s)?",
                r"latest enrollment(?:s)?",
                r"new(?:ly)? enrolled patients?"
            ],
            "sql": "SELECT patient_id, enrollment_at, gender, risk_level, patient_status FROM patient_tracker_gold WHERE is_deleted = false AND enrollment_at IS NOT NULL ORDER BY enrollment_at DESC LIMIT 50",
            "extract_table": False
        },
        
        # =====================================================================
        # Screening & Assessment Patterns
        # =====================================================================
        "screenings_by_type": {
            "patterns": [
                r"screenings? by type",
                r"screening types? breakdown",
                r"how many (?:of each\s+)?screening type"
            ],
            "sql": 'SELECT screening_type, COUNT(*) as screening_count FROM "screening" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "screenings_by_status": {
            "patterns": [
                r"screenings? by status",
                r"screening status breakdown",
                r"completed vs pending screenings?"
            ],
            "sql": 'SELECT status, COUNT(*) as screening_count FROM "screening" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "screenings_this_month": {
            "patterns": [
                r"screenings? this month",
                r"monthly screening count",
                r"how many screenings? (?:were\s+)?(?:done|completed) this month"
            ],
            "sql": "SELECT COUNT(*) as screening_count FROM \"screening\" WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)",
            "extract_table": False
        },
        
        # =====================================================================
        # Encounter Patterns
        # =====================================================================
        "encounters_by_type": {
            "patterns": [
                r"encounters? by type",
                r"encounter types? breakdown",
                r"visit types? distribution"
            ],
            "sql": 'SELECT encounter_type, COUNT(*) as encounter_count FROM "encounter" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "encounters_by_status": {
            "patterns": [
                r"encounters? by status",
                r"encounter status breakdown"
            ],
            "sql": 'SELECT status, COUNT(*) as encounter_count FROM "encounter" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "recent_encounters": {
            "patterns": [
                r"recent encounters?",
                r"latest encounters?",
                r"last (\d+) encounters?"
            ],
            "sql": 'SELECT * FROM "encounter" ORDER BY encounter_date DESC LIMIT 20',
            "extract_table": False
        },
        
        # =====================================================================
        # Condition/Diagnosis Patterns
        # =====================================================================
        "conditions_by_code": {
            "patterns": [
                r"conditions? by (?:icd\s*)?code",
                r"diagnos(?:is|es) breakdown",
                r"most common conditions?",
                r"top conditions?"
            ],
            "sql": 'SELECT condition_code, condition_display, COUNT(*) as condition_count FROM "condition" GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20',
            "extract_table": False
        },
        "conditions_by_category": {
            "patterns": [
                r"conditions? by category",
                r"diagnosis categories?"
            ],
            "sql": 'SELECT category, COUNT(*) as condition_count FROM "condition" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        
        # =====================================================================
        # Medication Patterns
        # =====================================================================
        "medications_by_type": {
            "patterns": [
                r"medications? by type",
                r"prescription types?",
                r"most prescribed medications?"
            ],
            "sql": 'SELECT medication_code, medication_display, COUNT(*) as prescription_count FROM "medication_request" GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20',
            "extract_table": False
        },
        "active_medications": {
            "patterns": [
                r"active medications?",
                r"current prescriptions?"
            ],
            "sql": "SELECT medication_code, medication_display, COUNT(*) as count FROM \"medication_request\" WHERE status = 'active' GROUP BY 1, 2 ORDER BY 3 DESC",
            "extract_table": False
        },
        
        # =====================================================================
        # Observation/Vital Signs Patterns
        # =====================================================================
        "observations_by_type": {
            "patterns": [
                r"observations? by type",
                r"vital signs? breakdown",
                r"lab results? by type"
            ],
            "sql": 'SELECT observation_code, observation_display, COUNT(*) as observation_count FROM "observation" GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20',
            "extract_table": False
        },
        "recent_vitals": {
            "patterns": [
                r"recent vitals?",
                r"latest vital signs?",
                r"recent observations?"
            ],
            "sql": 'SELECT * FROM "observation" ORDER BY effective_date DESC LIMIT 50',
            "extract_table": False
        },
        
        # =====================================================================
        # Appointment Patterns
        # =====================================================================
        "appointments_by_status": {
            "patterns": [
                r"appointments? by status",
                r"appointment status breakdown",
                r"scheduled vs completed appointments?"
            ],
            "sql": 'SELECT status, COUNT(*) as appointment_count FROM "appointment" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        "upcoming_appointments": {
            "patterns": [
                r"upcoming appointments?",
                r"scheduled appointments?",
                r"future appointments?"
            ],
            "sql": "SELECT * FROM \"appointment\" WHERE start_time > CURRENT_TIMESTAMP AND status = 'booked' ORDER BY start_time LIMIT 50",
            "extract_table": False
        },
        
        # =====================================================================
        # Practitioner/Provider Patterns
        # =====================================================================
        "practitioners_by_specialty": {
            "patterns": [
                r"practitioners? by specialty",
                r"providers? by specialty",
                r"doctors? by specialty"
            ],
            "sql": 'SELECT specialty, COUNT(*) as practitioner_count FROM "practitioner" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": False
        },
        
        # =====================================================================
        # Generic Patterns (fallback)
        # =====================================================================
        "top_n": {
            "patterns": [
                r"top (\d+) (\w+)",
                r"(\d+) (?:highest|most) (\w+)"
            ],
            "sql": 'SELECT * FROM "{table}" ORDER BY {order_field} DESC LIMIT {n}',
            "extract_n": True,
            "extract_table": True
        },
        "latest": {
            "patterns": [
                r"latest (\w+)",
                r"most recent (\w+)",
                r"newest (\w+)"
            ],
            "sql": 'SELECT * FROM "{table}" ORDER BY created_at DESC LIMIT 10',
            "extract_table": True
        },
        "list_all": {
            "patterns": [
                r"list (?:all\s+)?(\w+)",
                r"show (?:all\s+)?(\w+)",
                r"get (?:all\s+)?(\w+)"
            ],
            "sql": 'SELECT * FROM "{table}" LIMIT 100',
            "extract_table": True
        },
        
        # =====================================================================
        # M&E Blood Pressure Screening Patterns
        # =====================================================================
        "bp_screening_count_daterange": {
            "patterns": [
                r"(?:how many\s+)?individual(?:s)?\s+screened\s+(?:for\s+)?(?:blood\s+pressure|bp)\s+(?:from|since)\s+(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)\s+(\d{4})",
                r"(?:how many\s+)?(?:people|patients?|individual(?:s)?)\s+(?:have\s+been\s+)?screened\s+(?:for\s+)?(?:blood\s+pressure|bp)\s+(?:from|since)\s+(\d{4})",
                r"bp\s+screening(?:s)?\s+(?:count|total)\s+(?:from|since)\s+(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)\s+(\d{4})"
            ],
            "sql_template": "SELECT COUNT(DISTINCT patient_id) AS individuals_screened_bp FROM bp_log_gold WHERE TRY_CAST(bp_taken_on AS DATE) >= DATE '{year}-01-01' AND TRY_CAST(bp_taken_on AS DATE) <= CURRENT_DATE AND is_src_deleted IS DISTINCT FROM 'true'",
            "params": ["year"],
            "extract_table": False
        },
        "bp_screening_elevated": {
            "patterns": [
                r"(?:how many\s+)?individual(?:s)?\s+(?:with\s+)?elevated\s+(?:blood\s+pressure|bp)",
                r"(?:how many\s+)?screened\s+(?:for\s+)?(?:blood\s+pressure|bp)\s+with\s+elevated",
                r"elevated\s+(?:blood\s+pressure|bp)\s+count"
            ],
            "sql": "SELECT COUNT(DISTINCT patient_id) AS elevated_bp_count FROM bp_log_gold WHERE (avg_systolic >= 140 OR avg_diastolic >= 90) AND is_src_deleted IS DISTINCT FROM 'true'",
            "extract_table": False
        },
        "bp_screening_proportion_elevated": {
            "patterns": [
                r"(?:what\s+)?proportion\s+(?:of\s+)?individual(?:s)?\s+(?:screened\s+)?(?:for\s+)?(?:blood\s+pressure|bp)\s+with\s+elevated",
                r"percentage\s+(?:of\s+)?(?:people|patients?)\s+with\s+elevated\s+(?:blood\s+pressure|bp)",
                r"(?:what\s+)?(?:proportion|percentage)\s+(?:with\s+)?elevated\s+(?:blood\s+pressure|bp)"
            ],
            "sql": "SELECT ROUND(100.0 * COUNT(DISTINCT CASE WHEN avg_systolic >= 140 OR avg_diastolic >= 90 THEN patient_id END) / NULLIF(COUNT(DISTINCT patient_id), 0), 2) AS elevated_bp_proportion FROM bp_log_gold WHERE is_src_deleted IS DISTINCT FROM 'true'",
            "extract_table": False
        },
        "glucose_screening_count_daterange": {
            "patterns": [
                r"(?:how many\s+)?individual(?:s)?\s+screened\s+(?:for\s+)?(?:glucose|blood\s+glucose|bg)\s+(?:from|since)\s+(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)\s+(\d{4})",
                r"(?:how many\s+)?(?:people|patients?|individual(?:s)?)\s+(?:have\s+been\s+)?screened\s+(?:for\s+)?(?:glucose|blood\s+glucose|bg)\s+(?:from|since)\s+(\d{4})",
                r"(?:glucose|bg)\s+screening(?:s)?\s+(?:count|total)\s+(?:from|since)\s+(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep|sept|october|oct|november|nov|december|dec)\s+(\d{4})"
            ],
            "sql_template": "SELECT COUNT(DISTINCT patient_id) AS individuals_screened_glucose FROM glucose_log_gold WHERE TRY_CAST(bg_taken_on AS DATE) >= DATE '{year}-01-01' AND TRY_CAST(bg_taken_on AS DATE) <= CURRENT_DATE",
            "params": ["year"],
            "extract_table": False
        },
        "htn_followup_3months": {
            "patterns": [
                r"(?:how many\s+)?hypertensive\s+patients?\s+(?:with|had)\s+(?:a\s+)?(?:bp\s+)?follow[- ]?up\s+(?:in\s+)?(?:the\s+)?last\s+3\s+months",
                r"htn\s+patients?\s+(?:with|had)\s+(?:bp\s+)?follow[- ]?up\s+(?:last|in)\s+3\s+months",
                r"hypertensive\s+patients?\s+(?:who\s+)?had\s+(?:a\s+)?follow[- ]?up\s+(?:in\s+)?3\s+months"
            ],
            "sql": "SELECT COUNT(DISTINCT pt.patient_id) AS htn_with_followup FROM patient_tracker_gold pt INNER JOIN bp_log_gold bp ON pt.patient_id = bp.patient_id WHERE pt.is_deleted = FALSE AND pt.is_htn_diagnosis = TRUE AND CAST(bp.bp_taken_on AS DATE) >= CURRENT_DATE - INTERVAL '3 months' AND bp.is_src_deleted IS DISTINCT FROM 'true'",
            "extract_table": False
        },
        "htn_followup_percentage_3months": {
            "patterns": [
                r"(?:what\s+)?(?:is\s+)?(?:the\s+)?(?:percentage|proportion|rate)\s+(?:of\s+)?hypertensive\s+patients?\s+(?:who\s+)?(?:had|with)\s+(?:a\s+)?follow[- ]?up\s+(?:in\s+)?(?:the\s+)?(?:last\s+)?3\s+months",
                r"(?:what\s+)?(?:percentage|proportion)\s+(?:of\s+)?htn\s+patients?\s+(?:had|with)\s+follow[- ]?up",
                r"htn\s+follow[- ]?up\s+(?:rate|percentage|proportion)"
            ],
            "sql": "WITH htn_total AS (SELECT COUNT(DISTINCT patient_id) AS total FROM patient_tracker_gold WHERE is_deleted = FALSE AND is_htn_diagnosis = TRUE), htn_with_fu AS (SELECT COUNT(DISTINCT pt.patient_id) AS with_followup FROM patient_tracker_gold pt INNER JOIN bp_log_gold bp ON pt.patient_id = bp.patient_id WHERE pt.is_deleted = FALSE AND pt.is_htn_diagnosis = TRUE AND CAST(bp.bp_taken_on AS DATE) >= CURRENT_DATE - INTERVAL '3 months' AND bp.is_src_deleted IS DISTINCT FROM 'true') SELECT htn_with_fu.with_followup AS htn_with_followup, htn_total.total AS total_htn_patients, ROUND(100.0 * htn_with_fu.with_followup / NULLIF(htn_total.total, 0), 2) AS followup_percentage FROM htn_total, htn_with_fu",
            "extract_table": False
        },
        "dm_glucose_3months": {
            "patterns": [
                r"(?:how many\s+)?diabetes\s+patients?\s+with\s+(?:documented\s+)?(?:blood\s+)?glucose\s+(?:in\s+)?(?:the\s+)?last\s+3\s+months",
                r"dm\s+patients?\s+(?:with\s+)?glucose\s+(?:reading(?:s)?|measurement(?:s)?)\s+(?:last|in)\s+3\s+months"
            ],
            "sql": "SELECT COUNT(DISTINCT pt.patient_id) AS dm_with_glucose FROM patient_tracker_gold pt INNER JOIN glucose_log_gold gl ON pt.patient_id = gl.patient_id WHERE pt.is_deleted = FALSE AND pt.is_diabetes_diagnosis = TRUE AND TRY_CAST(gl.bg_taken_on AS DATE) >= CURRENT_DATE - INTERVAL '3 months'",
            "extract_table": False
        },
        "dm_hba1c_3months": {
            "patterns": [
                r"(?:how many\s+)?diabetes\s+patients?\s+with\s+(?:documented\s+|a\s+)?hba1c\s+(?:in\s+)?(?:the\s+)?last\s+3\s+months",
                r"dm\s+patients?\s+(?:with\s+)?hba1c\s+(?:last|in)\s+3\s+months"
            ],
            "sql": "SELECT COUNT(DISTINCT pt.patient_id) AS dm_with_hba1c FROM patient_tracker_gold pt INNER JOIN glucose_log_gold gl ON pt.patient_id = gl.patient_id WHERE pt.is_deleted = FALSE AND pt.is_diabetes_diagnosis = TRUE AND gl.hba1c IS NOT NULL AND TRY_CAST(gl.bg_taken_on AS DATE) >= CURRENT_DATE - INTERVAL '3 months'",
            "extract_table": False
        },
        "htn_control_rate": {
            "patterns": [
                r"(?:what\s+is\s+)?(?:the\s+)?(?:number\s+and\s+)?proportion\s+(?:of\s+)?patients?\s+with\s+controlled\s+hypertension",
                r"htn\s+control\s+rate",
                r"controlled\s+hypertension\s+(?:rate|proportion|percentage)"
            ],
            "sql": "WITH htn_patients AS (SELECT DISTINCT pt.patient_id FROM patient_tracker_gold pt INNER JOIN bp_log_latest_gold bl ON pt.patient_id = bl.patient_id WHERE pt.is_deleted = FALSE AND pt.is_htn_diagnosis = TRUE AND TRY_CAST(bl.bp_taken_on AS DATE) >= CURRENT_DATE - INTERVAL '3 months') SELECT COUNT(DISTINCT CASE WHEN bl.avg_systolic < 140 AND bl.avg_diastolic < 90 THEN bl.patient_id END) AS controlled_count, COUNT(DISTINCT bl.patient_id) AS total_htn_with_reading, ROUND(100.0 * COUNT(DISTINCT CASE WHEN bl.avg_systolic < 140 AND bl.avg_diastolic < 90 THEN bl.patient_id END) / NULLIF(COUNT(DISTINCT bl.patient_id), 0), 2) AS control_rate FROM bp_log_latest_gold bl WHERE bl.patient_id IN (SELECT patient_id FROM htn_patients)",
            "extract_table": False
        },
        "enrolled_by_county": {
            "patterns": [
                r"(?:how\s+are\s+)?enrolled\s+patients?\s+distributed\s+by\s+county",
                r"patient\s+distribution\s+by\s+county",
                r"enrollment\s+by\s+county"
            ],
            "sql": "WITH facilities AS (SELECT hf.id AS facility_id, CAST(hf.fhir_id AS BIGINT) AS organization_id, dis.name AS county_name FROM health_facility_admin_gold hf LEFT JOIN district_admin_gold dis ON hf.district_id = dis.id WHERE hf.is_deleted = FALSE) SELECT f.county_name, COUNT(DISTINCT pt.patient_id) AS enrolled_patients FROM patient_tracker_gold pt LEFT JOIN facilities f ON f.organization_id = pt.site_id WHERE pt.is_deleted = FALSE AND (pt.is_htn_diagnosis = TRUE OR pt.is_diabetes_diagnosis = TRUE) GROUP BY f.county_name ORDER BY enrolled_patients DESC",
            "extract_table": False
        },
        
        # =====================================================================
        # Generic Count Patterns (MUST be at the end - fallback only)
        # =====================================================================
        "count_total": {
            "patterns": [
                r"how many (\w+)",
                r"count (\w+)",
                r"total (\w+)",
                r"number of (\w+)"
            ],
            "sql": 'SELECT COUNT(*) as count FROM "{table}"',
            "extract_table": True
        },
        "count_by_field": {
            "patterns": [
                r"how many (\w+) by (\w+)",
                r"count (\w+) grouped by (\w+)",
                r"(\w+) breakdown by (\w+)",
                r"(\w+) distribution by (\w+)"
            ],
            "sql": 'SELECT "{field}", COUNT(*) as count FROM "{table}" GROUP BY 1 ORDER BY 2 DESC',
            "extract_table": True,
            "extract_field": True
        }
    }
    
    def __init__(self, manifest: "SchemaManifest"):
        """
        Initialize QueryTemplateEngine.
        
        Args:
            manifest: Schema manifest for table/column resolution
        """
        self.manifest = manifest
        
        # Build table name synonyms for matching
        self._table_patterns = {}
        for model_name in manifest.models:
            # Add model name and its parts
            patterns = [model_name.lower()]
            patterns.extend(model_name.lower().split("_"))
            
            # Add synonyms from manifest
            model = manifest.models[model_name]
            for syn in model.synonyms:
                patterns.append(syn.lower())
            
            self._table_patterns[model_name] = patterns
    
    # Month name to number mapping
    MONTH_MAP = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12
    }
    
    def match(self, question: str) -> Optional[Dict[str, Any]]:
        """
        Try to match question to a template.
        
        Args:
            question: User's question
            
        Returns:
            Dict with sql, tables, template_name, or None if no match
        """
        import re
        
        question_lower = question.lower()
        
        for template_name, template in self.TEMPLATES.items():
            for pattern in template["patterns"]:
                match = re.search(pattern, question_lower)
                if match:
                    # Extract captured groups
                    groups = match.groups()
                    
                    # Handle parameterized templates (sql_template with params)
                    if "sql_template" in template:
                        params = template.get("params", [])
                        if len(groups) >= len(params):
                            # Build substitution dict
                            subs = {}
                            for i, param_name in enumerate(params):
                                subs[param_name] = groups[i]
                            
                            # Handle special case: end_year_plus_one for date ranges
                            if "end_year" in subs and "end_year_plus_one" in template["sql_template"]:
                                try:
                                    end_year = int(subs["end_year"])
                                    subs["end_year_plus_one"] = str(end_year + 1)
                                except ValueError:
                                    continue  # Skip if year is invalid
                            
                            # Handle month name to number conversion
                            if template.get("month_param") and "month" in subs:
                                month_name = subs["month"].lower()
                                month_num = self.MONTH_MAP.get(month_name)
                                if month_num is None:
                                    continue  # Skip if month is invalid
                                subs["month_num"] = month_num
                            
                            sql = template["sql_template"].format(**subs)
                            
                            # Determine tables used based on template
                            tables = []
                            if "bp_log" in sql:
                                tables = ["bp_log_gold"]
                            elif "patient_tracker" in sql:
                                tables = ["patient_tracker_gold"]
                            
                            logger.info(
                                f"QueryTemplateEngine matched parameterized: template={template_name}, "
                                f"params={subs}"
                            )
                            
                            return {
                                "sql": sql,
                                "tables": tables,
                                "template_name": template_name,
                                "confidence": 0.9
                            }
                        continue  # Not enough groups for params
                    
                    # Try to resolve table name
                    table_name = None
                    if template.get("extract_table") and groups:
                        entity = groups[0] if not template.get("extract_n") else groups[1]
                        table_name = self._resolve_table(entity)
                    
                    if not table_name and template.get("extract_table"):
                        continue  # Need table but couldn't find it
                    
                    # Build SQL from template
                    sql = template["sql"]
                    
                    if table_name:
                        sql = sql.replace("{table}", table_name)
                    
                    if template.get("extract_field") and len(groups) > 1:
                        field = self._resolve_column(table_name, groups[1])
                        if field:
                            sql = sql.replace("{field}", field)
                    
                    if template.get("extract_n") and groups:
                        n = int(groups[0])
                        sql = sql.replace("{n}", str(n))
                    
                    # Default order field for top_n
                    if "{order_field}" in sql:
                        order_field = self._get_default_order_field(table_name)
                        sql = sql.replace("{order_field}", order_field)
                    
                    logger.info(
                        f"QueryTemplateEngine matched: template={template_name}, "
                        f"table={table_name}"
                    )
                    
                    return {
                        "sql": sql,
                        "tables": [table_name] if table_name else [],
                        "template_name": template_name,
                        "confidence": 0.9  # High confidence for template matches
                    }
        
        return None
    
    def _resolve_table(self, entity: str) -> Optional[str]:
        """Resolve an entity mention to a table name."""
        entity_lower = entity.lower()
        
        # Singularize common patterns
        if entity_lower.endswith("s"):
            singular = entity_lower[:-1]
        else:
            singular = entity_lower
        
        for table_name, patterns in self._table_patterns.items():
            if entity_lower in patterns or singular in patterns:
                return table_name
        
        # Partial match
        for table_name, patterns in self._table_patterns.items():
            for pattern in patterns:
                if entity_lower in pattern or pattern in entity_lower:
                    return table_name
        
        return None
    
    def _resolve_column(
        self,
        table_name: Optional[str],
        field_mention: str
    ) -> Optional[str]:
        """Resolve a field mention to a column name."""
        if not table_name:
            return None
        
        model = self.manifest.get_model(table_name)
        if not model:
            return None
        
        field_lower = field_mention.lower()
        
        for col in model.columns:
            if col.name.lower() == field_lower:
                return col.name
            if field_lower in col.name.lower():
                return col.name
        
        return field_mention  # Use as-is
    
    def _get_default_order_field(self, table_name: Optional[str]) -> str:
        """Get default ordering field for a table."""
        if not table_name:
            return "1"  # Order by first column
        
        model = self.manifest.get_model(table_name)
        if not model:
            return "1"
        
        # Common ordering fields
        for preferred in ["created_at", "updated_at", "id", "date", "timestamp"]:
            for col in model.columns:
                if preferred in col.name.lower():
                    return col.name
        
        return "1"
