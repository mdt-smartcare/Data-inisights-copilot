"""
Ollama LLM Provider.

Supports local LLM inference via Ollama server.
Models: llama2, codellama, mistral, mixtral, etc.
"""
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel

from app.core.utils.logging import get_logger
from app.core.llm.base import LLMProvider

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    """
    Ollama LLM provider for local model inference.
    """
    
    def __init__(
        self,
        model: str = "llama2",
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        num_ctx: int = 4096,
        num_predict: int = 2048,
        **kwargs: Any
    ):
        """
        Initialize Ollama provider.
        
        Args:
            model: Model name (e.g., 'llama2', 'mistral', 'codellama')
            base_url: Ollama server URL (default: http://localhost:11434)
            temperature: Sampling temperature
            num_ctx: Context window size
            num_predict: Maximum tokens to generate
        """
        self._model_name = model
        self._base_url = base_url or "http://localhost:11434"
        self._temperature = temperature
        self._num_ctx = num_ctx
        self._num_predict = num_predict
        self._extra_kwargs = kwargs
        self._llm: Optional[BaseChatModel] = None
        
        self._init_llm()
    
    def _init_llm(self) -> None:
        """Initialize the ChatOllama instance."""
        try:
            from langchain_ollama import ChatOllama
            
            self._llm = ChatOllama(
                model=self._model_name,
                base_url=self._base_url,
                temperature=self._temperature,
                num_ctx=self._num_ctx,
                num_predict=self._num_predict,
                **self._extra_kwargs
            )
            
            logger.info(f"Ollama provider initialized: model={self._model_name}, url={self._base_url}")
            
        except ImportError:
            # Fallback to community package
            try:
                from langchain_community.chat_models import ChatOllama
                
                self._llm = ChatOllama(
                    model=self._model_name,
                    base_url=self._base_url,
                    temperature=self._temperature,
                    num_ctx=self._num_ctx,
                    num_predict=self._num_predict,
                    **self._extra_kwargs
                )
                
                logger.info(f"Ollama provider initialized (community): model={self._model_name}")
                
            except ImportError:
                raise ImportError(
                    "langchain-ollama package required. "
                    "Install with: pip install langchain-ollama"
                )
        except Exception as e:
            logger.error(f"Failed to initialize Ollama provider: {e}")
            raise
    
    def get_langchain_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._init_llm()
        return self._llm
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def get_config(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self._model_name,
            "base_url": self._base_url,
            "temperature": self._temperature,
            "num_ctx": self._num_ctx,
            "num_predict": self._num_predict,
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if Ollama server is reachable and model is available."""
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                if response.status_code != 200:
                    return {
                        "healthy": False,
                        "provider": self.provider_name,
                        "model": self._model_name,
                        "message": f"Ollama server returned {response.status_code}"
                    }
                
                models_data = response.json()
                available_models = [m["name"] for m in models_data.get("models", [])]
                
                model_available = any(
                    self._model_name == m or m.startswith(f"{self._model_name}:")
                    for m in available_models
                )
                
                if not model_available:
                    return {
                        "healthy": False,
                        "provider": self.provider_name,
                        "model": self._model_name,
                        "message": f"Model not found. Available: {available_models[:5]}",
                        "available_models": available_models,
                    }
                
                return {
                    "healthy": True,
                    "provider": self.provider_name,
                    "model": self._model_name,
                    "message": "Ollama server operational",
                    "available_models": available_models,
                }
                
        except Exception as e:
            return {
                "healthy": False,
                "provider": self.provider_name,
                "model": self._model_name,
                "message": str(e),
            }
