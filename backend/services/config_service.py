"""
Configuration Service for Data Insights AI-Copilot.

This service provides:
- System prompt generation and management
- Access to runtime-configurable settings from database (via SettingsService)
- Operational configuration access (chunking, PII rules, medical context)
- Hot-reload support: automatically invalidates cache when settings change

IMPORTANT: This service reads configuration from the database (system_settings table),
NOT from static YAML files. The database is the single source of truth.
"""
from typing import Optional, Dict, Any, List
import json
from langchain.prompts import ChatPromptTemplate
from backend.core.logging import get_logger
from backend.services.settings_service import get_settings_service, SettingsService
from backend.sqliteDb.db import get_db_service
import os
from dotenv import load_dotenv

logger = get_logger(__name__)


# Categories that ConfigService cares about for hot-reload
OPERATIONAL_CONFIG_CATEGORIES = {
    'chunking', 'data_privacy', 'medical_context', 'vector_store',
    'embedding', 'rag'
}


class ConfigService:
    """
    Configuration service for managing system prompts and runtime settings.
    
    All configuration is read from the database via SettingsService,
    which provides TTL-cached access to prevent database hammering.
    
    HOT-RELOAD: This service registers as a listener with SettingsService
    to immediately invalidate its internal cache when settings change.
    """
    
    def __init__(self, settings_service: Optional[SettingsService] = None):
        """
        Initialize ConfigService.
        
        Args:
            settings_service: Optional SettingsService instance for dependency injection.
                            If not provided, uses the singleton.
        """
        load_dotenv()
        self.config = {
            "db_url": os.getenv("DATABASE_URL"),
            "jwt_secret": os.getenv("JWT_SECRET"),
            "debug": os.getenv("DEBUG", "False").lower() in ("true", "1", "t"),
        }
        self._sql_service = None
        self._llm = None
        self.db_service = get_db_service()
        self._settings_service = settings_service
        self._config_cache: Dict[str, Any] = {}
        self._cache_valid = False
        
        # Register for hot-reload notifications
        self._register_for_updates()

    def _register_for_updates(self):
        """Register as a listener with SettingsService for hot-reload support."""
        try:
            self.settings_service.register_listener(self._on_settings_changed)
            logger.info("ConfigService registered for settings change notifications")
        except Exception as e:
            logger.warning(f"Failed to register for settings updates: {e}")

    def _on_settings_changed(self, category: str, updated_keys: List[str], updated_by: str):
        """
        Callback invoked when settings change.
        
        This enables hot-reloading: the next ingestion job will use
        the new parameters without requiring a server restart.
        
        Args:
            category: The category of settings that changed
            updated_keys: List of keys that were updated
            updated_by: Username who made the change
        """
        if category in OPERATIONAL_CONFIG_CATEGORIES:
            logger.info(
                f"Hot-reload triggered: {category}.{updated_keys} changed by {updated_by}. "
                "ConfigService cache invalidated."
            )
            self._invalidate_cache()

    def _invalidate_cache(self):
        """Invalidate the internal configuration cache."""
        self._config_cache = {}
        self._cache_valid = False

    @property
    def settings_service(self) -> SettingsService:
        """Lazy initialization of settings service."""
        if self._settings_service is None:
            self._settings_service = get_settings_service()
            # Register for updates if we just initialized
            self._settings_service.register_listener(self._on_settings_changed)
        return self._settings_service

    @property
    def sql_service(self):
        """Lazy initialization of SQL service (PostgreSQL connection)."""
        if self._sql_service is None:
            from backend.services.sql_service import get_sql_service
            self._sql_service = get_sql_service()
        return self._sql_service

    @property
    def llm(self):
        """Lazy initialization of LLM.
        
        Gets LLM directly from the LLM registry to avoid initializing
        AgentService (which requires a database connection).
        This allows prompt generation to work before a config is published.
        """
        if self._llm is None:
            from backend.services.llm_registry import get_llm_registry
            llm_registry = get_llm_registry()
            provider = llm_registry.get_active_provider()
            self._llm = provider.get_langchain_llm()
        return self._llm

    # =========================================================================
    # Operational Configuration Access (from database via SettingsService)
    # =========================================================================

    def get_chunking_params(self) -> Dict[str, Any]:
        """
        Get chunking parameters from database.
        
        Returns:
            Dict with keys: parent_chunk_size, parent_chunk_overlap,
                          child_chunk_size, child_chunk_overlap, min_chunk_length
        """
        return self.settings_service.get_category_settings_raw('chunking')

    def get_pii_rules(self) -> Dict[str, Any]:
        """
        Get PII protection rules from database.
        
        Returns:
            Dict with keys: global_exclude_columns, exclude_tables, table_specific_exclusions
        """
        return self.settings_service.get_category_settings_raw('data_privacy')

    def get_medical_context(self) -> Dict[str, Any]:
        """
        Get medical context settings from database.
        
        Returns:
            Dict with keys: terminology_mappings, clinical_flag_prefixes
        """
        return self.settings_service.get_category_settings_raw('medical_context')

    def get_vector_store_config(self) -> Dict[str, Any]:
        """
        Get vector store configuration from database.
        
        Returns:
            Dict with keys: type, default_collection, chroma_base_path
        """
        return self.settings_service.get_category_settings_raw('vector_store')

    def get_embedding_config(self) -> Dict[str, Any]:
        """
        Get embedding model configuration from database.
        
        Returns:
            Dict with keys: provider, model_name, model_path, batch_size, dimensions
        """
        return self.settings_service.get_category_settings_raw('embedding')

    def get_rag_config(self) -> Dict[str, Any]:
        """
        Get RAG pipeline configuration from database.
        
        Returns:
            Dict with keys: top_k_initial, top_k_final, hybrid_weights,
                          rerank_enabled, reranker_model, chunk_size, chunk_overlap
        """
        return self.settings_service.get_category_settings_raw('rag')

    def get_full_embedding_pipeline_config(self) -> Dict[str, Any]:
        """
        Get complete embedding pipeline configuration.
        
        This combines all operational settings needed for the embedding pipeline
        into a single unified configuration dictionary.
        
        Returns:
            Complete configuration dictionary with all pipeline settings
        """
        chunking = self.get_chunking_params()
        pii_rules = self.get_pii_rules()
        medical_context = self.get_medical_context()
        vector_store = self.get_vector_store_config()
        embedding = self.get_embedding_config()
        rag = self.get_rag_config()

        return {
            'embedding': embedding,
            'chunking': chunking,
            'vector_store': vector_store,
            'retriever': {
                'top_k_initial': rag.get('top_k_initial', 50),
                'top_k_final': rag.get('top_k_final', 10),
                'hybrid_search_weights': rag.get('hybrid_weights', [0.75, 0.25]),
                'rerank_enabled': rag.get('rerank_enabled', True),
                'reranker_model_name': rag.get('reranker_model', 'BAAI/bge-reranker-base'),
            },
            'tables': {
                'global_exclude_columns': pii_rules.get('global_exclude_columns', []),
                'exclude_tables': pii_rules.get('exclude_tables', []),
                'table_specific_exclusions': pii_rules.get('table_specific_exclusions', {}),
            },
            'medical_context': medical_context.get('terminology_mappings', {}),
            'clinical_flag_prefixes': medical_context.get('clinical_flag_prefixes', []),
            'text_processing': {
                'min_chunk_length': chunking.get('min_chunk_length', 50),
            },
        }

    # =========================================================================
    # Update Methods (with hot-reload via SettingsService)
    # =========================================================================

    def merge_with_overrides(self, override_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Merge database defaults with optional ad-hoc overrides.
        
        This is used for Phase 3: Payload Injection - allowing users to run
        specific ingestion jobs with custom settings without changing global defaults.
        
        Args:
            override_config: Optional dict with override values. Keys can include:
                - parent_chunk_size, parent_chunk_overlap, child_chunk_size, etc.
                - exclude_columns, exclude_tables
                - batch_size
                
        Returns:
            Complete configuration dict with overrides applied on top of defaults
        """
        # Get all defaults from database
        base_config = self.get_full_embedding_pipeline_config()
        
        if not override_config:
            return base_config
        
        # Apply chunking overrides
        chunking_keys = ['parent_chunk_size', 'parent_chunk_overlap', 
                        'child_chunk_size', 'child_chunk_overlap', 'min_chunk_length']
        for key in chunking_keys:
            if key in override_config and override_config[key] is not None:
                base_config['chunking'][key] = override_config[key]
        
        # Apply PII/table overrides
        if 'exclude_columns' in override_config and override_config['exclude_columns'] is not None:
            base_config['tables']['global_exclude_columns'] = override_config['exclude_columns']
        
        if 'exclude_tables' in override_config and override_config['exclude_tables'] is not None:
            base_config['tables']['exclude_tables'] = override_config['exclude_tables']
        
        # Apply embedding overrides
        if 'batch_size' in override_config and override_config['batch_size'] is not None:
            base_config['embedding']['batch_size'] = override_config['batch_size']
        
        logger.info(f"Config merged with overrides: {list(override_config.keys())}")
        return base_config

    def update_chunking_params(
        self, 
        settings: Dict[str, Any], 
        updated_by: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update chunking parameters.
        
        Hot-reload: Changes take effect immediately for the next ingestion job.
        
        Args:
            settings: Dict with chunking parameters to update
            updated_by: Username making the change
            reason: Optional reason for the change
            
        Returns:
            Updated chunking settings
        """
        return self.settings_service.update_category_settings(
            'chunking', settings, updated_by, reason
        )

    def update_pii_rules(
        self, 
        settings: Dict[str, Any], 
        updated_by: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update PII protection rules.
        
        Hot-reload: Changes take effect immediately for the next ingestion job.
        
        Args:
            settings: Dict with PII rules to update
            updated_by: Username making the change
            reason: Optional reason for the change
            
        Returns:
            Updated PII settings
        """
        return self.settings_service.update_category_settings(
            'data_privacy', settings, updated_by, reason
        )

    def update_medical_context(
        self, 
        settings: Dict[str, Any], 
        updated_by: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update medical context settings.
        
        Hot-reload: Changes take effect immediately for the next ingestion job.
        
        Args:
            settings: Dict with medical context to update
            updated_by: Username making the change
            reason: Optional reason for the change
            
        Returns:
            Updated medical context settings
        """
        return self.settings_service.update_category_settings(
            'medical_context', settings, updated_by, reason
        )

    def update_vector_store_config(
        self, 
        settings: Dict[str, Any], 
        updated_by: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update vector store configuration.
        
        Hot-reload: Changes take effect immediately for the next ingestion job.
        
        Args:
            settings: Dict with vector store settings to update
            updated_by: Username making the change
            reason: Optional reason for the change
            
        Returns:
            Updated vector store settings
        """
        return self.settings_service.update_category_settings(
            'vector_store', settings, updated_by, reason
        )

    # =========================================================================
    # System Prompt Generation
    # =========================================================================

    def generate_draft_prompt(self, data_dictionary: str, data_source_type: str = 'database') -> Dict[str, Any]:
        """
        Generates a draft system prompt based on the provided data dictionary / context.
        
        Args:
            data_dictionary: A string containing schema info, selected tables, and user notes.
                             (Constructed by the frontend wizard)
            data_source_type: The type of data source ('database' or 'file').
        """
        system_role = "You are a Data Architect and AI System Prompt Engineer."
        
        # IMPORTANT: Escape curly braces in data_dictionary to prevent format string errors
        # This is necessary because ChatPromptTemplate uses {} for variable substitution
        safe_data_dictionary = data_dictionary.replace("{", "{{").replace("}", "}}")
        
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

        JSON FORMAT:
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

        if data_source_type == 'file':
            instruction = (
                "Your task is to write a comprehensive SYSTEM PROMPT for an AI assistant that will answer questions based on a set of provided documents.\n\n"
                "DOCUMENT CONTENT PROVIDED:\n"
                f"{safe_data_dictionary}\n\n"
                "INSTRUCTIONS:\n"
                "1. Define a suitable persona based strictly on the content provided in the context above.\n"
                "2. Summarize the key topics and types of information available in the documents.\n"
                "3. Define strict rules for answering questions.\n"
                "   - Instruct the assistant to only answer based on the provided text.\n"
                "   - If the answer is not in the text, instruct the assistant to say it does not know.\n"
                "4. **OUTPUT FORMAT:**\n"
                "   - Do NOT include generic chart generation rules or JSON formats in your output (these will be appended automatically).\n"
                "5. Return ONLY the prompt text (Persona + Extraction Rules), no markdown formatting."
            )
        else:
            instruction = (
                "Your task is to write a comprehensive SYSTEM PROMPT for an AI assistant that will query a structured database.\n\n"
                "CONTEXT PROVIDED:\n"
                f"{safe_data_dictionary}\n\n"
                "INSTRUCTIONS:\n"
                "1. Define a suitable persona based strictly on the table names and column definitions provided in the context.\n"
                "2. List the KEY tables and columns available based on the context above.\n"
                "3. Define strict rules for SQL generation (e.g., joins, filters).\n"
                "   - When multiple specific entities are mentioned (e.g., 'at Site A and Site B'), Use 'GROUP BY' to provide a breakdown/comparison, NOT a single total sum.\n"
                "4. **OUTPUT FORMAT:**\n"
                "   - Do NOT include generic chart generation rules or JSON formats in your output (these will be appended automatically).\n"
                "   - Focus on domain-specific examples and logic.\n"
                "5. Return ONLY the prompt text (Persona + SQL Rules), no markdown formatting."
            )

        # Add reasoning request to instruction
        instruction += (
            "\n\nAlso, at the end of your response, strictly separated by '---REASONING---', "
            "provide a JSON object with two keys: \n"
            "1. 'selection_reasoning': mapping key schema/document elements to the reason they were selected.\n"
            "2. 'example_questions': a list of 3-5 representative questions this agent could answer.\n"
        )

        # Use direct message objects to avoid format string issues with ChatPromptTemplate
        from langchain.schema import HumanMessage, SystemMessage
        
        messages = [
            SystemMessage(content=system_role),
            HumanMessage(content=instruction)
        ]

        # Invoke the LLM directly with messages
        response = self.llm.invoke(messages)
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

    # =========================================================================
    # System Prompt Publishing
    # =========================================================================

    def publish_system_prompt(self, prompt_text: str, user_id: str, 
                              connection_id: Optional[int] = None, 
                              schema_selection: Optional[str] = None, 
                              data_dictionary: Optional[str] = None,
                              reasoning: Optional[str] = None,
                              example_questions: Optional[str] = None,
                              embedding_config: Optional[str] = None,
                              retriever_config: Optional[str] = None,
                              chunking_config: Optional[str] = None,
                              llm_config: Optional[str] = None,
                              agent_id: Optional[int] = None,
                              data_source_type: str = 'database',
                              ingestion_documents: Optional[str] = None,
                              ingestion_file_name: Optional[str] = None,
                              ingestion_file_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Publishes a drafted system prompt as the new active version.
        Includes optional configuration metadata for reproducibility and explainability.
        """
        # Register Vector DB if provided in embedding_config
        if embedding_config:
            import json
            try:
                emb_conf = json.loads(embedding_config)
                vector_db_name = emb_conf.get("vectorDbName")
                if vector_db_name:
                    data_source_id = str(connection_id) if data_source_type == 'database' else (ingestion_file_name or "unknown")
                    try:
                        self.db_service.register_vector_db(vector_db_name, data_source_id, user_id)
                    except ValueError:
                        # Already exists, which is fine if they are republishing with the same name
                        pass
            except Exception as e:
                logger.warning(f"Failed to register vector DB from config: {e}")

        return self.db_service.publish_system_prompt(
            prompt_text, 
            user_id, 
            connection_id, 
            schema_selection, 
            data_dictionary,
            reasoning,
            example_questions,
            embedding_config=embedding_config,
            retriever_config=retriever_config,
            chunking_config=chunking_config,
            llm_config=llm_config,
            agent_id=agent_id,
            data_source_type=data_source_type,
            ingestion_documents=ingestion_documents,
            ingestion_file_name=ingestion_file_name,
            ingestion_file_type=ingestion_file_type
        )

    # =========================================================================
    # Prompt History & Active Config
    # =========================================================================

    def get_prompt_history(self, agent_id: Optional[int] = None):
        """Get history of all system prompts."""
        return self.db_service.get_all_prompts(agent_id=agent_id)

    def get_active_config(self, agent_id: Optional[int] = None) -> Optional[dict]:
        """Get the active prompt configuration."""
        return self.db_service.get_active_config(agent_id=agent_id)


# =========================================================================
# Singleton Pattern
# =========================================================================

_config_service: Optional[ConfigService] = None


def get_config_service() -> ConfigService:
    """Get the singleton ConfigService instance."""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service
