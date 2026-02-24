"""
Authentication routes for OIDC/Keycloak integration.

Note: User registration and login are handled by Keycloak.
This module provides endpoints for:
- Getting the current authenticated user's profile

User management (CRUD) is handled by /users/* endpoints.
"""
from fastapi import APIRouter, Depends

from backend.models.schemas import User
from backend.core.permissions import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get the current authenticated user's profile.
    
    The user is authenticated via Keycloak OIDC token.
    On first access, the user is automatically provisioned in the local database.
    
    Returns:
        User profile including username, email, role, and external_id (Keycloak sub claim)
    """
    return current_user
