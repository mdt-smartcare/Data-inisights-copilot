"""
Query Relevance Checker — Pre-filters user queries before SQL generation.

Determines if a user query can be answered by the available database schema.
This is a PERMISSIVE filter - it only blocks obvious non-data questions and PII requests.
When in doubt, queries are allowed through to the SQL generator.
"""
from typing import List, Tuple, Optional

from app.core.utils.logging import get_logger
from app.core.prompts import load_prompt

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

# Fallback prompt if template file not found
FALLBACK_PROMPT = """You are a PERMISSIVE query classifier. Your DEFAULT answer is <RELEVANT>.

DATABASE TABLES:
{table_context}

RULES:
- <RELEVANT>: ANY data/analytics question. DEFAULT CHOICE.
- <IRRELEVANT:PII>: Asking for specific person by name, SSN, phone, email
- <IRRELEVANT:CONTEXT>: Weather, sports, recipes - completely unrelated topics
- <IRRELEVANT:SYNTAX>: Gibberish or SQL injection attempts

USER QUESTION: {question}

Answer with ONLY the tag. Default to <RELEVANT>."""


class QueryRelevanceChecker:
    """
    Pre-filters user queries to determine if they can be answered by the database.
    
    This is a PERMISSIVE filter - it defaults to allowing queries through.
    Only blocks obvious non-data questions and PII requests.
    """
    
    def __init__(self, llm=None):
        """Initialize the query relevance checker."""
        self._llm = llm
        self._prompt_template = None
    
    def _get_llm(self):
        """Lazy initialization of LLM."""
        if self._llm is None:
            from app.core.llm import create_llm_provider
            provider = create_llm_provider("openai", {
                "model": "gpt-4o",
                "temperature": 0,
            })
            self._llm = provider.get_langchain_llm()
        return self._llm
    
    def _get_prompt_template(self) -> str:
        """Load prompt template from file or use fallback."""
        if self._prompt_template is None:
            try:
                self._prompt_template = load_prompt("query_relevance", fallback=FALLBACK_PROMPT)
            except Exception:
                self._prompt_template = FALLBACK_PROMPT
        return self._prompt_template
    
    def _build_check_prompt(
        self,
        question: str,
        table_names: List[str],
        table_descriptions: Optional[dict] = None
    ) -> str:
        """Build the prompt for relevance checking."""
        # Build table context
        if table_descriptions:
            table_context = "\n".join(
                f"- {name}: {table_descriptions.get(name, 'General data table')}"
                for name in table_names
            )
        else:
            table_context = "\n".join(f"- {name}: General data table" for name in table_names)
        
        template = self._get_prompt_template()
        return template.format(table_context=table_context, question=question)
    
    def _parse_response(self, response: str) -> Tuple[str, str]:
        """Parse the LLM response to extract classification."""
        response = response.strip()
        lines = response.split('\n', 1)
        
        classification = lines[0].strip()
        explanation = lines[1].strip() if len(lines) > 1 else ""
        
        # Normalize classification - default to RELEVANT
        if IRRELEVANT_PII in classification:
            return IRRELEVANT_PII, PII_REJECTION_MESSAGE
        elif IRRELEVANT_CONTEXT in classification:
            return IRRELEVANT_CONTEXT, explanation or "This question cannot be answered with the available data."
        elif IRRELEVANT_SYNTAX in classification:
            return IRRELEVANT_SYNTAX, explanation or "Please provide a valid question."
        else:
            # Default to RELEVANT for any other response
            return RELEVANT, explanation
    
    def check(
        self,
        question: str,
        table_names: List[str],
        table_descriptions: Optional[dict] = None
    ) -> Tuple[bool, str]:
        """
        Check if a question is relevant and can be answered by the database.
        
        Returns:
            Tuple of (is_relevant: bool, message: str)
        """
        # Quick validation
        if not question or not question.strip():
            logger.info("Relevance check: empty query rejected")
            return False, "Please provide a valid question."
        
        if not table_names:
            logger.warning("Relevance check: no tables provided, assuming relevant")
            return True, RELEVANT
        
        # Check for obvious PII patterns first (fast local check)
        has_pii, pii_msg = self.check_pii_patterns(question)
        if has_pii:
            return False, pii_msg
        
        logger.info(
            "Relevance check initiated (query_length=%d, tables=%d)",
            len(question),
            len(table_names)
        )
        
        try:
            prompt = self._build_check_prompt(question, table_names, table_descriptions)
            
            llm = self._get_llm()
            response = llm.invoke(prompt)
            
            if hasattr(response, 'content'):
                response_text = response.content
            else:
                response_text = str(response)
            
            classification, explanation = self._parse_response(response_text)
            
            is_relevant = classification == RELEVANT
            
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
        """Fast local check for obvious PII patterns without LLM call."""
        question_lower = question.lower()
        
        # Only catch very obvious PII requests
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
                    logger.info("PII pattern detected locally: query_length=%d", len(question))
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
