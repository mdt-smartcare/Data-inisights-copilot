"""
Follow-up question generation service.

Generates contextual follow-up questions based on the query and response.
"""
import asyncio
from typing import List, Optional

from app.core.utils.logging import get_logger
from app.core.config import get_settings
from app.core.prompts import get_followup_generator_prompt

logger = get_logger(__name__)


class FollowupService:
    """
    Service for generating follow-up questions.
    
    Uses LLM to suggest relevant follow-up questions based on
    the original query and the system's response.
    """
    
    def __init__(self):
        self._settings = get_settings()
    
    async def generate_followups(
        self,
        original_question: str,
        system_response: str,
        max_questions: int = 3,
        callbacks: Optional[List] = None,
    ) -> List[str]:
        """
        Generate follow-up questions.
        
        Args:
            original_question: User's original query
            system_response: System's response
            max_questions: Maximum number of follow-ups to generate
            callbacks: Optional LangChain callbacks for tracing
            
        Returns:
            List of follow-up question strings
        """
        try:
            from app.core.llm import create_llm_provider
            from langchain_core.prompts import ChatPromptTemplate
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", get_followup_generator_prompt()),
                ("user", """Original question: {question}

Response received: {response}

Suggest {max_questions} follow-up questions:""")
            ])
            
            provider = create_llm_provider("openai", {
                "model": "gpt-4o-mini",
                "temperature": 0.7,  # Some creativity for varied questions
            })
            llm = provider.get_langchain_llm()
            
            chain = prompt | llm
            
            # Truncate response if too long
            response_preview = system_response[:1000] if len(system_response) > 1000 else system_response
            
            result = await chain.ainvoke(
                {
                    "question": original_question,
                    "response": response_preview,
                    "max_questions": max_questions,
                },
                config={"callbacks": callbacks} if callbacks else None,
            )
            
            # Parse questions from response
            questions = []
            for line in result.content.strip().split('\n'):
                line = line.strip()
                # Remove common prefixes
                for prefix in ['- ', '• ', '1. ', '2. ', '3. ', '4. ', '5. ']:
                    if line.startswith(prefix):
                        line = line[len(prefix):]
                
                if line and line.endswith('?'):
                    questions.append(line)
            
            return questions[:max_questions]
            
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
            return []


# Singleton instance
_followup_service: Optional[FollowupService] = None


def get_followup_service() -> FollowupService:
    """Get the follow-up service singleton."""
    global _followup_service
    if _followup_service is None:
        _followup_service = FollowupService()
    return _followup_service


async def generate_followups_background(
    original_question: str,
    system_response: str,
    timeout: float = 2.0,
) -> List[str]:
    """
    Generate follow-up questions with timeout.
    
    This is meant to be called as a background task that shouldn't
    slow down the main response.
    
    Args:
        original_question: User's original query
        system_response: System's response
        timeout: Maximum time to wait (seconds)
        
    Returns:
        List of follow-up questions, or empty list if timeout/error
    """
    service = get_followup_service()
    
    try:
        return await asyncio.wait_for(
            service.generate_followups(original_question, system_response),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Follow-up generation timed out")
        return []
    except Exception as e:
        logger.warning(f"Follow-up generation failed: {e}")
        return []
