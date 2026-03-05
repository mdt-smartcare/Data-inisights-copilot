import json
from typing import Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from backend.config import get_settings, get_llm_settings
from backend.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class IntentClassification(BaseModel):
    """Structured output for the intent routing decision."""
    intent: str = Field(
        description="The classified intent: 'A' for SQL only, 'B' for Vector only, or 'C' for Hybrid."
    )
    sql_filter: Optional[str] = Field(
        description="For Intent C ONLY, a PostgreSQL query to extract the relevant IDs (e.g., patient_id). Return None for Intent A or B.",
        default=None
    )


class IntentClassifier:
    """
    Intent Router for clinical Hybrid RAG system.
    Routes queries to SQL Engine, Vector Engine, or Hybrid approach.
    """
    
    def __init__(self, llm=None):
        if llm:
            self.llm = llm
        else:
            # Get LLM settings from database (runtime configurable)
            llm_settings = get_llm_settings()
            self.llm = ChatOpenAI(
                temperature=0,
                model_name=llm_settings.get('model_name', 'gpt-4o'),
                api_key=settings.openai_api_key
            )
        
        self.structured_llm = self.llm.with_structured_output(IntentClassification)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Antigravity, the Intent Router and Orchestrator for a clinical Hybrid RAG system.
Your function is to interpret user queries and route them to the correct execution engine.

You coordinate two subsystems:
1. SQL Agent — Structured Data Engine (INTENT A)
- Operates on relational clinical data (tables, spreadsheets, CSV files).
- Supports numerical filters, aggregations, counts, statistics, distributions, breakdowns, and structured lookups.
- ALWAYS use SQL for: counts, totals, averages, min/max, rates, percentages, distributions, breakdowns by category, rankings, trends, care cascades, funnel analysis.
- Triggers: "how many", "count", "total", "average", "rate", "percentage", "breakdown", "distribution", "by age", "by gender", "by region", "highest", "lowest", "top", "trend", "cascade", "funnel", "screened", "diagnosed", "treated", "controlled".

2. Vector Engine — Unstructured Data Engine (INTENT B)
- Operates on narrative clinical documents, notes, and free-text content.
- Supports semantic retrieval across clinical notes, summaries, and unstructured uploads.
- ONLY use Vector for: finding specific patient notes, clinical summaries, document search, "tell me about patient X", "find notes mentioning Y".
- Triggers: "notes", "documents", "clinical summaries", "tell me about", "find mentions of", "patient history narrative".

3. Hybrid (SQL Filter -> Vector Search) (INTENT C)
- Combines numerical SQL filtering with semantic text search.
- Triggers: Queries that need BOTH a numerical condition AND narrative content.
- Example: "Summarize the notes for all patients whose glucose was over 200 last week."

CRITICAL RULES:
1. CARE CASCADE / FUNNEL queries are ALWAYS Intent A (SQL):
   - "Show the care cascade" → SQL aggregation by status/stage
   - "NCD care cascade" → SQL COUNT grouped by screening/diagnosis/treatment status
   - "Patient journey stages" → SQL aggregation

2. DISTRIBUTION / BREAKDOWN queries are ALWAYS Intent A (SQL):
   - "Distribution by region" → SQL GROUP BY region
   - "Breakdown by age" → SQL GROUP BY age_group
   - "Male vs female" → SQL GROUP BY gender

3. RATE / PERCENTAGE queries are ALWAYS Intent A (SQL):
   - "Control rate" → SQL calculation
   - "Screening coverage" → SQL percentage

4. Only use Intent B (Vector) for actual unstructured text search:
   - "Find patient notes about diabetes complications"
   - "What did the doctor write about patient X?"

For Intent C, you must ALSO provide a valid PostgreSQL query in 'sql_filter' that returns a single column of 'patient_id' satisfying the numerical condition.
"""),
            ("user", "Query: {query}\n\nSchema Context (if needed for Intent C):\n{schema}")
        ])

    def classify(self, query: str, schema_context: str = "") -> IntentClassification:
        """Classify the user intent and optionally generate a SQL filter."""
        logger.info(f"Classifying intent for query: {query}")
        
        # Quick heuristic pre-check for obvious SQL queries
        query_lower = query.lower()
        sql_keywords = [
            'count', 'total', 'how many', 'average', 'rate', 'percentage', 'percent',
            'breakdown', 'distribution', 'by age', 'by gender', 'by region', 'by district',
            'highest', 'lowest', 'top', 'bottom', 'rank', 'trend', 'monthly', 'yearly',
            'cascade', 'funnel', 'screened', 'diagnosed', 'treated', 'controlled',
            'male', 'female', 'coverage', 'screening', 'vs target'
        ]
        
        if any(keyword in query_lower for keyword in sql_keywords):
            logger.info(f"Pre-classified as Intent A (SQL) based on keywords")
            return IntentClassification(intent="A", sql_filter=None)
        
        try:
            chain = self.prompt | self.structured_llm
            result = chain.invoke({"query": query, "schema": schema_context})
            logger.info(f"Classification result: Intent={result.intent}, SQL Filter={result.sql_filter}")
            return result
        except Exception as e:
            logger.error(f"Failed to classify intent: {e}")
            # Fallback to SQL for most analytical queries
            return IntentClassification(intent="A", sql_filter=None)
