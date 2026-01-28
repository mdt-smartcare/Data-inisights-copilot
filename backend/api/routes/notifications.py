"""
API routes for notification management.
Handles notification retrieval, preferences, and status updates.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status

from backend.models.schemas import User
from backend.models.rag_models import (
    Notification, NotificationPreferences, NotificationPreferencesUpdate,
    NotificationStatus
)
from backend.services.notification_service import get_notification_service, NotificationService
from backend.core.permissions import get_current_user
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[Notification])
async def get_notifications(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """
    Get notifications for the current user.
    
    Args:
        status_filter: Optional filter by status (unread, read, dismissed)
        limit: Maximum notifications to return
        offset: Pagination offset
    """
    # Parse status filter
    status_enum = None
    if status_filter:
        try:
            status_enum = NotificationStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}. Must be one of: unread, read, dismissed"
            )
    
    notifications = notification_service.get_user_notifications(
        user_id=current_user.id,
        status=status_enum,
        limit=limit,
        offset=offset
    )
    
    return notifications


@router.get("/unread-count", response_model=Dict[str, int])
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get count of unread notifications for the current user."""
    count = notification_service.get_unread_count(current_user.id)
    return {"count": count}


@router.get("/{notification_id}", response_model=Notification)
async def get_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get a specific notification."""
    notification = notification_service.get_notification(notification_id)
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    # Verify ownership
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access notifications of other users"
        )
    
    return notification


@router.post("/{notification_id}/read", response_model=Dict[str, bool])
async def mark_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Mark a notification as read."""
    success = notification_service.mark_as_read(notification_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or not owned by user"
        )
    
    return {"success": True}


@router.post("/read-all", response_model=Dict[str, Any])
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Mark all user's notifications as read."""
    count = notification_service.mark_all_as_read(current_user.id)
    return {"success": True, "marked_count": count}


@router.post("/{notification_id}/dismiss", response_model=Dict[str, bool])
async def dismiss_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Dismiss a notification."""
    success = notification_service.dismiss_notification(notification_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or not owned by user"
        )
    
    return {"success": True}


@router.get("/preferences", response_model=NotificationPreferences)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get notification preferences for the current user."""
    preferences = notification_service.get_user_preferences(current_user.id)
    return preferences


@router.put("/preferences", response_model=Dict[str, bool])
async def update_preferences(
    preferences_update: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Update notification preferences for the current user."""
    # Convert to dict, excluding None values
    updates = {k: v for k, v in preferences_update.model_dump().items() if v is not None}
    
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updates provided"
        )
    
    success = notification_service.update_user_preferences(current_user.id, updates)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences"
        )
    
    return {"success": True}
