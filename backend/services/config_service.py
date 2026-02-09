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
        instruction = (
            "Your task is to write a comprehensive SYSTEM PROMPT for an AI assistant that will query a structured database.\\n\\n"
            "CONTEXT PROVIDED:\\n"
            f"{data_dictionary}\\n\\n"
            "INSTRUCTIONS:\\n"
            "1. Define a suitable persona based strictly on the table names and column definitions provided in the context.\\n"
            "2. List the KEY tables and columns available based on the context above.\\n"
            "3. Define strict rules for SQL generation (e.g., joins, filters).\\n"
            "   - When multiple specific entities are mentioned (e.g., 'at Site A and Site B'), Use 'GROUP BY' to provide a breakdown/comparison, NOT a single total sum.\\n"
            "4. **CHART GENERATION RULES (STRICT):\\n"
            "1. **MANDATORY**: You MUST generate a chart_json for EVERY query that returns data. NEVER skip it.\\n"
            "2. **CHART PREFERENCES** (Override default choices):\\n"
            "   - IF data shows a distribution by LOCATION (Region, District, Site), USE 'treemap' INSTEAD of 'bar' or 'pie'.\\n"
            "   - IF data compares entities across multiple metrics, USE 'radar'.\\n"
            "   - IF data is a single number or summary, USE 'scorecard'.\\n"
            "3. **DATA QUALITY**: Plot whatever data you have, even if sparse. Do not apologize for missing data in the chart.\\n"
            "4. **NEGATIVE CONSTRAINTS (STRICT):**\\n"
            "   - DO NOT use 'bar' or 'pie' for Location/District/Region distributions. YOU MUST USE 'treemap'.\\n"
            "   - DO NOT Use 'bar' for single statistics. Use 'scorecard'.\\n"
            "5. For \"Scorecard\" (KPIs):\\n"
            "   - Use for single values: \"Total patients is 50\" -> Label: \"Total Patients\", Value: 50.\\n"
            "   - Use for summaries: \"Avg wait time 30m, Total 10\" -> 2 metrics.\\n"
            "   - Schema: {{ \"chart_json\": {{ \"type\": \"scorecard\", \"metrics\": [ {{ \"label\": \"...\", \"value\": \"...\" }} ] }} }}\\n"
            "3. For \"Radar\":\\n"
            "   - Use for comparing entities (A vs B) across variables.\\n"
            "4. For \"Treemap\":\\n"
            "   - Use for hierarchical or categorical distributions.\\n\\n"
            "JSON FORMAT:\\n"
            "You MUST append a single JSON block at the end of your response:\\n"
            "```json\\n"
            "{{\\n"
            "    \\\"chart_json\\\": {{\\n"
            "        \\\"title\\\": \\\"...\\\",\\n"
            "        \\\"type\\\": \\\"radar|scorecard|treemap|bar|line|pie\\\",\\n"
            "        \\\"data\\\": {{ ... }}\\n"
            "    }}\\n"
            "}}\\n"
            "```\\n"
            "If no chart is requested, omit the JSON.\\n"
            "Chart type guidelines:\\n"
            "- Use \\\"pie\\\" for: distributions, proportions (2-6 categories)\\n"
            "- Use \\\"bar\\\" for: comparisons, counts by category, rankings\\n"
            "- Use \\\"line\\\" for: trends over time\\n"
            "- Use \\\"scorecard\\\" for: high-level KPIs, summary stats, headline numbers (e.g., Total Patients, Average Wait Time)\\n"
            "- Use \\\"radar\\\" for: multi-variable comparison of entities (e.g., Hospital A vs B across 5 metrics)\\n"
            "- Use \\\"treemap\\\" for: hierarchical data or visualizing proportions of a whole with many categories\\n\\n"
            "FEW-SHOT EXAMPLES:\\n"
            "user: \"Show distribution of patients by District\"\\n"
            "assistant: ... \\\"chart_json\\\": {{ \\\"type\\\": \\\"treemap\\\", ... }}\\n\\n"
            "user: \"Total active patients\"\\n"
            "assistant: ... \\\"chart_json\\\": {{ \\\"type\\\": \\\"scorecard\\\", ... }}\\n\\n"
            "user: \"Compare Clinic A and Clinic B\"\\n"
            "assistant: ... \\\"chart_json\\\": {{ \\\"type\\\": \\\"bar\\\", ... }}\\n\\n"
            "5. Return ONLY the prompt text, no markdown formatting."
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
            "1. 'selection_reasoning': mapping key schema elements (table names or table.column) to the reason they were selected.\n"
            "2. 'example_questions': a list of 3-5 representative questions this agent could answer.\n"
            "Example:\n"
            "Prompt Text...\n"
            "---REASONING---\n"
            "{\"selection_reasoning\": {\"patients\": \"Contains core demographics needed for most queries\", \"visits.admission_date\": \"Required for timeline analysis\"}, \"example_questions\": [\"Count patients by gender\", \"What is the average length of stay?\"]}"
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
