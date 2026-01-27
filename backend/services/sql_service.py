"""
SQL service for structured database queries.
Wraps LangChain SQL agent for database interactions.
"""
from functools import lru_cache
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import re

from sqlalchemy import inspect
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from backend.config import get_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


# =============================================================================
# FIX 2: DASHBOARD KPI TEMPLATES - Exact SQL for dashboard alignment
# ORDERED BY PRIORITY - More specific patterns first!
# =============================================================================
DASHBOARD_KPI_TEMPLATES: List[Tuple[str, str, str]] = [
    # Format: (pattern, SQL query, description)
    # ORDER MATTERS - More specific patterns MUST come first!
    
    # ==========================================================================
    # PRIORITY 0: COMBINED/COMPOUND QUERIES (most specific - check FIRST!)
    # ==========================================================================
    (
        r"(critical|high).?risk.*smok|smok.*(critical|high).?risk",
        """SELECT 
            risk_category,
            COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END) as smokers,
            COUNT(DISTINCT CASE WHEN is_smoker = FALSE OR is_smoker IS NULL THEN patient_track_id END) as non_smokers,
            COUNT(DISTINCT patient_track_id) as total
        FROM v_high_risk_patients 
        WHERE workflow_status = 'NCD'
        GROUP BY risk_category
        ORDER BY CASE risk_category 
            WHEN 'Critical' THEN 1 
            WHEN 'High' THEN 2 
            WHEN 'Moderate' THEN 3 
            ELSE 4 END""",
        "high-risk patients by smoking status"
    ),
    (
        r"smok.*(critical|high).?risk|(critical|high).?risk.*who.*smok",
        """SELECT 
            COUNT(DISTINCT patient_track_id) as critical_smokers
        FROM v_high_risk_patients 
        WHERE workflow_status = 'NCD' 
        AND risk_category = 'Critical'
        AND is_smoker = TRUE""",
        "critical risk patients who are smokers"
    ),
    (
        r"risk.*categor.*smok|smok.*risk.*categor",
        """SELECT 
            risk_category,
            COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END) as smokers,
            COUNT(DISTINCT patient_track_id) as total,
            ROUND(COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END)::numeric / 
                  NULLIF(COUNT(DISTINCT patient_track_id), 0) * 100, 2) as smoking_rate_pct
        FROM v_high_risk_patients 
        WHERE workflow_status = 'NCD'
        GROUP BY risk_category
        ORDER BY CASE risk_category 
            WHEN 'Critical' THEN 1 
            WHEN 'High' THEN 2 
            WHEN 'Moderate' THEN 3 
            ELSE 4 END""",
        "smoking rate by risk category"
    ),
    
    # ==========================================================================
    # PRIORITY 1: High-Risk & Lifestyle Queries (specific but single-dimension)
    # ==========================================================================
    (
        r"high.?risk.*patient|critical.*patient|risk.*(category|stratification)",
        """SELECT risk_category, COUNT(DISTINCT patient_track_id) as count
        FROM v_high_risk_patients 
        WHERE workflow_status = 'NCD'
        GROUP BY risk_category
        ORDER BY CASE risk_category 
            WHEN 'Critical' THEN 1 
            WHEN 'High' THEN 2 
            WHEN 'Moderate' THEN 3 
            ELSE 4 END""",
        "high-risk patient distribution by category"
    ),
    (
        r"smoker|smoking.*patient",
        """SELECT 
            COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END) as smokers,
            COUNT(DISTINCT CASE WHEN is_smoker = FALSE OR is_smoker IS NULL THEN patient_track_id END) as non_smokers,
            ROUND(COUNT(DISTINCT CASE WHEN is_smoker = TRUE THEN patient_track_id END)::numeric / 
                  NULLIF(COUNT(DISTINCT patient_track_id), 0) * 100, 2) as smoking_rate_pct
        FROM v_analytics_screening_enhanced 
        WHERE workflow_status = 'NCD'""",
        "smoking status among NCD patients"
    ),
    (
        r"lifestyle.*risk|poor.*lifestyle",
        """SELECT 
            lifestyle_risk_score,
            COUNT(DISTINCT patient_track_id) as patient_count
        FROM v_analytics_screening_enhanced 
        WHERE workflow_status = 'NCD' AND lifestyle_risk_score IS NOT NULL
        GROUP BY lifestyle_risk_score
        ORDER BY lifestyle_risk_score DESC""",
        "lifestyle risk score distribution"
    ),
    (
        r"glycemic.*control|hba1c.*control",
        """SELECT 
            glycemic_control_status,
            COUNT(DISTINCT patient_track_id) as patient_count
        FROM v_analytics_enrollment_enhanced 
        WHERE patient_status = 'ENROLLED' AND workflow_status = 'NCD'
        GROUP BY glycemic_control_status
        ORDER BY CASE glycemic_control_status
            WHEN 'Very Poorly Controlled' THEN 1
            WHEN 'Poorly Controlled' THEN 2
            WHEN 'Controlled Diabetic' THEN 3
            WHEN 'Pre-Diabetic' THEN 4
            WHEN 'Normal' THEN 5
            ELSE 6 END""",
        "glycemic control status distribution"
    ),
    (
        r"abnormal.*lab|lab.*abnormal",
        """SELECT 
            CASE 
                WHEN abnormal_result_count >= 3 THEN '3+ abnormal'
                WHEN abnormal_result_count = 2 THEN '2 abnormal'
                WHEN abnormal_result_count = 1 THEN '1 abnormal'
                ELSE 'No abnormal'
            END as abnormal_category,
            COUNT(DISTINCT patient_track_id) as patient_count
        FROM v_analytics_enrollment_enhanced 
        WHERE patient_status = 'ENROLLED' AND workflow_status = 'NCD'
        GROUP BY abnormal_category
        ORDER BY abnormal_result_count DESC""",
        "patients by abnormal lab result count"
    ),
    (
        r"screener.*role|role.*screener|who.*screen",
        """SELECT 
            screener_role_name,
            COUNT(DISTINCT patient_track_id) as patients_screened
        FROM v_analytics_screening_enhanced 
        WHERE workflow_status = 'NCD' AND screener_role_name IS NOT NULL
        GROUP BY screener_role_name
        ORDER BY patients_screened DESC""",
        "screening counts by screener role"
    ),
    (
        r"shasthya kormi|chcp|medical officer",
        """SELECT 
            screener_role_name,
            COUNT(DISTINCT patient_track_id) as patients_screened,
            COUNT(DISTINCT CASE WHEN is_referred = TRUE THEN patient_track_id END) as patients_referred
        FROM v_analytics_screening_enhanced 
        WHERE workflow_status = 'NCD' AND screener_role_name IS NOT NULL
        GROUP BY screener_role_name
        ORDER BY patients_screened DESC""",
        "screening and referral by health worker role"
    ),
    (
        r"symptom|headache|dizziness|fatigue",
        """SELECT 
            COUNT(DISTINCT CASE WHEN has_headache = TRUE THEN patient_track_id END) as with_headache,
            COUNT(DISTINCT CASE WHEN has_dizziness = TRUE THEN patient_track_id END) as with_dizziness,
            COUNT(DISTINCT CASE WHEN has_fatigue = TRUE THEN patient_track_id END) as with_fatigue,
            COUNT(DISTINCT CASE WHEN has_vision_issues = TRUE THEN patient_track_id END) as with_vision_issues,
            COUNT(DISTINCT CASE WHEN has_chest_pain = TRUE THEN patient_track_id END) as with_chest_pain
        FROM v_analytics_screening_enhanced 
        WHERE workflow_status = 'NCD'""",
        "symptom prevalence among NCD patients"
    ),
    
    # ==========================================================================
    # PRIORITY 1: Prevalence & Yield KPIs (most specific - check these first!)
    # ==========================================================================
    (
        r"htn.*(prevalence|rate)|prevalence.*(htn|hypertension|bp)",
        """SELECT 
            ROUND(
                (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
                    AND referred_reason IN ('Due to Elevated BP', 'Due to Elevated BP & BG') 
                    THEN patient_track_id END)::numeric / 
                 NULLIF(COUNT(DISTINCT CASE WHEN has_bp_reading = TRUE 
                    THEN patient_track_id END), 0)) * 100, 
                2
            ) as htn_prevalence_pct
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD'""",
        "HTN prevalence rate"
    ),
    (
        r"hypertension.*(prevalence|rate)",
        """SELECT 
            ROUND(
                (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
                    AND referred_reason IN ('Due to Elevated BP', 'Due to Elevated BP & BG') 
                    THEN patient_track_id END)::numeric / 
                 NULLIF(COUNT(DISTINCT CASE WHEN has_bp_reading = TRUE 
                    THEN patient_track_id END), 0)) * 100, 
                2
            ) as htn_prevalence_pct
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD'""",
        "HTN prevalence rate"
    ),
    (
        r"dbm.*(prevalence|rate)|prevalence.*(dbm|diabetes|glucose|bg)",
        """SELECT 
            ROUND(
                (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
                    AND referred_reason IN ('Due to Elevated BG', 'Due to Elevated BP & BG') 
                    THEN patient_track_id END)::numeric / 
                 NULLIF(COUNT(DISTINCT CASE WHEN has_bg_reading = TRUE 
                    THEN patient_track_id END), 0)) * 100, 
                2
            ) as dbm_prevalence_pct
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD'""",
        "DBM prevalence rate"
    ),
    (
        r"diabetes.*(prevalence|rate)",
        """SELECT 
            ROUND(
                (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
                    AND referred_reason IN ('Due to Elevated BG', 'Due to Elevated BP & BG') 
                    THEN patient_track_id END)::numeric / 
                 NULLIF(COUNT(DISTINCT CASE WHEN has_bg_reading = TRUE 
                    THEN patient_track_id END), 0)) * 100, 
                2
            ) as dbm_prevalence_pct
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD'""",
        "DBM prevalence rate"
    ),
    (
        r"screening.*(yield|rate)",
        """SELECT 
            ROUND(
                (COUNT(DISTINCT CASE WHEN is_referred = TRUE 
                    AND referred_reason IN ('Due to Elevated BP', 'Due to Elevated BG', 'Due to Elevated BP & BG') 
                    THEN patient_track_id END)::numeric / 
                 NULLIF(COUNT(DISTINCT CASE WHEN has_bp_reading = TRUE 
                    THEN patient_track_id END), 0)) * 100, 
                2
            ) as screening_yield_pct
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD'""",
        "screening yield percentage"
    ),
    
    # ==========================================================================
    # PRIORITY 2: Referral KPIs (check before general screening)
    # ==========================================================================
    (
        r"crisis.*(referral|refer)",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_screening 
        WHERE crisis_referral_status = 'Crisis Referral'""",
        "crisis referrals"
    ),
    (
        r"referred.*(elevated|high).*(bp|blood pressure)",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD' 
        AND is_referred = TRUE 
        AND referred_reason IN ('Due to Elevated BP', 'Due to Elevated BP & BG')""",
        "patients referred due to elevated blood pressure"
    ),
    (
        r"referred.*(elevated|high).*(bg|glucose|sugar)",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD' 
        AND is_referred = TRUE 
        AND referred_reason IN ('Due to Elevated BG', 'Due to Elevated BP & BG')""",
        "patients referred due to elevated blood glucose"
    ),
    (
        r"(total|how many|count).*referred|people referred",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD' 
        AND is_referred = TRUE""",
        "total patients referred"
    ),
    
    # ==========================================================================
    # PRIORITY 3: Enrollment KPIs
    # ==========================================================================
    (
        r"enrolled.*by.*condition|breakdown.*enrolled",
        """SELECT enrolled_condition, COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_enrollment 
        WHERE patient_status = 'ENROLLED' 
        AND workflow_status = 'NCD'
        AND enrolled_condition IS NOT NULL
        GROUP BY enrolled_condition
        ORDER BY count DESC""",
        "enrollment breakdown by condition"
    ),
    (
        r"enrolled.*(hypertension|htn)",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_enrollment 
        WHERE patient_status = 'ENROLLED' 
        AND workflow_status = 'NCD'
        AND enrolled_condition = 'Hypertension'""",
        "patients enrolled with Hypertension"
    ),
    (
        r"enrolled.*(diabetes|dbm)",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_enrollment 
        WHERE patient_status = 'ENROLLED' 
        AND workflow_status = 'NCD'
        AND enrolled_condition = 'Diabetes'""",
        "patients enrolled with Diabetes"
    ),
    (
        r"enrolled.*co-?morbid",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_enrollment 
        WHERE patient_status = 'ENROLLED' 
        AND workflow_status = 'NCD'
        AND enrolled_condition = 'Co-morbid (DBM + HTN)'""",
        "patients enrolled with co-morbid conditions"
    ),
    (
        r"community.*(enrolled|enrollment)",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_enrollment 
        WHERE patient_status = 'ENROLLED' 
        AND is_screening = TRUE 
        AND workflow_status = 'NCD'""",
        "community enrolled patients"
    ),
    (
        r"(total|how many|count).*enrolled|enrolled.*ncd",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_enrollment 
        WHERE patient_status = 'ENROLLED' 
        AND workflow_status = 'NCD'""",
        "total enrolled NCD patients"
    ),
    
    # ==========================================================================
    # PRIORITY 4: Screening KPIs (most general - check last)
    # ==========================================================================
    (
        r"screened.*(bp|blood pressure)|(bp|blood pressure).*screened",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD' 
        AND has_bp_reading = TRUE""",
        "patients screened for blood pressure"
    ),
    (
        r"screened.*(bg|glucose|blood glucose)|(bg|glucose).*screened",
        """SELECT COUNT(DISTINCT patient_track_id) as count
        FROM v_analytics_screening 
        WHERE workflow_status = 'NCD' 
        AND has_bg_reading = TRUE""",
        "patients screened for blood glucose"
    ),
]


class SQLService:
    """Service for SQL database operations."""
    
    def __init__(self):
        logger.info(f"Connecting to database at {settings.database_url}")
        
        try:
            # Initialize database connection with views included
            temp_db = SQLDatabase.from_uri(settings.database_url)
            all_tables = list(temp_db.get_usable_table_names())
            
            # Include all analytics views (base + enhanced)
            analytics_views = [
                'v_analytics_screening', 
                'v_analytics_enrollment',
                'v_analytics_screening_enhanced',
                'v_analytics_enrollment_enhanced',
                'v_high_risk_patients',
                'v_user_roles',
                'v_patient_lifestyle',
                'v_patient_symptoms',
                'v_patient_lab_history'
            ]
            for view in analytics_views:
                if view not in all_tables:
                    all_tables.append(view)
            
            self.db = SQLDatabase.from_uri(
                settings.database_url,
                include_tables=all_tables,
                view_support=True
            )
            logger.info("Database connection established with view support")
            
            self._cache_schema()
            
            self.llm_fast = ChatOpenAI(
                temperature=0,
                model_name="gpt-3.5-turbo",
                api_key=settings.openai_api_key,
                verbose=True
            )
            
            self.llm = ChatOpenAI(
                temperature=settings.openai_temperature,
                model_name=settings.openai_model,
                api_key=settings.openai_api_key,
                verbose=True
            )
            
            self.sql_agent = create_sql_agent(
                llm=self.llm,
                db=self.db,
                agent_type="openai-tools",
                verbose=True,
                handle_parsing_errors=True,
                max_iterations=8,
                include_tables=self.relevant_tables
            )
            logger.info(f"SQL agent initialized successfully with {len(self.relevant_tables)} cached tables")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQL service: {e}", exc_info=True)
            raise
    
    def _cache_schema(self):
        try:
            all_tables = self.db.get_usable_table_names()
            
            self.relevant_tables = [
                table for table in all_tables 
                if any(keyword in table.lower() for keyword in [
                    'patient', 'visit', 'tracker', 'diagnosis', 'medication',
                    'lab_test', 'assessment', 'vital', 'bp_log', 'glucose',
                    'screening', 'enrollment', 'medical', 'notes',
                    'v_analytics'
                ])
            ]
            
            base_schema = self.db.get_table_info(table_names=self.relevant_tables)
            
            schema_enhancements = """
==============================================================================
CRITICAL: USE ANALYTICS VIEWS FOR DASHBOARD KPIs (MANDATORY)
==============================================================================

**RULE: For ANY statistics about screening, referrals, or enrollment, you MUST use:**
- `v_analytics_screening` - For screening & referral KPIs
- `v_analytics_enrollment` - For enrollment KPIs

**NEVER query raw `patienttracker` or `screeninglog` tables for aggregate statistics.**

==============================================================================
"""
            
            self.cached_schema = base_schema + schema_enhancements
            
            logger.info(f"Cached schema for {len(self.relevant_tables)} relevant tables out of {len(all_tables)} total")
            logger.info(f"Relevant tables: {', '.join(self.relevant_tables[:10])}...")
            
        except Exception as e:
            logger.warning(f"Could not cache schema: {e}. Will use default behavior.")
            self.relevant_tables = None
            self.cached_schema = None
    
    def _get_relevant_schema(self, question: str) -> str:
        try:
            question_lower = question.lower()
            
            relevant_tables = [
                table for table in (self.relevant_tables or [])
                if table.lower() in question_lower
            ]
            
            keyword_to_tables = {
                'glucose': ['glucose_log', 'patient_tracker', 'patient'],
                'bp': ['bp_log', 'patient_tracker', 'patient'],
                'blood pressure': ['bp_log', 'patient_tracker', 'patient'],
                'hypertension': ['patient_diagnosis', 'bp_log', 'patient_tracker', 'patient'],
                'diabetes': ['patient_diagnosis', 'glucose_log', 'patient_tracker', 'patient'],
                'smoker': ['patient', 'patient_tracker'],
                'smoking': ['patient', 'patient_tracker'],
                'visit': ['patient_visit', 'patient_tracker', 'patient'],
                'diagnosis': ['patient_diagnosis', 'patient_tracker', 'patient'],
                'medication': ['current_medication', 'patient_tracker', 'patient'],
                'lab': ['lab_test', 'lab_test_result', 'patient_tracker', 'patient'],
            }
            
            for keyword, tables in keyword_to_tables.items():
                if keyword in question_lower:
                    for table in tables:
                        if table in self.relevant_tables and table not in relevant_tables:
                            relevant_tables.append(table)
            
            if not relevant_tables:
                logger.info("No specific tables matched in question. Using full cached schema.")
                return self.cached_schema
            
            relevant_tables = list(dict.fromkeys(relevant_tables))
            logger.info(f"📋 Selected relevant tables for query: {', '.join(relevant_tables)}")
            
            base_schema = self.db.get_table_info(table_names=relevant_tables)
            
            schema_enhancements = """
==============================================================================
CRITICAL: CORRECT JOIN PATTERNS
==============================================================================

patient.id → patient_tracker.patient_id → other tables
patient_tracker.id → glucose_log.patient_track_id
patient_tracker.id → bp_log.patient_track_id
patient_tracker.id → patient_diagnosis.patient_track_id

==============================================================================
"""
            
            return base_schema + schema_enhancements
            
        except Exception as e:
            logger.warning(f"Failed to get relevant schema: {e}. Falling back to full schema.")
            return self.cached_schema

    def _check_dashboard_kpi(self, question: str) -> Optional[Tuple[str, str]]:
        """
        Check if question matches a known dashboard KPI template.
        Returns (sql_query, description) if matched, None otherwise.
        
        IMPORTANT: Templates are checked in priority order - more specific first!
        """
        question_lower = question.lower().strip()
        
        # Check templates in priority order (list maintains order)
        for pattern, sql, description in DASHBOARD_KPI_TEMPLATES:
            if re.search(pattern, question_lower):
                logger.info(f"⚡ KPI Template Match: '{pattern}' -> {description}")
                return (sql.strip(), description)
        
        return None

    def _is_simple_query(self, question: str) -> bool:
        question_lower = question.lower().strip()
        
        if question_lower.startswith('select'):
            logger.info(" Analyzing pre-generated SQL query")
            
            try:
                logger.info("  Pre-generated SQL detected, but will regenerate for safety")
                return False
            except Exception:
                return False
        
        logger.info("🔍 Analyzing natural language query")
        
        simple_patterns = [
            r'\bcount\b.*\bpatients?\b',
            r'\bhow many\b.*\bpatients?\b',
            r'\btotal\b.*\bnumber\b',
            r'\baverage\b.*\b(bmi|age|glucose|systolic|diastolic|bp|blood pressure)\b',
            r'\bmean\b.*\b(bmi|age|glucose)\b',
            r'\bsum\b.*\b(patients?|visits?)\b',
            r'number of (patients?|visits?)',
            r'(male|female|gender).*patients?.*with.*(hypertension|diabetes|htn|dm)',
            r'(gender|age|bmi).*(distribution|breakdown)',
            r'distribution of (gender|age|patients?)',
        ]
        
        has_simple_pattern = any(re.search(pattern, question_lower) for pattern in simple_patterns)
        
        complex_indicators = [
            'compare', 'versus', 'vs', 'compared to',
            'trend', 'over time', 'by month', 'by year', 'by quarter',
            'breakdown by site', 'breakdown by region',
            'categorize',
            'correlation', 'relationship',
            'most', 'least', 'top', 'bottom',
            'rank', 'order by',
            'each', 'per', 'by site', 'by region',
            'percentage', 'proportion', 'ratio'
        ]
        
        has_complexity = any(indicator in question_lower for indicator in complex_indicators)
        
        table_references = sum(1 for table in (self.relevant_tables or []) if table.lower() in question_lower)
        
        targets_analytics_view = 'v_analytics' in question_lower
        if targets_analytics_view:
            logger.info("📊 Query targets analytics view - treating as single source")
            references_multiple_tables = False
        else:
            references_multiple_tables = table_references > 1
        
        is_simple = has_simple_pattern and not has_complexity and not references_multiple_tables
        
        if is_simple:
            logger.info("Query classified as SIMPLE (natural language)")
        else:
            logger.info(f" Query classified as COMPLEX (pattern={has_simple_pattern}, complexity={has_complexity}, multi_table={references_multiple_tables})")
        
        return is_simple
    
    def query(self, question: str) -> str:
        logger.info(f"Executing SQL query for: '{question[:100]}...'")
        
        kpi_match = self._check_dashboard_kpi(question)
        if kpi_match:
            sql_query, description = kpi_match
            logger.info(f"⚡ Using pre-defined KPI template for: {description}")
            return self._execute_kpi_template(sql_query, description, question)
        
        if self._is_simple_query(question):
            logger.info(" Detected simple query - using optimized execution path")
            return self._execute_optimized(question)
        else:
            logger.info(" Complex query detected - using full agent")
            return self._execute_with_agent(question)
    
    def _execute_kpi_template(self, sql_query: str, description: str, original_question: str) -> str:
        logger.info("=" * 80)
        logger.info("⚡ KPI TEMPLATE EXECUTION (1 API call):")
        logger.info("=" * 80)
        logger.info(f" Template: {description}")
        logger.info(f" SQL: {sql_query[:200]}...")
        
        try:
            result = self.db.run(sql_query)
            logger.info(f" Query result: {result}")
            
            format_prompt = f"""Convert this database result into a clear, natural language answer.

Dashboard KPI: {description}
SQL Query: {sql_query}
Result: {result}

Original question: {original_question}

Provide a concise, professional answer. Include the exact number(s) and briefly explain what they mean in the NCD program context."""

            formatted_response = self.llm.invoke(format_prompt)
            output = formatted_response.content.strip()
            
            logger.info("=" * 80)
            logger.info("✅ KPI template execution completed with 1 API call")
            logger.info(f" Final Answer: {output[:300]}...")
            logger.info("=" * 80)
            
            return output
            
        except Exception as e:
            logger.warning(f"⚠️ KPI template execution failed: {e}. Falling back to agent.")
            return self._execute_with_agent(original_question)
    
    def _execute_optimized(self, question: str) -> str:
        logger.info("=" * 80)
        logger.info("⚡ OPTIMIZED SQL EXECUTION:")
        logger.info("=" * 80)
        
        try:
            sql_query = None
            api_call_count = 0
            
            if question.strip().lower().startswith('select'):
                logger.info(" Input is already SQL format, using directly")
                sql_query = question.strip()
                sql_query = sql_query.split('--')[0].strip()
                sql_query = sql_query.rstrip(';') + ';'
            else:
                logger.info(" API Call 1: Generate SQL query with targeted schema")
                api_call_count += 1
                
                relevant_schema = self._get_relevant_schema(question)
                
                prompt = f"""You are a PostgreSQL expert. Generate ONLY a SQL query to answer the question.

DATABASE SCHEMA:
{relevant_schema}

IMPORTANT RULES:
1. Use ONLY the exact column names shown in the schema above
2. Use ONLY the exact table names shown in the schema above
3. Study the sample rows to understand the data
4. For patient demographics (gender, age), use the 'patient' table
5. For patient vitals (BP, glucose), use 'bp_log' or 'glucose_log'
6. The patient_visit table links to patient_tracker via 'patient_track_id'
7. Use proper date filtering: WHERE date_column >= 'YYYY-MM-DD' AND date_column <= 'YYYY-MM-DD'

QUESTION: {question}

Return ONLY the SQL query, no markdown, no explanation, no comments.

SQL Query:"""

                response = self.llm_fast.invoke(prompt)
                sql_query = response.content.strip()
                
                sql_query = re.sub(r'```sql\n?', '', sql_query)
                sql_query = re.sub(r'```\n?', '', sql_query)
                sql_query = sql_query.strip()
            
            logger.info(f" SQL to execute: {sql_query[:200]}...")
            
            if not self._validate_sql_query(sql_query):
                logger.warning("  SQL validation failed, falling back to agent")
                return self._execute_with_agent(question)
            
            logger.info(" Executing query against database (no API call)")
            result = self.db.run(sql_query)
            logger.info(f" Query result: {result}")
            
            logger.info(f" API Call {api_call_count + 1}: Format natural language response")
            api_call_count += 1
            
            format_prompt = f"""Convert this database result into a clear, natural language answer.

SQL Query: {sql_query}
Result: {result}

Original question: {question}

Provide a concise, natural language answer."""

            formatted_response = self.llm.invoke(format_prompt)
            output = formatted_response.content.strip()
            
            logger.info("=" * 80)
            logger.info(f" Optimized execution completed with {api_call_count} API call(s) (vs 7 with agent)")
            logger.info(f" Final Answer: {output[:300]}...")
            logger.info("=" * 80)
            
            return output
            
        except Exception as e:
            logger.warning(f"  Optimized execution failed: {e}. Falling back to full agent.")
            logger.error(f"Error details: {str(e)}", exc_info=True)
            return self._execute_with_agent(question)
    
    def _validate_sql_query(self, sql_query: str) -> bool:
        sql_lower = sql_query.lower().strip()
        
        if not sql_lower.startswith('select'):
            logger.warning("Query doesn't start with SELECT")
            return False
        
        dangerous_keywords = ['drop', 'delete', 'truncate', 'alter', 'create', 'insert', 'update', 'exec']
        if any(keyword in sql_lower for keyword in dangerous_keywords):
            logger.warning("Query contains dangerous keyword")
            return False
        
        if self.relevant_tables:
            has_known_table = any(table.lower() in sql_lower for table in self.relevant_tables)
            if not has_known_table:
                logger.warning("Query doesn't reference any known tables")
                return False
        
        if 'from' not in sql_lower:
            logger.warning("Query missing FROM clause")
            return False
        
        return True
    
    def _execute_with_agent(self, question: str) -> str:
        logger.info("=" * 80)
        logger.info(" SQL AGENT EXECUTION TRACE:")
        logger.info("=" * 80)
        
        try:
            result = self.sql_agent.invoke({"input": question})
            
            if isinstance(result, dict):
                output = result.get("output", str(result))
                
                if "intermediate_steps" in result:
                    logger.info("\n Agent Intermediate Steps:")
                    for i, step in enumerate(result["intermediate_steps"], 1):
                        action = step[0] if len(step) > 0 else None
                        observation = step[1] if len(step) > 1 else None
                        
                        logger.info(f"\n  Step {i}:")
                        if action:
                            logger.info(f"     Action: {action}")
                        if observation:
                            obs_preview = str(observation)[:300]
                            logger.info(f"      Observation: {obs_preview}...")
            else:
                output = str(result)
            
            logger.info("=" * 80)
            logger.info(f" SQL query completed. Result length: {len(output)} chars")
            output_preview = output[:300] if len(output) > 300 else output
            logger.info(f" Final Answer: {output_preview}...")
            logger.info("=" * 80)
            
            return output
            
        except Exception as e:
            logger.error(f" SQL query failed: {e}", exc_info=True)
            raise
    
    def health_check(self) -> bool:
        try:
            self.db.run("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def get_table_info(self) -> str:
        try:
            return self.db.get_table_info()
        except Exception as e:
            logger.error(f"Failed to get table info: {e}")
            return "Error retrieving table information"

    def get_schema_info_for_connection(self, uri: str) -> Dict[str, Any]:
        """
        Connect to a database URI and retrieve its schema (tables and columns).
        Used for the frontend Schema Explorer.
        """
        try:
            # Create a temporary connection
            temp_db = SQLDatabase.from_uri(uri)
            table_names = temp_db.get_usable_table_names()
            
            schema_info = {}
            for table in table_names:
                # Get column info
                # LangChain's SQLDatabase doesn't expose raw columns easily, 
                # but we can use the underlying engine inspector if needed.
                # Or parsing get_table_info([table]). 
                # For a cleaner approach, let's use the sqlalchemy inspector directly via the engine.
                inspector = inspect(temp_db._engine)
                columns = inspector.get_columns(table)
                
                column_details = []
                for col in columns:
                    column_details.append({
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True)
                    })
                
                schema_info[table] = column_details
                
            return {"tables": table_names, "details": schema_info}
            
        except Exception as e:
            logger.error(f"Failed to inspect schema for URI {uri}: {e}")
            raise ValueError(f"Could not connect or inspect database: {str(e)}")

@lru_cache()
def get_sql_service() -> SQLService:
    return SQLService()

