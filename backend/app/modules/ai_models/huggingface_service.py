"""
HuggingFace Hub integration service.

Provides:
- Model search via HuggingFace Hub API
- Model info/metadata retrieval
- Model download with progress tracking

Uses the official huggingface_hub library for downloads.
"""
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any, Dict, Callable
import httpx

from app.core.settings import get_settings


# HuggingFace Hub API base URL
HF_API_BASE = "https://huggingface.co/api"


@dataclass
class HFModelInfo:
    """HuggingFace model information."""
    model_id: str  # e.g., 'BAAI/bge-base-en-v1.5'
    author: str  # e.g., 'BAAI'
    model_name: str  # e.g., 'bge-base-en-v1.5'
    pipeline_tag: Optional[str] = None  # e.g., 'sentence-similarity', 'text-generation'
    library_name: Optional[str] = None  # e.g., 'sentence-transformers', 'transformers'
    downloads: int = 0
    likes: int = 0
    trending_score: Optional[float] = None
    last_modified: Optional[datetime] = None
    tags: List[str] = None
    description: Optional[str] = None
    
    # Inferred fields
    model_type: Optional[str] = None  # 'llm', 'embedding', 'reranker'
    dimensions: Optional[int] = None  # For embedding models
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        self._infer_model_type()
    
    def _infer_model_type(self):
        """Infer model type from pipeline_tag and library_name."""
        if self.pipeline_tag:
            tag = self.pipeline_tag.lower()
            if tag in ('sentence-similarity', 'feature-extraction'):
                self.model_type = 'embedding'
            elif tag in ('text-generation', 'text2text-generation', 'conversational'):
                self.model_type = 'llm'
            elif tag in ('text-classification',) and 'rerank' in ' '.join(self.tags).lower():
                self.model_type = 'reranker'
        
        # Check library for additional hints
        if self.library_name:
            lib = self.library_name.lower()
            if 'sentence-transformers' in lib:
                self.model_type = self.model_type or 'embedding'
            elif lib in ('transformers', 'llama-cpp', 'exllama'):
                self.model_type = self.model_type or 'llm'


@dataclass
class HFSearchResult:
    """Search result from HuggingFace Hub."""
    models: List[HFModelInfo]
    total: int
    num_pages: int


class HuggingFaceHubService:
    """
    Service for interacting with HuggingFace Hub API.
    
    Example:
        service = HuggingFaceHubService()
        
        # Search for embedding models
        results = await service.search_models(
            query="bge embedding",
            model_type="embedding",
            limit=10
        )
        
        # Get model info
        info = await service.get_model_info("BAAI/bge-base-en-v1.5")
    """
    
    def __init__(self, hf_token: Optional[str] = None):
        """
        Initialize the service.
        
        Args:
            hf_token: Optional HuggingFace API token for private models
        """
        self.hf_token = hf_token or os.environ.get("HUGGINGFACE_TOKEN")
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            if self.hf_token:
                headers["Authorization"] = f"Bearer {self.hf_token}"
            
            self._client = httpx.AsyncClient(
                base_url=HF_API_BASE,
                headers=headers,
                timeout=30.0
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def search_models(
        self,
        query: str,
        model_type: Optional[str] = None,  # 'llm', 'embedding', 'reranker'
        limit: int = 20,
        sort: str = "downloads",  # 'downloads', 'likes', 'trending', 'lastModified'
        direction: str = "-1"  # '-1' descending, '1' ascending
    ) -> HFSearchResult:
        """
        Search for models on HuggingFace Hub.
        
        Args:
            query: Search query (e.g., 'bge embedding', 'llama 7b')
            model_type: Filter by type ('llm', 'embedding', 'reranker')
            limit: Maximum results to return
            sort: Sort field
            direction: Sort direction
            
        Returns:
            HFSearchResult with matching models
        """
        client = await self._get_client()
        
        # Build query parameters
        params = {
            "search": query,
            "limit": min(limit, 100),  # HF API limit
            "sort": sort,
            "direction": direction,
            "full": "true",  # Get full model info
        }
        
        # Map model_type to HF pipeline_tag filter
        if model_type:
            if model_type == 'embedding':
                params["filter"] = "sentence-similarity"
            elif model_type == 'llm':
                params["filter"] = "text-generation"
            elif model_type == 'reranker':
                # Rerankers don't have a specific filter, search with query
                params["search"] = f"{query} reranker"
        
        try:
            response = await client.get("/models", params=params)
            response.raise_for_status()
            data = response.json()
            
            models = []
            for item in data:
                model = self._parse_model_info(item)
                
                # Filter by model_type if specified
                if model_type and model.model_type != model_type:
                    # Try to infer from query
                    if model_type == 'reranker' and 'rerank' in model.model_id.lower():
                        model.model_type = 'reranker'
                    elif model.model_type is None:
                        continue
                
                models.append(model)
            
            return HFSearchResult(
                models=models,
                total=len(models),
                num_pages=1
            )
            
        except httpx.HTTPError as e:
            # Log error
            return HFSearchResult(models=[], total=0, num_pages=0)
    
    async def get_model_info(self, model_id: str) -> Optional[HFModelInfo]:
        """
        Get detailed info for a specific model.
        
        Args:
            model_id: Full model ID (e.g., 'BAAI/bge-base-en-v1.5')
            
        Returns:
            HFModelInfo or None if not found
        """
        client = await self._get_client()
        
        try:
            response = await client.get(f"/models/{model_id}")
            response.raise_for_status()
            data = response.json()
            return self._parse_model_info(data)
            
        except httpx.HTTPError:
            return None
    
    def _parse_model_info(self, data: Dict[str, Any]) -> HFModelInfo:
        """Parse API response into HFModelInfo."""
        model_id = data.get("modelId") or data.get("id", "")
        parts = model_id.split("/", 1)
        author = parts[0] if len(parts) > 1 else ""
        model_name = parts[1] if len(parts) > 1 else parts[0]
        
        # Parse last modified
        last_modified = None
        if "lastModified" in data:
            try:
                last_modified = datetime.fromisoformat(
                    data["lastModified"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        return HFModelInfo(
            model_id=model_id,
            author=author,
            model_name=model_name,
            pipeline_tag=data.get("pipeline_tag"),
            library_name=data.get("library_name"),
            downloads=data.get("downloads", 0),
            likes=data.get("likes", 0),
            trending_score=data.get("trendingScore"),
            last_modified=last_modified,
            tags=data.get("tags", []),
            description=data.get("description")
        )
    
    async def download_model(
        self,
        model_id: str,
        local_path: str,
        revision: str = "main",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        Download a model to local path.
        
        Uses huggingface_hub library for proper downloading with caching.
        
        Args:
            model_id: Full model ID (e.g., 'BAAI/bge-base-en-v1.5')
            local_path: Directory to save the model
            revision: Git revision/branch (default 'main')
            progress_callback: Optional callback(downloaded_bytes, total_bytes)
            
        Returns:
            True if download succeeded
        """
        try:
            from huggingface_hub import snapshot_download
            
            # Run in thread pool since snapshot_download is sync
            def _download():
                return snapshot_download(
                    repo_id=model_id,
                    local_dir=local_path,
                    revision=revision,
                    token=self.hf_token,
                    local_dir_use_symlinks=False,  # Copy files, don't symlink
                )
            
            loop = asyncio.get_event_loop()
            result_path = await loop.run_in_executor(None, _download)
            
            return Path(result_path).exists()
            
        except ImportError:
            # huggingface_hub not installed, try manual download
            return await self._manual_download(model_id, local_path, revision)
        except Exception as e:
            # Log error
            return False
    
    async def _manual_download(
        self,
        model_id: str,
        local_path: str,
        revision: str = "main"
    ) -> bool:
        """
        Fallback manual download without huggingface_hub library.
        
        Downloads essential files: config.json, model files, tokenizer files.
        """
        client = await self._get_client()
        base_url = f"https://huggingface.co/{model_id}/resolve/{revision}"
        
        essential_files = [
            "config.json",
            "tokenizer_config.json",
            "tokenizer.json",
            "vocab.txt",
            "special_tokens_map.json",
            "model.safetensors",
            "pytorch_model.bin",
        ]
        
        local_dir = Path(local_path)
        local_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded_any = False
        
        for filename in essential_files:
            try:
                response = await client.get(
                    f"{base_url}/{filename}",
                    follow_redirects=True,
                    timeout=300.0  # 5 min timeout for large files
                )
                if response.status_code == 200:
                    file_path = local_dir / filename
                    file_path.write_bytes(response.content)
                    downloaded_any = True
            except httpx.HTTPError:
                continue  # File doesn't exist or error
        
        return downloaded_any
    
    async def get_model_files(self, model_id: str) -> List[Dict[str, Any]]:
        """
        List files in a model repository.
        
        Args:
            model_id: Full model ID
            
        Returns:
            List of file info dicts with 'path', 'size', 'type'
        """
        client = await self._get_client()
        
        try:
            response = await client.get(f"/models/{model_id}/tree/main")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return []


# Singleton instance
_hf_service: Optional[HuggingFaceHubService] = None


def get_hf_service() -> HuggingFaceHubService:
    """Get or create the HuggingFace Hub service singleton."""
    global _hf_service
    if _hf_service is None:
        _hf_service = HuggingFaceHubService()
    return _hf_service
