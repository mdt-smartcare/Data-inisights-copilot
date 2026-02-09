"""
Follow-Up Question Generation Service.
Generates context-aware follow-up questions based on response content.
"""
import asyncio
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Timeout for follow-up generation (seconds)
# Allow enough time for context-aware generation, but prevent blocking
FOLLOWUP_TIMEOUT_SECONDS = 10


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
    
    Uses an LLM to analyze the response content and generate
    relevant questions that help users explore deeper insights.
    """
    
    # Fallback questions when generation fails
    FALLBACK_QUESTIONS = [
        "Can you provide more details about this?",
        "How does this compare to other segments?",
        "What trends are visible in this data?"
    ]
    
    def __init__(self, llm):
        """
        Initialize the FollowUpService.
        
        Args:
            llm: LangChain LLM instance (shared with AgentService)
        """
        self.llm = llm
        self.parser = JsonOutputParser(pydantic_object=FollowUpQuestions)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert data analyst helping users explore insights.

Generate exactly 3 follow-up questions based on the system's response content that:
1. Reference specific details from the response (numbers, trends, segments, key findings)
2. Use simple, natural language for non-technical users
3. Cover different analytical angles: comparison, drill-down, causation, trends, or actions
4. Help users discover related insights or explore deeper
5. **IMPORTANT - Chart/Visualization Focus:** When the response contains numerical or categorical data 
   (counts, distributions, breakdowns, percentages), at least ONE question should suggest exploring 
   the data through visualization or alternative chart types. Examples:
   - "Can you show this as a [bar/pie/line] chart?"
   - "How would this look broken down by [another dimension]?"
   - "Can you visualize the trend over time?"
   - "What does the distribution look like across [categories]?"

Focus on the RESPONSE content, not just the original question. Extract specific data points, 
metrics, or findings mentioned in the response and build questions around them.

**Chart-Related Question Guidelines:**
- If response shows counts/distributions → suggest visualization by category
- If response shows percentages/proportions → suggest pie chart or comparison
- If response mentions time periods → suggest trend visualization
- If response compares groups → suggest side-by-side chart comparison

Original Question: {original_question}
System Response: {system_response}

{format_instructions}""")
        ])
        
        logger.info("FollowUpService initialized")
    
    async def generate_followups(
        self, 
        original_question: str, 
        system_response: str
    ) -> List[str]:
        """
        Generate 3 context-aware follow-up questions with timeout protection.
        
        Args:
            original_question: The user's original query
            system_response: The system's response text
            
        Returns:
            List of 3 follow-up question strings
        """
        try:
            # Use asyncio.wait_for to enforce timeout
            return await asyncio.wait_for(
                self._generate_followups_internal(original_question, system_response),
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
        system_response: str
    ) -> List[str]:
        """Internal method that performs the actual LLM call."""
        # Build and execute the chain
        chain = self.prompt | self.llm | self.parser
        
        result = await chain.ainvoke({
            "original_question": original_question,
            "system_response": system_response,
            "format_instructions": self.parser.get_format_instructions()
        })
        
        questions = result.get("questions", [])
        
        # Validate we got exactly 3 questions
        if len(questions) != 3:
            logger.warning(
                f"Expected 3 questions, got {len(questions)}. Using fallback."
            )
            return self.FALLBACK_QUESTIONS
        
        logger.debug(f"Generated follow-up questions: {questions}")
        return questions
