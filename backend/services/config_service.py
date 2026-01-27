import logging
from typing import List, Optional
from langchain.prompts import ChatPromptTemplate
from backend.services.sql_service import get_sql_service
from backend.services.agent_service import get_agent_service
from backend.sqliteDb.db import get_db_service

logger = logging.getLogger(__name__)

class ConfigService:
    def __init__(self):
        self.sql_service = get_sql_service()
        # Access the LLM from the agent service (reusing the configured ChatOpenAI instance)
        self.llm = get_agent_service().llm
        self.db_service = get_db_service()

    def generate_draft_prompt(self, data_dictionary: str) -> str:
        """
        Generates a draft system prompt based on the provided data dictionary / context.
        
        Args:
            data_dictionary: A string containing schema info, selected tables, and user notes.
                             (Constructed by the frontend wizard)
        """
        system_role = "You are a Clinical Data Architect and AI System Prompt Engineer."
        instruction = (
            "Your task is to write a comprehensive SYSTEM PROMPT for an AI assistant that will query a medical database.\n\n"
            "CONTEXT PROVIDED:\n"
            f"{data_dictionary}\n\n"
            "INSTRUCTIONS:\n"
            "1. Define the persona (NCD Clinical Data Intelligence Agent).\n"
            "2. List the KEY tables and columns available based on the context above.\n"
            "3. Define strict rules for SQL generation (e.g., joins, filters).\n"
            "4. Start with: 'You are an advanced NCD Clinical Data Intelligence Agent...'\n"
            "5. return ONLY the prompt text, no markdown formatting."
        )

        # Construct the prompt template
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_role),
            ("user", instruction)
        ])

        # Invoke the LLM
        chain = prompt_template | self.llm
        response = chain.invoke({})
        return response.content

    def publish_system_prompt(self, prompt_text: str, user_id: str):
        """Publish a new version of the system prompt."""
        return self.db_service.publish_system_prompt(prompt_text, user_id)

    def get_prompt_history(self):
        """Get history of all system prompts."""
        return self.db_service.get_all_prompts()

# Singleton instance pattern not strictly requested but good practice if needed.
# For now, just the class is requested, but usually services are singletons or instantiated per request.
# The prompt asks to "Create a class ConfigService". 
# The API route will likely instantiate it.

def get_config_service() -> ConfigService:
    return ConfigService()
