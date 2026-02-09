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
        system_role = "You are a Data Architect and AI System Prompt Engineer."
        # Standard Chart Rules to append (Single Source of Truth)
        standard_chart_rules = """
        CHART GENERATION RULES:
        1. Generate a chart_json for every query that returns data.
        2. Use 'treemap' for distributions by location (e.g., country, site).
        3. Use 'radar' for comparing entities across multiple metrics.
        4. Use 'scorecard' for single statistics or summary data.
        5. Avoid using 'bar' or 'pie' for location distributions; use 'treemap' instead.
        6. For "Scorecard" charts, provide clear labels and values for each metric.
        7. For "Radar" charts, compare entities across variables.
        8. For "Treemap" charts, visualize hierarchical or categorical distributions.

        JSON FORMAT:ß
        You MUST append a single JSON block at the end of your response:
        ```json
        {
            "chart_json": {
                "title": "...",
                "type": "radar|scorecard|treemap|bar|line|pie",
                "data": { "labels": ["..."], "values": [10, 20] }
            }
        }
        ```
        IMPORTANT: DO NOT use Chart.js structure (datasets). Use simple "values" array matching the "labels" array.
        """

        instruction = (
            "Your task is to write a comprehensive SYSTEM PROMPT for an AI assistant that will query a structured database.\\n\\n"
            "CONTEXT PROVIDED:\\n"
            f"{data_dictionary}\\n\\n"
            "INSTRUCTIONS:\\n"
            "1. Define a suitable persona based strictly on the table names and column definitions provided in the context.\\n"
            "2. List the KEY tables and columns available based on the context above.\\n"
            "3. Define strict rules for SQL generation (e.g., joins, filters).\\n"
            "   - When multiple specific entities are mentioned (e.g., 'at Site A and Site B'), Use 'GROUP BY' to provide a breakdown/comparison, NOT a single total sum.\\n"
            "4. **OUTPUT FORMAT:**\\n"
            "   - Do NOT include generic chart generation rules or JSON formats in your output (these will be appended automatically).\\n"
            "   - Focus on domain-specific examples and logic.\\n"
            "5. Return ONLY the prompt text (Persona + SQL Rules), no markdown formatting."
        )

        # Construct the prompt template
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_role),
            ("user", instruction)
        ])

        # Invoke the LLM
        # We want the LLM to explain WHY it prioritized certain tables
        instruction += (
            "\n\nAlso, at the end of your response, strictly separated by '---REASONING---', "
            "provide a JSON object with two keys: \n"
            "1. 'selection_reasoning': mapping key schema elements (table names or table.column) to the reason they were selected.\n"
            "2. 'example_questions': a list of 3-5 representative questions this agent could answer.\n"
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
                # fast cleanup if markdown code blocks are present
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
                except json.JSONDecodeError:
                    logger.warning("Failed to parse reasoning JSON: Invalid JSON")
                    reasoning = {}
                    questions = []
            except Exception as e:
                logger.warning(f"Error parsing reasoning section: {e}")
                reasoning = {}
                questions = []
        else:
            prompt_content = full_text
            reasoning = {}
            questions = []

        # Append standard chart rules
        if "CHART GENERATION RULES" not in prompt_content:
            prompt_content += "\n\n" + standard_chart_rules

        return {
            "draft_prompt": prompt_content, 
            "reasoning": reasoning,
            "example_questions": questions
        }

    def publish_system_prompt(self, prompt_text: str, user_id: str, 
                              connection_id: Optional[int] = None, 
                              schema_selection: Optional[str] = None, 
                              data_dictionary: Optional[str] = None,
                              reasoning: Optional[str] = None,
                              example_questions: Optional[str] = None) -> Dict[str, Any]:
        """
        Publishes a drafted system prompt as the new active version.
        Includes optional configuration metadata for reproducibility and explainability.
        """
        return self.db_service.publish_system_prompt(
            prompt_text, 
            user_id, 
            connection_id, 
            schema_selection, 
            data_dictionary,
            reasoning,
            example_questions
        )

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
