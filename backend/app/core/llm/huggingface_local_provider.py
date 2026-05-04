"""
HuggingFace Local LLM Provider.

Supports locally downloaded LLMs from HuggingFace Hub.
"""
import os
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from app.core.llm.base import LLMProvider

logger = get_logger(__name__)


class HuggingFaceLocalProvider(LLMProvider):
    """
    HuggingFace local LLM provider using langchain_huggingface.
    
    Supports: Llama, Mistral, Phi, Qwen, etc.
    """
    
    def __init__(
        self,
        model: str,
        local_path: Optional[str] = None,
        temperature: float = 0.0,
        max_new_tokens: int = 2048,
        device_map: str = "auto",
        **kwargs: Any
    ):
        self._model_name = model
        self._local_path = local_path
        self._temperature = temperature
        self._max_new_tokens = max_new_tokens
        self._device_map = device_map
        self._kwargs = kwargs
        self._llm: Optional[BaseChatModel] = None
        
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize using HuggingFacePipeline.from_model_id()."""
        try:
            from langchain_huggingface import HuggingFacePipeline, ChatHuggingFace
            
            # Use local path if exists, otherwise model name
            model_id = self._local_path if self._local_path and os.path.exists(self._local_path) else self._model_name
            
            pipeline_kwargs = {"max_new_tokens": self._max_new_tokens, "return_full_text": False}
            if self._temperature > 0:
                pipeline_kwargs.update({"temperature": self._temperature, "do_sample": True})
            
            logger.info(f"Loading HuggingFace model: {model_id}")
            
            llm = HuggingFacePipeline.from_model_id(
                model_id=model_id,
                task="text-generation",
                model_kwargs={"device_map": self._device_map, **self._kwargs},
                pipeline_kwargs=pipeline_kwargs,
            )
            
            self._llm = ChatHuggingFace(llm=llm)
            logger.info(f"HuggingFace provider initialized: {self._model_name}")
            
        except ImportError:
            raise ImportError("Install: pip install transformers accelerate torch langchain-huggingface")
    
    def get_langchain_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._init_llm()
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "huggingface"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": "huggingface",
            "model": self._model_name,
            "local_path": self._local_path,
            "temperature": self._temperature,
        }
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            if self._llm:
                self._llm.invoke("Hi")
                return {"healthy": True, "model": self._model_name}
            return {"healthy": False, "message": "Not initialized"}
        except Exception as e:
            return {"healthy": False, "message": str(e)}
