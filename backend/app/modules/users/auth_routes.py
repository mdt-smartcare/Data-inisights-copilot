"""
Authentication routes.

Handles user profile and authentication endpoints.
Authentication is handled by Keycloak - users obtain tokens from the identity provider.
"""
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPBearer

from app.core.models.common import BaseResponse
from app.modules.users.schemas import User
from app.core.auth.permissions import get_current_user

router = APIRouter()
security = HTTPBearer()


# Note: Login/logout handled by Keycloak
# Users should:
# 1. Login: Authenticate via Keycloak and obtain token
# 2. Logout: Revoke token via Keycloak's logout endpoint
# 3. Token refresh: Use Keycloak's token refresh endpoint




@router.get("/me", response_model=BaseResponse[User])
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information.
    
    Returns the user profile of the currently authenticated user based 
    on the Keycloak token in the Authorization header.
    """
    return BaseResponse.ok(data=current_user)
