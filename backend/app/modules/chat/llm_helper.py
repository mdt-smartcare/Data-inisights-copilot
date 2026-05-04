"""
Chat LLM Helper — Centralized LLM provider for the chat module.

Fetches LLM configuration from ai_models table via AIModelService.
Supports agent-specific models or falls back to global defaults.

Usage:
    from app.modules.chat.llm_helper import LLMHelper
    
    # Create helper
    llm_helper = LLMHelper(db, agent_id)
    
    # Get LLM (fetches config on first call)
    llm = await llm_helper.get_llm()                 # temp=0.0 (default)
    llm = await llm_helper.get_llm(temperature=0.7)  # creative
"""
import os
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from app.core.settings import get_settings

logger = get_logger(__name__)


class LLMHelper:
    """
    Simple LLM helper — fetches config from DB on first use, provides LLMs on demand.
    
    Usage:
        llm_helper = LLMHelper(db, agent_id)
        llm = await llm_helper.get_llm(temperature=0.0)
    """
    
    def __init__(self, db_session, agent_id: Optional[int] = None):
        self._db = db_session
        self._agent_id = agent_id
        self._initialized = False
        # Config fields
        self._provider_name: str = ""
        self._model: str = ""
        self._api_key: Optional[str] = None
        self._api_base_url: Optional[str] = None
        self._local_path: Optional[str] = None
        self._is_local: bool = False
    
    async def get_llm(self, temperature: float = 0.0) -> BaseChatModel:
        """
        Get LLM with specified temperature.
        
        Args:
            temperature: 0.0 = deterministic, 0.7 = creative (default: 0.0)
        """
        logger.info(f"LLMHelper initialized: {self._initialized}")
        if not self._initialized:
            await self._fetch_config()
            self._initialized = True
        logger.info(f"LLMHelper initialized Completed: {self._initialized}")
        from app.core.llm import create_llm_provider
        
        provider_config: Dict[str, Any] = {
            "model": self._model,
            "temperature": temperature,
        }
        
        if self._api_key:
            provider_config["api_key"] = self._api_key
        if self._api_base_url:
            provider_config["base_url"] = self._api_base_url
        if self._provider_name == "huggingface" and self._local_path:
            provider_config["local_path"] = self._local_path
        
        logger.info(f"Creating LLM: {self._provider_name}/{self._model}, temp={temperature}")
        
        provider = create_llm_provider(self._provider_name, provider_config)
        return provider.get_langchain_llm()
    
    async def _fetch_config(self):
        """Fetch LLM config from DB or fallback to env."""
        settings = get_settings()
        
        try:
            from app.modules.ai_models.service import AIModelService
            ai_model_service = AIModelService(self._db)
            model_response = None
            logger.info(f"Fetching LLM config for agent_id={self._agent_id}")
            # Try agent-specific model
            if self._agent_id:
                from uuid import UUID
                from app.modules.agents.service import AgentConfigService
                
                agent_service = AgentConfigService(self._db)
                try:
                    agent_uuid = UUID(str(self._agent_id)) if not isinstance(self._agent_id, UUID) else self._agent_id
                    agent_config = await agent_service.get_active_config(agent_uuid)
                    logger.info(f"LLM Helper fetched agent config for agent_id={self._agent_id}: {agent_config}")
                    if agent_config and agent_config.llm_model_id:
                        model_response = await ai_model_service.get_model(agent_config.llm_model_id)
                except Exception as e:
                    logger.info(f"Failed to get agent config: {e}")
            
            # Fall back to global default
            if not model_response:
                defaults = await ai_model_service.get_defaults()
                model_response = defaults.llm
            
            if model_response:
                is_local = model_response.deployment_type == "local"
                if is_local and model_response.provider_name.lower() == "huggingface":
                    if model_response.download_status != "ready":
                        logger.warning("HuggingFace model not ready. Using fallback.")
                        self._set_fallback(settings)
                        return
                
                api_key = None
                if model_response.api_key_env_var:
                    api_key = os.environ.get(model_response.api_key_env_var)
                if not api_key:
                    api_key = settings.openai_api_key
                
                model_name = model_response.model_id.split("/", 1)[-1] if "/" in model_response.model_id else model_response.model_id
                logger.info(f"Using LLM: {model_response.provider_name}/{model_name}")
                
                self._provider_name = model_response.provider_name.lower()
                self._model = model_name
                self._api_key = api_key
                self._api_base_url = model_response.api_base_url
                self._local_path = model_response.local_path
                self._is_local = is_local
                return
                
        except Exception as e:
            logger.warning(f"Failed to fetch LLM config: {e}. Using fallback.")
        
        self._set_fallback(settings)
    
    def _set_fallback(self, settings):
        """Set fallback config from environment."""
        ollama_url = os.environ.get("OLLAMA_BASE_URL")
        ollama_model = os.environ.get("OLLAMA_MODEL")
        if ollama_url and ollama_model:
            self._provider_name = "ollama"
            self._model = ollama_model
            self._api_base_url = ollama_url
            self._is_local = True
            return
        
        self._provider_name = "openai"
        self._model = "gpt-4o-mini"
        self._api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    
    @property
    def provider_name(self) -> str:
        return self._provider_name
    
    @property
    def model_name(self) -> str:
        return self._model
    
    @property
    def is_local(self) -> bool:
        return self._is_local
