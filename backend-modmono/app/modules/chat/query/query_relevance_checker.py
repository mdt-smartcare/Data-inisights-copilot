"""
Query Relevance Checker — Pre-filters user queries before SQL generation.

Determines if a user query can be answered by the available database schema.
This prevents wasting LLM calls on irrelevant or unanswerable questions,
and enforces privacy by rejecting PII-seeking queries.

Classifications:
- RELEVANT: Question can be answered with available tables
- IRRELEVANT:CONTEXT: Question is about topics not in database
- IRRELEVANT:PII: Question asks for personally identifiable information
- IRRELEVANT:SYNTAX: Question is not a valid query
"""
from typing import List, Tuple, Optional

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


# Classification constants
RELEVANT = "<RELEVANT>"
IRRELEVANT_CONTEXT = "<IRRELEVANT:CONTEXT>"
IRRELEVANT_PII = "<IRRELEVANT:PII>"
IRRELEVANT_SYNTAX = "<IRRELEVANT:SYNTAX>"

# PII rejection message
PII_REJECTION_MESSAGE = (
    "This query requests personally identifiable information which cannot be disclosed. "
    "Please rephrase your question to ask for aggregated or anonymized data instead."
)


class QueryRelevanceChecker:
    """
    Pre-filters user queries to determine if they can be answered by the database.
    
    Uses a fast LLM to classify queries into:
    - RELEVANT: Can be answered with available data
    - IRRELEVANT:CONTEXT: Topic not covered by database
    - IRRELEVANT:PII: Requests personally identifiable information
    - IRRELEVANT:SYNTAX: Invalid or malformed query
    
    Usage:
        checker = get_query_relevance_checker()
        is_relevant, message = checker.check(
            question="What is the average blood pressure by age group?",
            table_names=["measurements", "entities"]
        )
        if not is_relevant:
            return f"Cannot answer: {message}"
    """
    
    def __init__(self, llm=None):
        """
        Initialize the query relevance checker.
        
        Args:
            llm: Optional LangChain LLM. If not provided, will initialize with gpt-3.5-turbo.
        """
        self._llm = llm
    
    def _get_llm(self):
        """Lazy initialization of fast LLM (gpt-3.5-turbo)."""
        if self._llm is None:
            from app.core.llm import create_llm_provider
            provider = create_llm_provider("openai", {
                "model": "gpt-3.5-turbo",
                "temperature": 0,
            })
            self._llm = provider.get_langchain_llm()
        return self._llm
    
    def _build_check_prompt(
        self,
        question: str,
        table_names: List[str],
        table_descriptions: Optional[dict] = None
    ) -> str:
        """
        Build the prompt for relevance checking.
        
        Args:
            question: User's question
            table_names: List of available table names
            table_descriptions: Optional dict mapping table names to descriptions
        """
        # Build table context
        if table_descriptions:
            table_context = "\n".join(
                f"- {name}: {table_descriptions.get(name, 'No description')}"
                for name in table_names
            )
        else:
            table_context = "\n".join(f"- {name}" for name in table_names)
        
        return f"""You are a query relevance classifier for a healthcare database system.

AVAILABLE DATABASE TABLES:
{table_context}

TASK: Classify the user's question into ONE of these categories:

<RELEVANT> - The question can be answered using the available tables. Questions about:
  - Counts, statistics, aggregations of data in these tables
  - Trends, distributions, comparisons using this data
  - Any analytical question that the schema can support

<IRRELEVANT:CONTEXT> - The question is about topics NOT covered by the database:
  - Asking about data/topics not in any table
  - General knowledge questions unrelated to the data
  - Questions about external systems or data sources

<IRRELEVANT:PII> - The question requests personally identifiable information:
  - Asking for specific individual's data by name (e.g., "Show me John Smith's records")
  - Requesting raw personal data export (e.g., "List all patient names and addresses")
  - Asking for contact information, addresses, phone numbers, or ID numbers
  - Asking to identify specific individuals (e.g., "Who is patient ID 12345?")
  - Requesting data that could identify individuals even without names

<IRRELEVANT:SYNTAX> - The question is malformed or not a valid query:
  - Gibberish or nonsensical text
  - Commands rather than questions (e.g., "Delete all records")
  - Empty or single-word inputs that aren't clear questions

IMPORTANT: For PII classification, be strict. If a query could potentially expose individual-level personal data, classify as <IRRELEVANT:PII>.

USER QUESTION: {question}

Respond with ONLY the classification tag (e.g., <RELEVANT>) followed by a brief explanation on the next line.
Do NOT include any other text before the classification tag."""
    
    def _parse_response(self, response: str) -> Tuple[str, str]:
        """
        Parse the LLM response to extract classification and explanation.
        
        Args:
            response: Raw LLM response text
            
        Returns:
            Tuple of (classification_tag, explanation)
        """
        response = response.strip()
        lines = response.split('\n', 1)
        
        classification = lines[0].strip()
        explanation = lines[1].strip() if len(lines) > 1 else ""
        
        # Normalize classification
        if RELEVANT in classification:
            return RELEVANT, explanation
        elif IRRELEVANT_PII in classification:
            return IRRELEVANT_PII, PII_REJECTION_MESSAGE
        elif IRRELEVANT_CONTEXT in classification:
            return IRRELEVANT_CONTEXT, explanation or "This question cannot be answered with the available data."
        elif IRRELEVANT_SYNTAX in classification:
            return IRRELEVANT_SYNTAX, explanation or "Please provide a valid question."
        else:
            # Unknown classification, assume relevant to avoid blocking valid queries
            logger.warning("Unknown classification received, assuming relevant")
            return RELEVANT, ""
    
    def check(
        self,
        question: str,
        table_names: List[str],
        table_descriptions: Optional[dict] = None
    ) -> Tuple[bool, str]:
        """
        Check if a question is relevant and can be answered by the database.
        
        Args:
            question: User's natural language question
            table_names: List of available table names in the database
            table_descriptions: Optional dict mapping table names to descriptions
            
        Returns:
            Tuple of (is_relevant: bool, message: str)
            - is_relevant: True if query should proceed to SQL generation
            - message: Classification result or rejection reason
        """
        # Quick validation
        if not question or not question.strip():
            logger.info("Relevance check: empty query rejected")
            return False, "Please provide a valid question."
        
        if not table_names:
            logger.warning("Relevance check: no tables provided, assuming relevant")
            return True, RELEVANT
        
        # Log check initiation (without query content for privacy)
        logger.info(
            "Relevance check initiated (query_length=%d, tables=%d)",
            len(question),
            len(table_names)
        )
        
        try:
            # Build and execute prompt
            prompt = self._build_check_prompt(question, table_names, table_descriptions)
            
            llm = self._get_llm()
            response = llm.invoke(prompt)
            
            # Extract text content from response
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            # Parse classification
            classification, explanation = self._parse_response(response_text)
            
            is_relevant = classification == RELEVANT
            
            # Log result (without query content)
            logger.info(
                "Relevance check complete: classification=%s, is_relevant=%s, query_length=%d",
                classification,
                is_relevant,
                len(question)
            )
            
            if is_relevant:
                return True, classification
            else:
                return False, explanation
                
        except Exception as e:
            # On error, assume relevant to avoid blocking valid queries
            logger.error("Relevance check failed: %s. Assuming relevant to proceed.", e)
            return True, RELEVANT
    
    def check_pii_patterns(self, question: str) -> Tuple[bool, str]:
        """
        Fast local check for obvious PII patterns without LLM call.
        
        This is a quick heuristic check that can catch obvious PII requests
        before making an LLM call.
        
        Args:
            question: User's question
            
        Returns:
            Tuple of (has_pii_pattern: bool, message: str)
        """
        question_lower = question.lower()
        
        # Patterns that strongly indicate PII requests
        pii_patterns = [
            # Name-based lookups
            ("show me", "record"),
            ("find", "patient named"),
            ("get", "information for"),
            ("look up", "name"),
            ("search for", "person"),
            
            # Contact information
            ("phone number", ""),
            ("email address", ""),
            ("home address", ""),
            ("contact info", ""),
            ("ssn", ""),
            ("social security", ""),
            
            # Export requests
            ("export all", "patient"),
            ("list all", "names"),
            ("download", "personal"),
            
            # Individual identification
            ("who is patient", ""),
            ("identify", "individual"),
            ("which person", ""),
        ]
        
        for pattern1, pattern2 in pii_patterns:
            if pattern1 in question_lower:
                if not pattern2 or pattern2 in question_lower:
                    logger.info(
                        "PII pattern detected locally: query_length=%d",
                        len(question)
                    )
                    return True, PII_REJECTION_MESSAGE
        
        return False, ""


# Singleton instance
_checker_instance: Optional[QueryRelevanceChecker] = None


def get_query_relevance_checker() -> QueryRelevanceChecker:
    """Get or create the query relevance checker singleton."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = QueryRelevanceChecker()
    return _checker_instance
