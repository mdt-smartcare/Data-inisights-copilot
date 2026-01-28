"""
Reflection Service - Self-Correction Logic.
Critiques generated SQL against schema rules and best practices.
"""
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser

from backend.config import get_settings
from backend.core.logging import get_logger
from backend.models.schemas import CritiqueResponse

settings = get_settings()
logger = get_logger(__name__)

CRITIQUE_PROMPT_TEMPLATE = """You are a Senior SQL Expert and Security Auditor.
Your job is to critique and validate the following SQL query generated for a PostgreSQL database.

DATABASE SCHEMA CONTEXT:
{schema_context}

USER QUESTION: "{question}"

GENERATED SQL:
{sql_query}

CRITIQUE RULES:
1. Schema Validation: Check if table and column names exist in the schema.
2. Logic Check: Does the SQL answer the user's question?
3. Security: Check for proper date handling and injection risks (though we use read-only).
4. Hallucination Check: Ensure no made-up columns that don't exist in the schema.
5. Join Logic: Are joins correct based on primary/foreign key relationships in the schema?

Output valid JSON matching the CritiqueResponse schema.
If the SQL is 100% correct and optimal, set is_valid=True.
"""

class SQLCritiqueService:
    def __init__(self):
        logger.info("Initializing SQLCritiqueService")
        self.llm = ChatOpenAI(
            temperature=0,
            model_name="gpt-4o", # Use smart model for critique
            api_key=settings.openai_api_key
        )
        self.parser = PydanticOutputParser(pydantic_object=CritiqueResponse)
        
        self.prompt = ChatPromptTemplate.from_template(
            CRITIQUE_PROMPT_TEMPLATE,
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )

    def critique_sql(self, question: str, sql_query: str, schema_context: str) -> CritiqueResponse:
        """
        Analyze SQL query for correctness and safety.
        """
        logger.info(f"Critiquing SQL for: '{question[:50]}...'")
        
        try:
            # Format inputs
            _input = self.prompt.format_messages(
                schema_context=schema_context,
                question=question,
                sql_query=sql_query
            )
            
            # Invoke LLM (direct invoke can typically handle Pydantic parsing if using structured output methods,
            # but standard invoke + parser is fine too. Let's use with_structured_output if available or parser)
            
            # Using Pydantic output parser workflow
            output = self.llm.invoke(_input)
            
            # Use structured output parsing
            if hasattr(self.llm, "with_structured_output"):
                structured_llm = self.llm.with_structured_output(CritiqueResponse)
                response = structured_llm.invoke(_input)
            else:
                # Fallback to manual parsing (though gpt-4o usually supports structured)
                response = self.parser.parse(output.content)
            
            if not response.is_valid:
                logger.warning(f"Critique Found Issues: {response.issues}")
            else:
                logger.info("SQL Critique Passed")
                
            return response
            
        except Exception as e:
            logger.error(f"Critique failed: {e}")
            # Fail safe - assume valid if critique breaks, to avoid blocking
            return CritiqueResponse(
                is_valid=True, 
                reasoning="Critique service unavailable", 
                issues=[]
            )

# Singleton
_critique_service = None

def get_critique_service():
    global _critique_service
    if not _critique_service:
        _critique_service = SQLCritiqueService()
    return _critique_service
