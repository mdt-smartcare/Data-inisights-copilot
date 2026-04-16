"""
Service layer for AI Models - Business logic.
"""
import os
import logging
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_value, decrypt_value
from app.core.settings import get_settings
from app.modules.ai_models.models import AIModel
from app.modules.ai_models.repository import AIModelRepository
from app.modules.ai_models.schemas import (
    AIModelCreate, AIModelUpdate, AIModelResponse, AIModelListResponse,
    HFSearchRequest, HFSearchResponse, HFModelInfo, HFQuickAddRequest,
    DownloadProgressResponse, DefaultsResponse, AvailableModel, AvailableModelsResponse
)
from app.modules.ai_models.huggingface_service import HuggingFaceHubService, get_hf_service
from app.modules.ai_models.download_manager import DownloadManager, get_download_manager

logger = logging.getLogger(__name__)


class AIModelService:
    """Service for AI model operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AIModelRepository(session)
        self.settings = get_settings()
    
    # ==========================================
    # Model CRUD
    # ==========================================
    
    async def create_model(self, data: AIModelCreate, user_id: Optional[str] = None) -> AIModelResponse:
        """Create a new AI model."""
        # Check if model_id already exists
        existing = await self.repo.get_by_model_id(data.model_id)
        if existing:
            raise ValueError(f"Model with ID '{data.model_id}' already exists")
        
        # Create model
        model = AIModel(
            model_id=data.model_id,
            display_name=data.display_name,
            model_type=data.model_type,
            provider_name=data.provider_name,
            deployment_type=data.deployment_type,
            api_base_url=data.api_base_url,
            api_key_env_var=data.api_key_env_var,
            local_path=data.local_path,
            hf_model_id=data.hf_model_id,
            hf_revision=data.hf_revision,
            context_length=data.context_length,
            max_input_tokens=data.max_input_tokens,
            dimensions=data.dimensions,
            recommended_chunk_size=data.recommended_chunk_size,
            compatibility_notes=data.compatibility_notes,
            description=data.description,
            is_default=data.is_default,
            created_by=user_id,
            # Local models start as not_downloaded
            download_status='not_downloaded' if data.deployment_type == 'local' else 'ready'
        )
        
        # Encrypt API key if provided
        if data.api_key:
            model.api_key_encrypted = encrypt_value(data.api_key)
        
        model = await self.repo.create(model)
        await self.session.commit()
        
        return self._to_response(model)
    
    async def get_model(self, model_id: int) -> Optional[AIModelResponse]:
        """Get model by ID."""
        model = await self.repo.get_by_id(model_id)
        if not model:
            return None
        return self._to_response(model)
    
    async def list_models(
        self,
        model_type: Optional[str] = None,
        provider_name: Optional[str] = None,
        deployment_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> AIModelListResponse:
        """List models with filters."""
        models, total = await self.repo.list(
            model_type=model_type,
            provider_name=provider_name,
            deployment_type=deployment_type,
            is_active=is_active,
            skip=skip,
            limit=limit
        )
        return AIModelListResponse(
            models=[self._to_response(m) for m in models],
            total=total
        )
    
    async def update_model(self, model_id: int, data: AIModelUpdate) -> Optional[AIModelResponse]:
        """Update a model."""
        model = await self.repo.get_by_id(model_id)
        if not model:
            return None
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        
        # Check model_id uniqueness if being changed
        if 'model_id' in update_data and update_data['model_id'] != model.model_id:
            existing = await self.repo.get_by_model_id(update_data['model_id'])
            if existing:
                raise ValueError(f"Model with ID '{update_data['model_id']}' already exists")
        
        # Handle API key separately
        if 'api_key' in update_data:
            api_key = update_data.pop('api_key')
            if api_key:
                model.api_key_encrypted = encrypt_value(api_key)
        
        for field, value in update_data.items():
            if hasattr(model, field):
                setattr(model, field, value)
        
        model = await self.repo.update(model)
        await self.session.commit()
        
        return self._to_response(model)
    
    async def delete_model(self, model_id: int) -> bool:
        """Delete a model."""
        model = await self.repo.get_by_id(model_id)
        if not model:
            return False
        
        await self.repo.delete(model)
        await self.session.commit()
        return True
    
    # ==========================================
    # Defaults
    # ==========================================
    
    async def get_defaults(self) -> DefaultsResponse:
        """Get default models for each type."""
        defaults = await self.repo.get_defaults()
        return DefaultsResponse(
            llm=self._to_response(defaults['llm']) if defaults['llm'] else None,
            embedding=self._to_response(defaults['embedding']) if defaults['embedding'] else None,
            reranker=self._to_response(defaults['reranker']) if defaults['reranker'] else None
        )
    
    async def set_default(self, model_type: str, model_id: Optional[int]) -> DefaultsResponse:
        """Set or clear default model for a type."""
        if model_id:
            model = await self.repo.get_by_id(model_id)
            if not model:
                raise ValueError(f"Model {model_id} not found")
            if model.model_type != model_type:
                raise ValueError(f"Model {model_id} is type '{model.model_type}', not '{model_type}'")
            await self.repo.set_default(model)
        else:
            await self.repo.clear_default(model_type)
        
        await self.session.commit()
        return await self.get_defaults()
    
    # ==========================================
    # Available Models (for agent config)
    # ==========================================
    
    async def get_available_models(self, model_type: Optional[str] = None) -> AvailableModelsResponse:
        """Get models available for agent configuration."""
        models = await self.repo.get_available(model_type)
        
        # Group by type
        result = {'llm': [], 'embedding': [], 'reranker': []}
        for model in models:
            item = AvailableModel(
                id=model.id,
                model_id=model.model_id,
                display_name=model.display_name,
                model_type=model.model_type,
                provider_name=model.provider_name,
                deployment_type=model.deployment_type,
                is_ready=model.is_ready,
                is_default=model.is_default,
                context_length=model.context_length,
                dimensions=model.dimensions
            )
            result[model.model_type].append(item)
        
        return AvailableModelsResponse(**result)
    
    # ==========================================
    # HuggingFace Search
    # ==========================================
    
    async def search_huggingface(self, request: HFSearchRequest) -> HFSearchResponse:
        """Search HuggingFace Hub for models."""
        hf_service = get_hf_service()
        
        hf_result = await hf_service.search_models(
            query=request.query,
            model_type=request.model_type,
            limit=request.limit
        )
        
        # Check which are already registered
        results = []
        for hf_model in hf_result.models:
            existing = await self.repo.get_by_model_id(f"huggingface/{hf_model.model_id}")
            
            # Suggest type based on pipeline tag
            suggested_type = None
            if hf_model.pipeline_tag:
                if hf_model.pipeline_tag in ['feature-extraction', 'sentence-similarity']:
                    suggested_type = 'embedding'
                elif hf_model.pipeline_tag in ['text-classification', 'text2text-generation']:
                    suggested_type = 'reranker'
                elif hf_model.pipeline_tag in ['text-generation', 'conversational']:
                    suggested_type = 'llm'
            
            results.append(HFModelInfo(
                model_id=hf_model.model_id,
                author=hf_model.author,
                model_name=hf_model.model_name,
                pipeline_tag=hf_model.pipeline_tag,
                downloads=hf_model.downloads,
                likes=hf_model.likes,
                last_modified=hf_model.last_modified.isoformat() if hf_model.last_modified else None,
                description=hf_model.description,
                suggested_type=suggested_type,
                is_registered=existing is not None
            ))
        
        return HFSearchResponse(models=results, total=len(results))
    
    async def quick_add_from_huggingface(
        self,
        request: HFQuickAddRequest,
        user_id: Optional[str] = None
    ) -> AIModelResponse:
        """Quick-add a model from HuggingFace."""
        hf_service = get_hf_service()
        
        # Get model info from HF
        hf_info = await hf_service.get_model_info(request.hf_model_id)
        if not hf_info:
            raise ValueError(f"Model '{request.hf_model_id}' not found on HuggingFace")
        
        # Generate model_id
        model_id = f"huggingface/{request.hf_model_id}"
        
        # Check if already exists
        existing = await self.repo.get_by_model_id(model_id)
        if existing:
            raise ValueError(f"Model '{model_id}' already registered")
        
        # Create model
        display_name = request.display_name or hf_info.model_name
        
        create_data = AIModelCreate(
            model_id=model_id,
            display_name=display_name,
            model_type=request.model_type,
            provider_name='huggingface',
            deployment_type='local',
            hf_model_id=request.hf_model_id,
            description=hf_info.description
        )
        
        response = await self.create_model(create_data, user_id)
        
        # Start download if requested
        if request.auto_download:
            await self.start_download(response.id)
        
        return response
    
    # ==========================================
    # Downloads
    # ==========================================
    
    async def start_download(self, model_id: int) -> DownloadProgressResponse:
        """Start downloading a local model."""
        model = await self.repo.get_by_id(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        
        if model.deployment_type != 'local':
            raise ValueError("Can only download local models")
        
        if not model.hf_model_id:
            raise ValueError("Model has no HuggingFace model ID for download")
        
        if model.download_status == 'downloading':
            raise ValueError("Download already in progress")
        
        # Update status to pending
        await self.repo.update_download_status(model, 'pending', 0)
        await self.session.commit()
        
        # Start background download
        download_manager = get_download_manager()
        await download_manager.start_download(
            model_id=model.id,
            hf_model_id=model.hf_model_id,
            local_path=model.local_path or f"./data/models/{model.hf_model_id}",
            revision=model.hf_revision or "main"
        )
        
        return DownloadProgressResponse(
            model_id=model.id,
            status='pending',
            progress=0
        )
    
    async def get_download_progress(self, model_id: int) -> Optional[DownloadProgressResponse]:
        """Get download progress for a model."""
        model = await self.repo.get_by_id(model_id)
        if not model:
            return None
        
        # Check download manager for live progress
        download_manager = get_download_manager()
        live_progress = download_manager.get_progress(model_id)
        queue_position = download_manager.get_queue_position(model_id)
        
        if live_progress:
            # Update database status
            await self.repo.update_download_status(
                model,
                live_progress.status,
                live_progress.progress_percent,
                live_progress.error_message,
                live_progress.local_path
            )
            await self.session.commit()
            
            # Return live progress directly (model object is stale)
            return DownloadProgressResponse(
                model_id=model.id,
                status=live_progress.status,
                progress=live_progress.progress_percent,
                error=live_progress.error_message,
                queue_position=queue_position
            )
        
        # No live progress - return stored status
        return DownloadProgressResponse(
            model_id=model.id,
            status=model.download_status,
            progress=model.download_progress,
            error=model.download_error,
            queue_position=queue_position
        )
    
    async def cancel_download(self, model_id: int) -> bool:
        """Cancel an in-progress download."""
        model = await self.repo.get_by_id(model_id)
        if not model:
            return False
        
        download_manager = get_download_manager()
        await download_manager.cancel_download(model_id)
        
        await self.repo.update_download_status(model, 'not_downloaded', 0)
        await self.session.commit()
        
        return True
    
    # ==========================================
    # API Key Retrieval (for RAG service)
    # ==========================================
    
    def get_api_key(self, model: AIModel) -> Optional[str]:
        """Get decrypted API key for a model."""
        # Try env var first
        if model.api_key_env_var:
            env_key = os.environ.get(model.api_key_env_var)
            if env_key:
                return env_key
        
        # Try encrypted key
        if model.api_key_encrypted:
            return decrypt_value(model.api_key_encrypted)
        
        return None
    
    # ==========================================
    # Helpers
    # ==========================================
    
    def _to_response(self, model: AIModel) -> AIModelResponse:
        """Convert model to response schema."""
        return AIModelResponse(
            id=model.id,
            model_id=model.model_id,
            display_name=model.display_name,
            model_type=model.model_type,
            provider_name=model.provider_name,
            deployment_type=model.deployment_type,
            api_base_url=model.api_base_url,
            has_api_key=model.has_api_key,
            api_key_env_var=model.api_key_env_var,
            local_path=model.local_path,
            download_status=model.download_status,
            download_progress=model.download_progress,
            download_error=model.download_error,
            hf_model_id=model.hf_model_id,
            hf_revision=model.hf_revision,
            context_length=model.context_length,
            max_input_tokens=model.max_input_tokens,
            dimensions=model.dimensions,
            recommended_chunk_size=model.recommended_chunk_size,
            compatibility_notes=model.compatibility_notes,
            is_active=model.is_active,
            is_default=model.is_default,
            is_ready=model.is_ready,
            description=model.description,
            created_at=model.created_at,
            updated_at=model.updated_at,
            created_by=model.created_by
        )
