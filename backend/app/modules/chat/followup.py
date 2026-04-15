"""
Follow-up question generation service.

Generates contextual follow-up questions based on the query and response.
"""
import asyncio
import json
import re
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
        conversation_history: Optional[str] = None,
        max_questions: int = 3,
        callbacks: Optional[List] = None,
    ) -> List[str]:
        """
        Generate follow-up questions.
        
        Args:
            original_question: User's original query
            system_response: System's response
            conversation_history: Optional previous conversation context
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
                ("user", """{history_section}Current question: {question}

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
            
            # Build history section if available
            history_section = ""
            if conversation_history:
                history_section = f"Conversation history:\n{conversation_history}\n\n"
            
            result = await chain.ainvoke(
                {
                    "question": original_question,
                    "response": response_preview,
                    "history_section": history_section,
                    "max_questions": max_questions,
                },
                config={"callbacks": callbacks} if callbacks else None,
            )
            
            # Parse questions from response
            questions = self._parse_followup_questions(result.content, max_questions)
            
            return questions
            
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
            return []
    
    def _parse_followup_questions(self, content: str, max_questions: int) -> List[str]:
        """
        Parse follow-up questions from LLM response.
        
        Handles both JSON array format and line-by-line format.
        """
        questions = []
        content = content.strip()
        
        # Try to parse as JSON first (expected format from prompt)
        try:
            # Extract JSON array from content (may be wrapped in markdown code blocks)
            json_match = re.search(r'\[.*?\]', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, str) and item.strip():
                            questions.append(item.strip())
                    if questions:
                        return questions[:max_questions]
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Fallback: parse line-by-line format
        for line in content.split('\n'):
            line = line.strip()
            # Remove common prefixes
            for prefix in ['- ', '• ', '1. ', '2. ', '3. ', '4. ', '5. ', '1) ', '2) ', '3) ']:
                if line.startswith(prefix):
                    line = line[len(prefix):]
            
            # Remove surrounding quotes if present
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            
            if line and line.endswith('?'):
                questions.append(line)
        
        return questions[:max_questions]


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
    conversation_history: Optional[str] = None,
    timeout: float = 2.0,
) -> List[str]:
    """
    Generate follow-up questions with timeout.
    
    This is meant to be called as a background task that shouldn't
    slow down the main response.
    
    Args:
        original_question: User's original query
        system_response: System's response
        conversation_history: Optional previous conversation context
        timeout: Maximum time to wait (seconds)
        
    Returns:
        List of follow-up questions, or empty list if timeout/error
    """
    service = get_followup_service()
    
    try:
        return await asyncio.wait_for(
            service.generate_followups(
                original_question, 
                system_response,
                conversation_history=conversation_history,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Follow-up generation timed out")
        return []
    except Exception as e:
        logger.warning(f"Follow-up generation failed: {e}")
        return []
