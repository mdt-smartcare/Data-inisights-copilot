"""
Authentication routes for login, registration, and token management.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from backend.config import get_settings
from backend.core.security import create_access_token
from backend.models.schemas import LoginRequest, RegisterRequest, TokenResponse, User
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service, DatabaseService
from backend.core.permissions import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
logger = get_logger(__name__)


@router.post("/token", include_in_schema=True)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: DatabaseService = Depends(get_db_service)
):
    """
    OAuth2 compatible token login for Swagger UI.
    
    This endpoint follows the OAuth2 password flow spec:
    - Accepts form data with username and password
    - Returns access_token and token_type
    
    Use this endpoint in Swagger UI's Authorize dialog.
    """
    logger.info(f"OAuth2 token request for user: {form_data.username}")
    
    # Get user by username
    user = db.get_user_by_username(form_data.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is active
    if not user.get('is_active'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not db.verify_password(form_data.password, user['password_hash']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": form_data.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    
    logger.info(f"OAuth2 token issued for user: {form_data.username}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: DatabaseService = Depends(get_db_service)  # Inject database service via FastAPI dependency
):
    """
    Register a new user account.
    
    This endpoint:
    1. Validates the registration data (via Pydantic schema)
    2. Hashes the password using bcrypt
    3. Stores the user in the SQLite database
    4. Returns user info (without password)
    
    Request Body:
    - **username**: Unique username (3-50 characters)
    - **password**: Password (minimum 6 characters) - will be hashed before storage
    - **email**: Optional email address (must be unique if provided)
    - **full_name**: Optional full name for display purposes
    - **role**: Optional role (default: 'viewer', can be 'super_admin', 'editor', 'user', 'viewer')
    
    Returns:
        User object with id, username, email, full_name, created_at, role
        (password is never returned)
    
    Raises:
        400 Bad Request: If username or email already exists
        500 Internal Server Error: For unexpected database errors
    """
    logger.info(f"Registration attempt for username: {request.username}")
    
    try:
        # Create user in database (password will be hashed by DatabaseService)
        user = db.create_user(
            username=request.username,
            password=request.password,  # Plain text password - will be hashed
            email=request.email,
            full_name=request.full_name,
            role=request.role or "viewer"  # Default to 'viewer' role if not specified
        )
        
        logger.info(f"User registered successfully: {request.username}")
        return User(**user)  # Convert dict to Pydantic model
    
    except ValueError as e:
        # ValueError indicates username/email already exists (from database constraint)
        logger.warning(f"Registration failed for {request.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Registration error for {request.username}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
async def login(
    request: LoginRequest,
    db: DatabaseService = Depends(get_db_service)  # Inject database service
):
    """
    Authenticate user and return JWT access token.
    
    This endpoint:
    1. Verifies username exists
    2. Checks if account is active
    3. Validates password using bcrypt
    4. Generates a JWT token valid for 12 hours (720 minutes)
    5. Returns token and user information
    
    Request Body:
    - **username**: User's username
    - **password**: User's plain text password
    
    Returns:
        TokenResponse containing:
        - access_token: JWT token to use in Authorization header
        - token_type: Always "bearer"
        - user: User object with username, email, full_name, role
        - expires_in: Token expiration time in seconds (43200 = 12 hours)
    
    Raises:
        401 Unauthorized: If username not found, account inactive, or password incorrect
        
    Usage:
        After receiving the token, include it in subsequent requests:
        Authorization: Bearer <access_token>
    """
    logger.info(f"Login attempt for user: {request.username}")
    
    # 1. Get user by username
    user = db.get_user_by_username(request.username)
    
    # 2. Check if user exists
    if not user:
        logger.warning(f"Login failed: User not found - {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # 3. Check if account is active
    if not user.get('is_active'):
        logger.warning(f"Login failed: User inactive - {request.username}")
        # Specific error for inactive users (as requested)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # 4. Verify password
    if not db.verify_password(request.password, user['password_hash']):
        logger.warning(f"Login failed: Invalid password - {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create JWT access token
    access_token = create_access_token(
        data={"sub": request.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    
    logger.info(f"Login successful for user: {request.username}")
    # Return token and user information
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=User(
            username=request.username,
            email=user.get('email'),
            full_name=user.get('full_name'),
            role=user.get('role', 'user'),
        ),
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get the current authenticated user's profile.
    """
    return current_user
