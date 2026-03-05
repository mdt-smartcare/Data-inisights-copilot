"""
Intent Router — Routes user queries to the optimal retrieval engine.

For 6.5M row datasets:
- SQL Engine: Aggregations, counts, filters on structured data (milliseconds)
- RAG Engine: Semantic search on unstructured text (doctor_notes, clinical_history)
- Hybrid: Combines both for complex queries

Architecture:
1. Query Classification: Analyze query intent using patterns + LLM
2. Route Decision: SQL vs RAG vs Hybrid
3. Execution: Dispatch to appropriate engine
4. Result Fusion: Combine results if hybrid
"""

import re
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Classification of query intent for routing."""
    SQL_AGGREGATION = "sql_aggregation"      # COUNT, AVG, SUM, etc.
    SQL_FILTER = "sql_filter"                # WHERE conditions on structured data
    SQL_LOOKUP = "sql_lookup"                # Specific record lookups
    RAG_SEMANTIC = "rag_semantic"            # Free-text semantic search
    RAG_SIMILARITY = "rag_similarity"        # Find similar records/notes
    HYBRID = "hybrid"                        # Needs both SQL and RAG
    UNKNOWN = "unknown"


@dataclass
class RoutingDecision:
    """Result of intent routing analysis."""
    primary_intent: QueryIntent
    confidence: float
    use_sql: bool
    use_rag: bool
    sql_hints: List[str] = field(default_factory=list)  # Columns/tables for SQL
    rag_hints: List[str] = field(default_factory=list)  # Keywords for RAG
    reason: str = ""
    suggested_sql: Optional[str] = None


@dataclass
class IntentRouterConfig:
    """Configuration for the intent router."""
    # Patterns indicating SQL aggregation queries
    sql_aggregation_patterns: List[str] = field(default_factory=lambda: [
        r'\bhow many\b', r'\bcount\b', r'\btotal\b', r'\bnumber of\b',
        r'\baverage\b', r'\bmean\b', r'\bmedian\b', r'\bsum\b',
        r'\bminimum\b', r'\bmaximum\b', r'\bmin\b', r'\bmax\b',
        r'\bpercentage\b', r'\bproportion\b', r'\bratio\b',
        r'\bdistribution\b', r'\bbreakdown\b', r'\bgroup by\b',
        r'\bper\b.*\b(month|year|week|day|gender|age|type)\b',
    ])
    # Patterns indicating SQL filter queries
    sql_filter_patterns: List[str] = field(default_factory=lambda: [
        r'\bwhere\b', r'\bwith\b.*\b(age|gender|status|type|date)\b',
        r'\bgreater than\b', r'\bless than\b', r'\bbetween\b',
        r'\bolder than\b', r'\byounger than\b',
        r'\bbefore\b', r'\bafter\b', r'\bduring\b',
        r'\bequal to\b', r'\bmatching\b',
        r'\b(male|female)\b.*patients', r'patients.*\b(male|female)\b',
        r'\bfilter\b', r'\bonly\b.*\bwith\b',
    ])
    # Patterns indicating RAG semantic search
    rag_semantic_patterns: List[str] = field(default_factory=lambda: [
        r'\bfind\b.*\b(patients?|records?|cases?)\b.*\b(with|having|showing)\b',
        r'\bsearch\b', r'\blook for\b', r'\bidentify\b',
        r'\bsymptoms?\b', r'\bconditions?\b', r'\bdiagnos[ei]s\b',
        r'\btreatment\b', r'\bmedication\b', r'\bprescription\b',
        r'\bcomplaint\b', r'\bpresenting\b', r'\bhistory of\b',
        r'\bsimilar to\b', r'\blike\b', r'\bresembl\w+\b',
        r'\bmentioned\b', r'\bdescribed\b', r'\bnoted\b',
        r'\bchronic\b', r'\bacute\b', r'\bsevere\b',
        r'\bexhibiting\b', r'\bdisplaying\b', r'\bexperiencing\b',
    ])
    # Patterns indicating hybrid queries
    hybrid_patterns: List[str] = field(default_factory=lambda: [
        r'\bhow many\b.*\b(with|having)\b.*\b(symptoms?|conditions?|diagnosis)\b',
        r'\baverage\b.*\bwho\b.*\b(mentioned|described|noted)\b',
        r'\bpatients?\b.*\b(age|gender)\b.*\b(notes?|history)\b',
        r'\bcount\b.*\b(similar|like|matching)\b.*\btext\b',
    ])
    # Confidence thresholds
    high_confidence_threshold: float = 0.8
    medium_confidence_threshold: float = 0.6
    # LLM-based classification (more accurate but slower)
    use_llm_classification: bool = True


class IntentRouter:
    """
    Routes queries to the optimal retrieval engine based on intent analysis.
    
    For a 6.5M row clinical dataset:
    - "How many patients have diabetes?" → SQL (COUNT query, milliseconds)
    - "Find patients with chronic migraine and vision loss" → RAG (semantic search)
    - "Average age of patients mentioning chest pain" → Hybrid (SQL + RAG)
    """
    
    def __init__(self, config: Optional[IntentRouterConfig] = None):
        self.config = config or IntentRouterConfig()
        self._compiled_patterns: Dict[str, List[Tuple[re.Pattern, float]]] = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns with weights."""
        self._compiled_patterns = {
            'sql_aggregation': [
                (re.compile(p, re.IGNORECASE), 1.0) 
                for p in self.config.sql_aggregation_patterns
            ],
            'sql_filter': [
                (re.compile(p, re.IGNORECASE), 0.8)
                for p in self.config.sql_filter_patterns
            ],
            'rag_semantic': [
                (re.compile(p, re.IGNORECASE), 1.0)
                for p in self.config.rag_semantic_patterns
            ],
            'hybrid': [
                (re.compile(p, re.IGNORECASE), 1.2)  # Higher weight for explicit hybrid
                for p in self.config.hybrid_patterns
            ],
        }
    
    def _calculate_pattern_scores(self, query: str) -> Dict[str, float]:
        """Calculate match scores for each intent category."""
        scores = {
            'sql_aggregation': 0.0,
            'sql_filter': 0.0,
            'rag_semantic': 0.0,
            'hybrid': 0.0,
        }
        
        for category, patterns in self._compiled_patterns.items():
            for pattern, weight in patterns:
                if pattern.search(query):
                    scores[category] += weight
        
        return scores
    
    def _extract_sql_hints(self, query: str) -> List[str]:
        """Extract hints for SQL query generation."""
        hints = []
        
        # Look for column-like references
        column_patterns = [
            r'\b(age|gender|status|type|date|id|count|total)\b',
            r'\b(blood_pressure|bmi|weight|height|temperature)\b',
            r'\b(encounter|visit|admission|discharge)\b',
        ]
        
        for pattern in column_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            hints.extend(matches)
        
        # Look for aggregation functions
        if re.search(r'\bhow many\b|\bcount\b|\btotal\b', query, re.IGNORECASE):
            hints.append('COUNT')
        if re.search(r'\baverage\b|\bmean\b', query, re.IGNORECASE):
            hints.append('AVG')
        if re.search(r'\bsum\b|\btotal\b', query, re.IGNORECASE):
            hints.append('SUM')
        if re.search(r'\bgroup\b|\bper\b|\bby\b', query, re.IGNORECASE):
            hints.append('GROUP BY')
        
        return list(set(hints))
    
    def _extract_rag_hints(self, query: str) -> List[str]:
        """Extract hints for RAG semantic search."""
        hints = []
        
        # Medical/clinical terms for semantic search
        medical_patterns = [
            r'\b(symptom\w*|condition\w*|diagnos\w*|treatment\w*)\b',
            r'\b(pain|ache|discomfort|swelling|fever|fatigue)\b',
            r'\b(chronic|acute|severe|mild|moderate)\b',
            r'\b(medication\w*|prescription\w*|drug\w*)\b',
            r'\b(history|complaint|presentation)\b',
        ]
        
        for pattern in medical_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            hints.extend(matches)
        
        return list(set(hints))
    
    def _pattern_based_routing(self, query: str) -> RoutingDecision:
        """Route based on pattern matching (fast, no LLM)."""
        scores = self._calculate_pattern_scores(query)
        sql_hints = self._extract_sql_hints(query)
        rag_hints = self._extract_rag_hints(query)
        
        # Check for explicit hybrid patterns first
        if scores['hybrid'] > 0:
            return RoutingDecision(
                primary_intent=QueryIntent.HYBRID,
                confidence=min(0.9, scores['hybrid'] / 2),
                use_sql=True,
                use_rag=True,
                sql_hints=sql_hints,
                rag_hints=rag_hints,
                reason=f"Hybrid patterns detected (score: {scores['hybrid']:.2f})"
            )
        
        # Compare SQL vs RAG scores
        sql_score = scores['sql_aggregation'] + scores['sql_filter']
        rag_score = scores['rag_semantic']
        
        if sql_score > rag_score and sql_score > 0:
            if scores['sql_aggregation'] > scores['sql_filter']:
                intent = QueryIntent.SQL_AGGREGATION
            else:
                intent = QueryIntent.SQL_FILTER
            
            return RoutingDecision(
                primary_intent=intent,
                confidence=min(0.9, sql_score / 3),
                use_sql=True,
                use_rag=False,
                sql_hints=sql_hints,
                rag_hints=[],
                reason=f"SQL patterns dominant (score: {sql_score:.2f} vs RAG: {rag_score:.2f})"
            )
        
        if rag_score > sql_score and rag_score > 0:
            return RoutingDecision(
                primary_intent=QueryIntent.RAG_SEMANTIC,
                confidence=min(0.9, rag_score / 3),
                use_sql=False,
                use_rag=True,
                sql_hints=[],
                rag_hints=rag_hints,
                reason=f"RAG patterns dominant (score: {rag_score:.2f} vs SQL: {sql_score:.2f})"
            )
        
        # Both have scores - might be hybrid
        if sql_score > 0 and rag_score > 0:
            return RoutingDecision(
                primary_intent=QueryIntent.HYBRID,
                confidence=0.6,
                use_sql=True,
                use_rag=True,
                sql_hints=sql_hints,
                rag_hints=rag_hints,
                reason=f"Mixed signals - SQL: {sql_score:.2f}, RAG: {rag_score:.2f}"
            )
        
        # No clear patterns - default to SQL for structured data
        return RoutingDecision(
            primary_intent=QueryIntent.UNKNOWN,
            confidence=0.3,
            use_sql=True,  # Default to SQL as it's faster
            use_rag=False,
            sql_hints=sql_hints,
            rag_hints=rag_hints,
            reason="No strong patterns detected - defaulting to SQL"
        )
    
    def _llm_based_routing(self, query: str, schema_context: str = "") -> RoutingDecision:
        """Route using LLM classification (more accurate, slower)."""
        try:
            from langchain_openai import ChatOpenAI
            from backend.config import get_settings
            
            settings = get_settings()
            llm = ChatOpenAI(
                temperature=0,
                model_name="gpt-3.5-turbo",
                api_key=settings.openai_api_key,
            )
            
            prompt = f"""Classify this query for a clinical database with 6.5M patient records.

The database has:
- Structured columns: age, gender, blood_pressure, bmi, encounter_type, dates, IDs
- Unstructured columns: doctor_notes, clinical_history, assessment_notes

Query: "{query}"

{f"Schema context: {schema_context}" if schema_context else ""}

Classify as ONE of:
1. SQL_AGGREGATION - Counting, averaging, summing structured data
2. SQL_FILTER - Filtering/looking up records by structured fields
3. RAG_SEMANTIC - Searching free-text notes for symptoms, conditions, descriptions
4. HYBRID - Needs both structured filters AND semantic text search

Respond with JSON:
{{"intent": "SQL_AGGREGATION|SQL_FILTER|RAG_SEMANTIC|HYBRID", "confidence": 0.0-1.0, "reason": "brief explanation"}}

JSON:"""

            response = llm.invoke(prompt)
            content = response.content.strip()
            
            # Parse JSON response
            import json
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                result = json.loads(json_match.group())
                intent_map = {
                    'SQL_AGGREGATION': QueryIntent.SQL_AGGREGATION,
                    'SQL_FILTER': QueryIntent.SQL_FILTER,
                    'RAG_SEMANTIC': QueryIntent.RAG_SEMANTIC,
                    'HYBRID': QueryIntent.HYBRID,
                }
                
                intent = intent_map.get(result.get('intent', ''), QueryIntent.UNKNOWN)
                confidence = float(result.get('confidence', 0.7))
                reason = result.get('reason', 'LLM classification')
                
                return RoutingDecision(
                    primary_intent=intent,
                    confidence=confidence,
                    use_sql=intent in [QueryIntent.SQL_AGGREGATION, QueryIntent.SQL_FILTER, QueryIntent.HYBRID],
                    use_rag=intent in [QueryIntent.RAG_SEMANTIC, QueryIntent.HYBRID],
                    sql_hints=self._extract_sql_hints(query),
                    rag_hints=self._extract_rag_hints(query),
                    reason=f"LLM: {reason}"
                )
        except Exception as e:
            logger.warning(f"LLM routing failed, falling back to patterns: {e}")
        
        # Fallback to pattern-based
        return self._pattern_based_routing(query)
    
    def route(
        self, 
        query: str, 
        schema_context: str = "",
        use_llm: Optional[bool] = None
    ) -> RoutingDecision:
        """
        Route a query to the appropriate retrieval engine.
        
        Args:
            query: User's natural language query
            schema_context: Optional schema information for better routing
            use_llm: Override config for LLM usage
            
        Returns:
            RoutingDecision with intent and engine recommendations
        """
        query = query.strip()
        if not query:
            return RoutingDecision(
                primary_intent=QueryIntent.UNKNOWN,
                confidence=0.0,
                use_sql=False,
                use_rag=False,
                reason="Empty query"
            )
        
        # Determine whether to use LLM
        should_use_llm = use_llm if use_llm is not None else self.config.use_llm_classification
        
        if should_use_llm:
            decision = self._llm_based_routing(query, schema_context)
        else:
            decision = self._pattern_based_routing(query)
        
        logger.info(
            f"Intent routing: '{query[:50]}...' → {decision.primary_intent.value} "
            f"(confidence: {decision.confidence:.0%}, SQL: {decision.use_sql}, RAG: {decision.use_rag})"
        )
        
        return decision
    
    def route_batch(
        self, 
        queries: List[str],
        use_llm: bool = False  # Batch routing typically uses patterns for speed
    ) -> List[RoutingDecision]:
        """Route multiple queries efficiently."""
        return [self.route(q, use_llm=use_llm) for q in queries]


# Convenience functions
def get_intent_router(config: Optional[IntentRouterConfig] = None) -> IntentRouter:
    """Get an IntentRouter instance."""
    return IntentRouter(config)


def route_query(query: str, use_llm: bool = False) -> RoutingDecision:
    """Quick routing for a single query."""
    router = IntentRouter()
    return router.route(query, use_llm=use_llm)
