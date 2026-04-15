"""
API routes for AI Models - Simplified Design.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.auth.permissions import get_current_user, require_admin
from app.modules.audit.helpers import AuditLogger, get_audit_logger
from app.modules.audit.schemas import AuditAction
from app.modules.users.schemas import User
from app.modules.ai_models.service import AIModelService
from app.modules.ai_models.schemas import (
    AIModelCreate, AIModelUpdate, AIModelResponse, AIModelListResponse,
    HFSearchRequest, HFSearchResponse, HFQuickAddRequest,
    DownloadProgressResponse, DefaultsResponse, SetDefaultRequest,
    AvailableModelsResponse
)


router = APIRouter(prefix="/ai-models", tags=["AI Models"])


# ==========================================
# Model CRUD
# ==========================================

@router.get("", response_model=AIModelListResponse)
async def list_models(
    model_type: Optional[str] = Query(None, description="Filter by model type (llm, embedding, reranker)"),
    provider_name: Optional[str] = Query(None, description="Filter by provider"),
    deployment_type: Optional[str] = Query(None, description="Filter by deployment (cloud, local)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """List all AI models."""
    service = AIModelService(db)
    return await service.list_models(
        model_type=model_type,
        provider_name=provider_name,
        deployment_type=deployment_type,
        is_active=is_active,
        skip=skip,
        limit=limit
    )


@router.post("", response_model=AIModelResponse)
async def create_model(
    data: AIModelCreate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """Create a new AI model."""
    service = AIModelService(db)
    try:
        model = await service.create_model(data, user.id)
        
        # Audit log: aimodel.registered
        await audit.log(
            action=AuditAction.AIMODEL_REGISTERED,
            actor=user,
            resource_type="aimodel",
            resource_id=str(model.id),
            resource_name=model.display_name or model.model_id,
            details={
                "provider": model.provider_name,
                "model_id": model.model_id,
                "model_type": model.model_type,
                "deployment_type": model.deployment_type,
                "registered_by": user.username
            },
        )
        
        return model
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/available", response_model=AvailableModelsResponse)
async def get_available_models(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Get models available for agent configuration."""
    service = AIModelService(db)
    return await service.get_available_models(model_type)


@router.get("/defaults", response_model=DefaultsResponse)
async def get_defaults(
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Get default models for each type."""
    service = AIModelService(db)
    return await service.get_defaults()


@router.put("/defaults/{model_type}", response_model=DefaultsResponse)
async def set_default(
    model_type: str,
    data: SetDefaultRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """Set default model for a type."""
    if model_type not in ['llm', 'embedding', 'reranker']:
        raise HTTPException(status_code=400, detail="Invalid model type")
    
    service = AIModelService(db)
    try:
        # Get previous default for audit log
        current_defaults = await service.get_defaults()
        previous_default = None
        if model_type == 'llm':
            previous_default = current_defaults.llm.display_name if current_defaults.llm else None
        elif model_type == 'embedding':
            previous_default = current_defaults.embedding.display_name if current_defaults.embedding else None
        elif model_type == 'reranker':
            previous_default = current_defaults.reranker.display_name if current_defaults.reranker else None
        
        result = await service.set_default(model_type, data.model_id)
        
        # Audit log: aimodel.set_as_default
        if data.model_id:
            model = await service.get_model(data.model_id)
            await audit.log(
                action=AuditAction.AIMODEL_SET_AS_DEFAULT,
                actor=user,
                resource_type="aimodel",
                resource_id=str(data.model_id),
                resource_name=model.display_name if model else str(data.model_id),
                details={
                    "model_type": model_type,
                    "previous_default": previous_default,
                    "set_by": user.username
                },
            )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/defaults/{model_type}", response_model=DefaultsResponse)
async def clear_default(
    model_type: str,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin)
):
    """Clear default model for a type."""
    if model_type not in ['llm', 'embedding', 'reranker']:
        raise HTTPException(status_code=400, detail="Invalid model type")
    
    service = AIModelService(db)
    return await service.set_default(model_type, None)


@router.get("/{model_id}", response_model=AIModelResponse)
async def get_model(
    model_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Get a specific AI model."""
    service = AIModelService(db)
    model = await service.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.patch("/{model_id}", response_model=AIModelResponse)
async def update_model(
    model_id: int,
    data: AIModelUpdate,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """Update an AI model."""
    service = AIModelService(db)
    model = await service.update_model(model_id, data)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Audit log: aimodel.updated
    # Build fields changed - exclude api_key value for security
    fields_changed = [k for k, v in data.model_dump(exclude_unset=True).items() if v is not None]
    if 'api_key' in fields_changed:
        fields_changed = [f if f != 'api_key' else 'api_key (updated)' for f in fields_changed]
    
    await audit.log(
        action=AuditAction.AIMODEL_UPDATED,
        actor=user,
        resource_type="aimodel",
        resource_id=str(model_id),
        resource_name=model.display_name or model.model_id,
        details={
            "fields_changed": fields_changed,
            "updated_by": user.username
        },
    )
    
    return model


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """Delete an AI model."""
    service = AIModelService(db)
    
    # Get model info before deletion for audit log
    model = await service.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    deleted = await service.delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Audit log: aimodel.deleted
    await audit.log(
        action=AuditAction.AIMODEL_DELETED,
        actor=user,
        resource_type="aimodel",
        resource_id=str(model_id),
        resource_name=model.display_name or model.model_id,
        details={
            "provider": model.provider_name,
            "model_id": model.model_id,
            "deleted_by": user.username
        },
    )
    
    return {"message": "Model deleted"}


# ==========================================
# HuggingFace Integration
# ==========================================

@router.post("/huggingface/search", response_model=HFSearchResponse)
async def search_huggingface(
    request: HFSearchRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Search HuggingFace Hub for models."""
    service = AIModelService(db)
    return await service.search_huggingface(request)


@router.post("/huggingface/quick-add", response_model=AIModelResponse)
async def quick_add_from_huggingface(
    request: HFQuickAddRequest,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin)
):
    """Quick-add a model from HuggingFace Hub."""
    service = AIModelService(db)
    try:
        return await service.quick_add_from_huggingface(request, user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================
# Downloads
# ==========================================

@router.post("/{model_id}/download", response_model=DownloadProgressResponse)
async def start_download(
    model_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin)
):
    """Start downloading a local model."""
    service = AIModelService(db)
    try:
        return await service.start_download(model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{model_id}/download", response_model=DownloadProgressResponse)
async def get_download_progress(
    model_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user)
):
    """Get download progress for a model."""
    service = AIModelService(db)
    progress = await service.get_download_progress(model_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Model not found")
    return progress


@router.delete("/{model_id}/download")
async def cancel_download(
    model_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin)
):
    """Cancel an in-progress download."""
    service = AIModelService(db)
    cancelled = await service.cancel_download(model_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"message": "Download cancelled"}
