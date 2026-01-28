"""
Follow-Up Question Generation Service.
Generates context-aware follow-up questions based on response content.
"""
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from backend.core.logging import get_logger

logger = get_logger(__name__)


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

Focus on the RESPONSE content, not just the original question. Extract specific data points, 
metrics, or findings mentioned in the response and build questions around them.

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
        Generate 3 context-aware follow-up questions.
        
        Args:
            original_question: The user's original query
            system_response: The system's response text
            
        Returns:
            List of 3 follow-up question strings
        """
        try:
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
            
        except Exception as e:
            logger.warning(
                f"Failed to generate follow-up questions: {e}. Using fallback."
            )
            return self.FALLBACK_QUESTIONS
