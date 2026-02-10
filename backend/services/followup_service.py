"""
Follow-Up Question Generation Service.
Generates context-aware follow-up questions based on response content.

OPTIMIZED: Uses gpt-3.5-turbo for faster generation with reduced timeout.
"""
import asyncio
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Reduced timeout for faster response - follow-ups are nice-to-have, not critical
FOLLOWUP_TIMEOUT_SECONDS = 5


class FollowUpQuestions(BaseModel):
    """Pydantic model for structured LLM output."""
    questions: List[str] = Field(
        description="List of 3 contextually relevant follow-up questions",
        min_length=3,
        max_length=3
    )


class FollowUpService:
    """
    Service for generating context-aware follow-up questions.
    
    OPTIMIZED: Uses gpt-3.5-turbo (faster & cheaper) instead of gpt-4o.
    Follow-up questions don't require advanced reasoning.
    """
    
    # Fallback questions when generation fails
    FALLBACK_QUESTIONS = [
        "Can you provide more details about this?",
        "How does this compare to other segments?",
        "What trends are visible in this data?"
    ]
    
    def __init__(self, llm=None):
        """
        Initialize the FollowUpService.
        
        Args:
            llm: LangChain LLM instance (ignored - we use dedicated fast model)
        """
        # Use dedicated fast model for follow-ups (gpt-3.5-turbo is 10x faster)
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.7,  # Slightly creative for diverse questions
            api_key=settings.openai_api_key,
            max_tokens=200,  # Follow-ups are short
            request_timeout=5,  # Fast timeout
        )
        
        self.parser = JsonOutputParser(pydantic_object=FollowUpQuestions)
        
        # Simplified prompt for faster processing
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Generate 3 brief follow-up questions based on the response.
Questions should:
- Reference specific details from the response
- Be simple and natural
- Cover different angles: comparison, drill-down, trends

Original Question: {original_question}
Response Summary: {system_response}

{format_instructions}""")
        ])
        
        logger.info("FollowUpService initialized with fast model (gpt-3.5-turbo)")
    
    async def generate_followups(
        self, 
        original_question: str, 
        system_response: str,
        callbacks: Optional[List[BaseCallbackHandler]] = None
    ) -> List[str]:
        """
        Generate 3 context-aware follow-up questions with timeout protection.
        
        Args:
            original_question: The user's original query
            system_response: The system's response text (truncated for speed)
            callbacks: Optional list of callback handlers for tracing
            
        Returns:
            List of 3 follow-up question strings
        """
        try:
            # Truncate response to first 500 chars for faster processing
            truncated_response = system_response[:500] if len(system_response) > 500 else system_response
            
            # Use asyncio.wait_for to enforce timeout
            return await asyncio.wait_for(
                self._generate_followups_internal(original_question, truncated_response, callbacks),
                timeout=FOLLOWUP_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Follow-up generation timed out after {FOLLOWUP_TIMEOUT_SECONDS}s. Using fallback."
            )
            return self.FALLBACK_QUESTIONS
        except Exception as e:
            logger.warning(
                f"Failed to generate follow-up questions: {e}. Using fallback."
            )
            return self.FALLBACK_QUESTIONS
    
    async def _generate_followups_internal(
        self, 
        original_question: str, 
        system_response: str,
        callbacks: Optional[List[BaseCallbackHandler]] = None
    ) -> List[str]:
        """Internal method that performs the actual LLM call."""
        # Build and execute the chain
        chain = self.prompt | self.llm | self.parser
        
        # Build config with callbacks if provided (for Langfuse tracing)
        config = {}
        if callbacks:
            config["callbacks"] = callbacks
        
        result = await chain.ainvoke(
            {
                "original_question": original_question,
                "system_response": system_response,
                "format_instructions": self.parser.get_format_instructions()
            },
            config=config if config else None
        )
        
        questions = result.get("questions", [])
        
        # Validate we got exactly 3 questions
        if len(questions) != 3:
            logger.warning(
                f"Expected 3 questions, got {len(questions)}. Using fallback."
            )
            return self.FALLBACK_QUESTIONS
        
        logger.debug(f"Generated follow-up questions: {questions}")
        return questions
