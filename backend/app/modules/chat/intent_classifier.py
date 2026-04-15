"""
Intent Router for query classification.

Routes queries to:
- A: SQL only (structured data questions - counts, aggregations, filters)
- B: Vector only (semantic search on documents)
- C: Hybrid (SQL filter for IDs + vector search on those IDs)
"""
import re
import time
from typing import Optional, Dict, Tuple, List
from enum import Enum
from pydantic import BaseModel, Field

from app.core.utils.logging import get_logger
from app.core.config import get_settings
from app.core.prompts import get_intent_router_prompt

logger = get_logger(__name__)

# Classification cache for performance
_CLASSIFICATION_CACHE: Dict[str, Tuple['IntentClassification', float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE_MAX_SIZE = 200


class QueryIntent(str, Enum):
    """Query intent types."""
    SQL_ONLY = "A"      # Pure SQL for structured data
    VECTOR_ONLY = "B"   # Pure vector search for documents
    HYBRID = "C"        # SQL filter + vector search
    FALLBACK = "Fallback"  # Use agent with tools


class IntentClassification(BaseModel):
    """Result of intent classification."""
    intent: str = Field(
        description="The classified intent: 'A' for SQL only, 'B' for Vector only, 'C' for Hybrid, or 'Fallback'."
    )
    sql_filter: Optional[str] = Field(
        default=None,
        description="For Intent C only: SQL query to extract IDs for filtering vector search."
    )
    confidence_score: float = Field(
        default=1.0,
        description="Confidence score between 0.0 and 1.0"
    )
    reason: str = Field(
        default="",
        description="Explanation for the classification"
    )


class IntentClassifier:
    """
    Classifies user queries into SQL, Vector, or Hybrid intents.
    
    Uses a combination of:
    1. Keyword heuristics (fast, no API call)
    2. LLM classification (accurate, slower - used when heuristics uncertain)
    """
    
    # Keywords indicating SQL queries (aggregations, counts, filters)
    SQL_KEYWORDS = [
        'count', 'total', 'how many', 'average', 'avg', 'sum',
        'rate', 'percentage', 'percent', '%',
        'breakdown', 'distribution', 'by age', 'by gender', 'by region',
        'highest', 'lowest', 'top', 'bottom', 'rank', 'ranking',
        'trend', 'monthly', 'yearly', 'weekly', 'daily',
        'male', 'female', 'coverage', 'screening',
        'min', 'max', 'minimum', 'maximum',
        'group by', 'grouped', 'per', 'each',
        'statistics', 'stats', 'numbers', 'metrics',
        'frequency', 'frequently', 'how often', 'occurrences',
        'assessment', 'assessments',
    ]
    
    # Keywords indicating Vector/RAG queries (semantic search)
    VECTOR_KEYWORDS = [
        'notes', 'documents', 'clinical summaries', 'tell me about',
        'find mentions', 'patient history', 'narrative', 'what did',
        'doctor wrote', 'patient notes', 'document search',
        'medical history', 'patient summary', 'clinical notes',
        'describe', 'explain', 'details about', 'information about',
        'symptoms', 'conditions', 'diagnosis', 'treatment plan',
        'search for', 'look for', 'find patients with',
        'mentions', 'references', 'discussed', 'reported',
    ]
    
    # Keywords indicating Hybrid queries (need both SQL filter + vector search)
    HYBRID_KEYWORDS = [
        'patients over', 'patients under', 'patients aged',
        'male patients with', 'female patients with',
        'patients in region', 'patients from district',
        'recent patients', 'patients diagnosed',
    ]
    
    def __init__(self, llm=None):
        """
        Initialize the intent classifier.
        
        Args:
            llm: Optional LangChain LLM. If not provided, will initialize from settings.
        """
        self._llm = llm
        self._structured_llm = None
        self._settings = get_settings()
    
    def _get_llm(self):
        """Lazy initialization of LLM."""
        if self._llm is None:
            from app.core.llm import create_llm_provider
            provider = create_llm_provider("openai", {
                "model": "gpt-4o-mini",  # Use smaller model for classification
                "temperature": 0,
            })
            self._llm = provider.get_langchain_llm()
        return self._llm
    
    def _get_structured_llm(self):
        """Get LLM with structured output."""
        if self._structured_llm is None:
            self._structured_llm = self._get_llm().with_structured_output(IntentClassification)
        return self._structured_llm
    
    def _keyword_classify(self, query: str) -> Optional[IntentClassification]:
        """
        Fast keyword-based classification.
        
        Returns classification if confident, None if LLM should be used.
        """
        query_lower = query.lower()
        
        # Check for hybrid patterns first (most specific)
        hybrid_score = sum(1 for kw in self.HYBRID_KEYWORDS if kw in query_lower)
        if hybrid_score > 0:
            return IntentClassification(
                intent=QueryIntent.HYBRID.value,
                confidence_score=0.8,
                reason=f"Hybrid keywords detected (score: {hybrid_score})"
            )
        
        # Count keyword matches
        sql_score = sum(1 for kw in self.SQL_KEYWORDS if kw in query_lower)
        vector_score = sum(1 for kw in self.VECTOR_KEYWORDS if kw in query_lower)
        
        # Clear SQL intent
        if sql_score >= 2 and vector_score == 0:
            return IntentClassification(
                intent=QueryIntent.SQL_ONLY.value,
                confidence_score=0.9,
                reason=f"SQL keywords dominant (SQL: {sql_score}, Vector: {vector_score})"
            )
        
        # Clear Vector intent
        if vector_score >= 2 and sql_score == 0:
            return IntentClassification(
                intent=QueryIntent.VECTOR_ONLY.value,
                confidence_score=0.9,
                reason=f"Vector keywords dominant (SQL: {sql_score}, Vector: {vector_score})"
            )
        
        # Strong SQL signal
        if sql_score > vector_score and sql_score >= 1:
            return IntentClassification(
                intent=QueryIntent.SQL_ONLY.value,
                confidence_score=0.7,
                reason=f"SQL keywords detected (SQL: {sql_score}, Vector: {vector_score})"
            )
        
        # Strong Vector signal
        if vector_score > sql_score and vector_score >= 1:
            return IntentClassification(
                intent=QueryIntent.VECTOR_ONLY.value,
                confidence_score=0.7,
                reason=f"Vector keywords detected (SQL: {sql_score}, Vector: {vector_score})"
            )
        
        # Ambiguous - return None to trigger LLM classification
        return None
    
    def _llm_classify(self, query: str, schema_context: str = "") -> IntentClassification:
        """
        LLM-based classification for ambiguous queries.
        """
        from langchain_core.prompts import ChatPromptTemplate
        
        # Load prompt from external template file
        system_prompt = get_intent_router_prompt()

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Query: {query}\n\nSchema Context:\n{schema}")
        ])
        
        try:
            chain = prompt | self._get_structured_llm()
            result = chain.invoke({
                "query": query,
                "schema": schema_context or "No schema provided"
            })
            return result
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            # Fallback to SQL (faster, lower risk)
            return IntentClassification(
                intent=QueryIntent.SQL_ONLY.value,
                confidence_score=0.5,
                reason=f"LLM failed, defaulting to SQL: {str(e)}"
            )
    
    def classify(
        self, 
        query: str, 
        schema_context: str = "",
        use_llm: bool = True
    ) -> IntentClassification:
        """
        Classify a query into SQL, Vector, or Hybrid intent.
        
        Args:
            query: User's natural language query
            schema_context: Optional database schema for better classification
            use_llm: Whether to use LLM for ambiguous cases (default True)
            
        Returns:
            IntentClassification with intent, confidence, and optional SQL filter
        """
        query = query.strip()
        if not query:
            return IntentClassification(
                intent=QueryIntent.FALLBACK.value,
                confidence_score=0.0,
                reason="Empty query"
            )
        
        # Check cache first
        cache_key = query.lower()
        now = time.time()
        
        if cache_key in _CLASSIFICATION_CACHE:
            cached, timestamp = _CLASSIFICATION_CACHE[cache_key]
            if now - timestamp < _CACHE_TTL_SECONDS:
                logger.info(f"Classification cache hit: {cached.intent}")
                return cached
            else:
                del _CLASSIFICATION_CACHE[cache_key]
        
        # Try keyword classification first (fast)
        result = self._keyword_classify(query)
        
        # If uncertain and LLM enabled, use LLM
        if result is None and use_llm:
            result = self._llm_classify(query, schema_context)
        elif result is None:
            # No LLM, default to fallback
            result = IntentClassification(
                intent=QueryIntent.FALLBACK.value,
                confidence_score=0.5,
                reason="Ambiguous query, LLM disabled"
            )
        
        # Cache result
        _CLASSIFICATION_CACHE[cache_key] = (result, now)
        if len(_CLASSIFICATION_CACHE) > _CACHE_MAX_SIZE:
            # Remove oldest entry
            oldest = next(iter(_CLASSIFICATION_CACHE))
            del _CLASSIFICATION_CACHE[oldest]
        
        logger.info(
            f"Query classified",
            intent=result.intent,
            confidence=result.confidence_score,
            reason=result.reason,
        )
        
        return result


# Singleton instance
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Get or create the intent classifier singleton."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
