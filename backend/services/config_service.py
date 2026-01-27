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

    def publish_prompt(self, prompt_text: str, user_id: str) -> int:
        """
        Publishes a new system prompt.
        - Inserts into system_prompts table.
        - Increments version.
        - Sets is_active=1 for the new row and 0 for all others.
        
        Returns:
            The version number of the newly published prompt.
        """
        conn = self.db_service.get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Get the current max version
            cursor.execute("SELECT MAX(version) FROM system_prompts")
            result = cursor.fetchone()
            current_max_version = result[0] if result and result[0] is not None else 0
            new_version = current_max_version + 1

            # 2. Deactivate all existing prompts
            cursor.execute("UPDATE system_prompts SET is_active = 0 WHERE is_active = 1")

            # 3. Insert the new prompt
            cursor.execute("""
                INSERT INTO system_prompts (prompt_text, version, is_active, created_by)
                VALUES (?, ?, 1, ?)
            """, (prompt_text, new_version, user_id))
            
            conn.commit()
            logger.info(f"Published new system prompt version {new_version} by user {user_id}")
            return new_version
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to publish prompt: {e}")
            raise
        finally:
            conn.close()

# Singleton instance pattern not strictly requested but good practice if needed.
# For now, just the class is requested, but usually services are singletons or instantiated per request.
# The prompt asks to "Create a class ConfigService". 
# The API route will likely instantiate it.

def get_config_service() -> ConfigService:
    return ConfigService()
