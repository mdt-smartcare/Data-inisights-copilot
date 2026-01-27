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
        Generates a draft system prompt based on the database schema and user-provided data dictionary.
        """
        # Fetch all table names using the SQL service's database connection
        # Adapting from prompt "self.sql_service.db_connector.get_all_tables()" 
        # to actual "self.sql_service.db.get_usable_table_names()"
        try:
            table_list = self.sql_service.db.get_usable_table_names()
        except AttributeError:
             # Fallback if db structure is different, but based on inspection it should be this
             logger.warning("Could not fetch table names from sql_service.db, using empty list.")
             table_list = []

        system_role = "You are a Clinical Data Architect."
        instruction = (
            "Analyze the schema and dictionary. Write a strict System Instruction for an AI chatbot "
            "to query this database. Define table relationships and unit conversions."
        )

        # Construct the prompt template
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_role),
            ("user", f"Tables: {table_list}\n\nData Dictionary:\n{data_dictionary}\n\n{instruction}")
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
