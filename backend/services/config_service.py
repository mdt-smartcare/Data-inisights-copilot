import logging
from typing import List, Optional, Dict, Any
import json
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

    def generate_draft_prompt(self, data_dictionary: str) -> Dict[str, Any]:
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
        # Invoke the LLM
        # We want the LLM to explain WHY it prioritized certain tables
        instruction += (
            "\n\nAlso, at the end of your response, strictly separated by '---REASONING---', "
            "provide a JSON object with two keys: \n"
            "1. 'selection_reasoning': mapping key schema elements to the reason they were selected.\n"
            "2. 'example_questions': a list of 3-5 representative questions this agent could answer.\n"
            "Example:\n"
            "Prompt Text...\n"
            "---REASONING---\n"
            "{\"selection_reasoning\": {\"patients\": \"...\"}, \"example_questions\": [\"Count patients by gender\", \"...\"]}"
        )

        chain = prompt_template | self.llm
        response = chain.invoke({})
        full_text = response.content
        
        # Parse output
        if "---REASONING---" in full_text:
            parts = full_text.split("---REASONING---")
            prompt_content = parts[0].strip()
            try:
                reasoning_json = parts[1].strip()
                # fast cleanup if mardown code blocks are present
                reasoning_json = reasoning_json.replace("```json", "").replace("```", "").strip()
                try:
                    parsed = json.loads(reasoning_json)
                    # Handle both old format (direct dict) and new format (nested keys)
                    if "selection_reasoning" in parsed:
                        reasoning = parsed.get("selection_reasoning", {})
                        questions = parsed.get("example_questions", [])
                    else:
                        # Fallback for simple dict
                        reasoning = parsed
                        questions = []
                except:
                    reasoning = {}
                    questions = []
            except:
                reasoning = {}
                questions = []
        else:
            prompt_content = full_text
            reasoning = {}
            questions = []

        return {
            "draft_prompt": prompt_content, 
            "reasoning": reasoning,
            "example_questions": questions
        }

    def publish_system_prompt(self, prompt_text: str, user_id: str, 
                              connection_id: Optional[int] = None, 
                              schema_selection: Optional[str] = None, 
                              data_dictionary: Optional[str] = None):
        """Publish a new version of the system prompt."""
        return self.db_service.publish_system_prompt(prompt_text, user_id, connection_id, schema_selection, data_dictionary)

    def get_prompt_history(self):
        """Get history of all system prompts."""
        return self.db_service.get_all_prompts()

    def get_active_config(self) -> Optional[dict]:
        """Get the active prompt configuration."""
        return self.db_service.get_active_config()

# Singleton instance pattern not strictly requested but good practice if needed.
# For now, just the class is requested, but usually services are singletons or instantiated per request.
# The prompt asks to "Create a class ConfigService". 
# The API route will likely instantiate it.

def get_config_service() -> ConfigService:
    return ConfigService()
