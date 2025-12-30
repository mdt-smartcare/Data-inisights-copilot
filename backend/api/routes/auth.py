"""
Authentication routes for login and token management.
"""
from fastapi import APIRouter, HTTPException, status
from datetime import timedelta

from backend.config import get_settings, DEFAULT_USERS
from backend.core.security import create_access_token
from backend.models.schemas import LoginRequest, TokenResponse
from backend.core.logging import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT token.
    
    - **username**: User's username
    - **password**: User's password
    
    Returns JWT access token for subsequent requests.
    """
    logger.info(f"Login attempt for user: {request.username}")
    
    # Validate credentials (temporary - will be hashed DB passwords later)
    if request.username not in DEFAULT_USERS:
        logger.warning(f"Login failed: User not found - {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    if DEFAULT_USERS[request.username] != request.password:
        logger.warning(f"Login failed: Invalid password for user - {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": request.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    
    logger.info(f"Login successful for user: {request.username}")
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        username=request.username,
        expires_in=settings.access_token_expire_minutes * 60
    )
