import json
from typing import Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from backend.config import get_settings
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
            self.llm = ChatOpenAI(
                temperature=0,
                model_name="gpt-4o",  # Use a competent model for structured output
                api_key=settings.openai_api_key
            )
        
        self.structured_llm = self.llm.with_structured_output(IntentClassification)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Antigravity, the Intent Router and Orchestrator for a clinical Hybrid RAG system.
Your function is to interpret user queries and route them to the correct execution engine.

You coordinate two subsystems:
1. SQL Agent — Structured Data Engine (INTENT A)
- Operates on relational clinical data.
- Supports numerical filters, aggregations, counts, statistics, and structured lookups.
- Triggers: counts, averages/min/max, filtering by numeric conditions, vitals, lab logs, or time-series metrics.
- Relevant Tables: bp_log, glucose_log, temperature_log, spo2_log, weight_log, patient, appointment.

2. Vector Engine — Unstructured Data Engine (INTENT B)
- Operates on narrative clinical documents.
- Supports semantic retrieval across clinical notes, summaries, and unstructured uploads.
- Triggers: symptoms, summaries, concepts, "notes", "documents", "clinical summaries".

3. Hybrid (SQL Filter -> Vector Search) (INTENT C)
- Triggers: Queries combining a numerical filter with a semantic text requirement.
- Example: "Summarize the notes for all patients whose glucose was over 200 last week."

STRICT RULE:
Never route numerical, threshold-based, or aggregation queries to the Vector Engine.
The Vector DB does not store row-level measurements and cannot evaluate expressions such as >, <, ranges, or mathematical conditions.

For Intent C, you must ALSO provide a valid PostgreSQL query in 'sql_filter' that returns a single column of 'patient_id' satisfying the numerical condition.
"""),
            ("user", "Query: {query}\n\nSchema Context (if needed for Intent C):\n{schema}")
        ])

    def classify(self, query: str, schema_context: str = "") -> IntentClassification:
        """Classify the user intent and optionally generate a SQL filter."""
        logger.info(f"Classifying intent for query: {query}")
        try:
            chain = self.prompt | self.structured_llm
            result = chain.invoke({"query": query, "schema": schema_context})
            logger.info(f"Classification result: Intent={result.intent}, SQL Filter={result.sql_filter}")
            return result
        except Exception as e:
            logger.error(f"Failed to classify intent: {e}")
            # Fallback to safe routing (B if semantic, A if structured) based on simple heuristics if LLM fails
            return IntentClassification(intent="B", sql_filter=None)
