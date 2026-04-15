"""
Repository for AI Models - Database operations.
"""
from typing import List, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_models.models import AIModel


class AIModelRepository:
    """Repository for AI model CRUD operations."""
    
    def __init__(self, session: AsyncSession):
        self.db = session
    
    async def create(self, model: AIModel) -> AIModel:
        """Create a new model."""
        self.db.add(model)
        await self.db.flush()
        await self.db.refresh(model)
        return model
    
    async def get_by_id(self, model_id: int) -> Optional[AIModel]:
        """Get model by ID."""
        result = await self.db.execute(
            select(AIModel).where(AIModel.id == model_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_model_id(self, model_id: str) -> Optional[AIModel]:
        """Get model by model_id string."""
        result = await self.db.execute(
            select(AIModel).where(AIModel.model_id == model_id)
        )
        return result.scalar_one_or_none()
    
    async def list(
        self,
        model_type: Optional[str] = None,
        provider_name: Optional[str] = None,
        deployment_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[AIModel], int]:
        """List models with filters."""
        query = select(AIModel)
        count_query = select(func.count(AIModel.id))
        
        # Apply filters
        conditions = []
        if model_type:
            conditions.append(AIModel.model_type == model_type)
        if provider_name:
            conditions.append(AIModel.provider_name == provider_name)
        if deployment_type:
            conditions.append(AIModel.deployment_type == deployment_type)
        if is_active is not None:
            conditions.append(AIModel.is_active == is_active)
        
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))
        
        # Get total
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Get paginated results
        query = query.order_by(AIModel.display_name).offset(skip).limit(limit)
        result = await self.db.execute(query)
        models = list(result.scalars().all())
        
        return models, total
    
    async def update(self, model: AIModel) -> AIModel:
        """Update a model."""
        await self.db.flush()
        await self.db.refresh(model)
        return model
    
    async def delete(self, model: AIModel) -> None:
        """Delete a model."""
        await self.db.delete(model)
        await self.db.flush()
    
    async def get_default(self, model_type: str) -> Optional[AIModel]:
        """Get default model for a type."""
        result = await self.db.execute(
            select(AIModel).where(
                and_(
                    AIModel.model_type == model_type,
                    AIModel.is_default == True,
                    AIModel.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_defaults(self) -> dict[str, Optional[AIModel]]:
        """Get all default models."""
        defaults = {}
        for model_type in ['llm', 'embedding', 'reranker']:
            defaults[model_type] = await self.get_default(model_type)
        return defaults
    
    async def set_default(self, model: AIModel) -> None:
        """Set model as default (clears other defaults of same type)."""
        # Clear existing default
        result = await self.db.execute(
            select(AIModel).where(
                and_(
                    AIModel.model_type == model.model_type,
                    AIModel.is_default == True
                )
            )
        )
        for existing in result.scalars().all():
            existing.is_default = False
        
        # Set new default
        model.is_default = True
        await self.db.flush()
    
    async def clear_default(self, model_type: str) -> None:
        """Clear default for a model type."""
        result = await self.db.execute(
            select(AIModel).where(
                and_(
                    AIModel.model_type == model_type,
                    AIModel.is_default == True
                )
            )
        )
        for model in result.scalars().all():
            model.is_default = False
        await self.db.flush()
    
    async def get_available(self, model_type: Optional[str] = None) -> List[AIModel]:
        """Get models available for agent config (active and ready)."""
        query = select(AIModel).where(AIModel.is_active == True)
        
        if model_type:
            query = query.where(AIModel.model_type == model_type)
        
        query = query.order_by(AIModel.model_type, AIModel.display_name)
        result = await self.db.execute(query)
        
        # Filter to ready models
        models = []
        for model in result.scalars().all():
            if model.is_ready:
                models.append(model)
        
        return models
    
    async def update_download_status(
        self,
        model: AIModel,
        status: str,
        progress: int = 0,
        error: Optional[str] = None,
        local_path: Optional[str] = None
    ) -> AIModel:
        """Update download status."""
        model.download_status = status
        model.download_progress = progress
        model.download_error = error
        if local_path:
            model.local_path = local_path
        await self.db.flush()
        await self.db.refresh(model)
        return model
