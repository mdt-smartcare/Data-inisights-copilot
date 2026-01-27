"""
Authentication routes for login, registration, and token management.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from datetime import timedelta

from backend.config import get_settings
from backend.core.security import create_access_token
from backend.models.schemas import LoginRequest, RegisterRequest, TokenResponse, User
from backend.core.logging import get_logger
from backend.sqliteDb.db import get_db_service, DatabaseService

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()
logger = get_logger(__name__)


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
    - **role**: Optional role (default: 'user', can be 'admin')
    
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
    
    # Authenticate user (checks username, password, and active status)
    user = db.authenticate_user(request.username, request.password)
    
    if not user:
        # Authentication failed - don't reveal why (security best practice)
        logger.warning(f"Login failed for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},  # Required for 401 responses
        )
    
    # Create JWT access token
    # Token contains username in 'sub' claim and expiration time
    access_token = create_access_token(
        data={"sub": request.username},  # 'sub' (subject) is standard JWT claim for user identifier
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)  # 720 minutes = 12 hours
    )
    
    logger.info(f"Login successful for user: {request.username}")
    # Return token and user information
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",  # OAuth 2.0 standard token type
        user=User(
            username=request.username,
            email=user.get('email'),
            full_name=user.get('full_name'),
            role=user.get('role', 'user'),  # Default to 'user' if role not set
        ),
        expires_in=settings.access_token_expire_minutes * 60  # Convert minutes to seconds for client
    )
