"""
User service for business logic.

Handles user CRUD operations, password management, and user searches.
"""
from typing import Optional, List
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    User, UserCreate, UserUpdate, TokenResponse, LoginRequest
)
from app.core.auth.security import (
    hash_password, verify_password, create_access_token
)
from app.core.config import get_settings
from app.core.utils.logging import get_logger
from app.core.utils.exceptions import (
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
    AuthenticationError,
    ValidationError
)

logger = get_logger(__name__)


class UserService:
    """Service layer for user operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = UserRepository(session)
        self.settings = get_settings()
    
    async def create_user(self, data: UserCreate) -> User:
        """
        Create a new user.
        
        Args:
            data: User creation data
        
        Returns:
            Created user
        
        Raises:
            ResourceAlreadyExistsError: If username or email already exists
        """
        # Check if username already exists
        existing = await self.repository.get_by_username(data.username)
        if existing:
            raise ResourceAlreadyExistsError(
                resource_type="User",
                identifier=f"username: {data.username}"
            )
        
        # Check if email already exists (if provided)
        if data.email:
            existing_email = await self.repository.get_by_email(data.email)
            if existing_email:
                raise ResourceAlreadyExistsError(
                    resource_type="User",
                    identifier=f"email: {data.email}"
                )
        
        # Hash password
        password = data.password
        data.password = hash_password(password)
        
        # Create user
        user = await self.repository.create(data)
        
        logger.info(f"User created", user_id=user.id, username=user.username)
        
        return user
    
    async def get_user(self, user_id: str) -> User:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
        
        Returns:
            User instance
        
        Raises:
            ResourceNotFoundError: If user not found
        """
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        return user
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return await self.repository.get_by_username(username)
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return await self.repository.get_by_email(email)
    
    async def get_user_by_external_id(self, external_id: str) -> Optional[User]:
        """Get user by external ID (OIDC)."""
        return await self.repository.get_by_external_id(external_id)
    
    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        List all users with pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
        
        Returns:
            List of users
        """
        return await self.repository.get_all(skip=skip, limit=limit, order_by="-created_at")
    
    async def search_users(
        self,
        query: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[User], int]:
        """
        Search users with filters.
        
        Args:
            query: Search query
            role: Filter by role
            is_active: Filter by active status
            skip: Pagination offset
            limit: Pagination limit
        
        Returns:
            Tuple of (users list, total count)
        """
        users = await self.repository.search_users(
            query=query,
            role=role,
            is_active=is_active,
            skip=skip,
            limit=limit
        )
        
        total = await self.repository.count_users(
            query=query,
            role=role,
            is_active=is_active
        )
        
        return users, total
    
    async def update_user(self, user_id: str, data: UserUpdate) -> User:
        """
        Update user.
        
        Args:
            user_id: User ID
            data: Update data
        
        Returns:
            Updated user
        
        Raises:
            ResourceNotFoundError: If user not found
        """
        # Hash password if provided
        if data.password:
            data.password = hash_password(data.password)
        
        user = await self.repository.update(user_id, data)
        if not user:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        logger.info(f"User updated", user_id=user.id, username=user.username)
        
        return user
    
    async def delete_user(self, user_id: str) -> bool:
        """
        Delete user.
        
        Args:
            user_id: User ID
        
        Returns:
            True if deleted
        
        Raises:
            ResourceNotFoundError: If user not found
        """
        deleted = await self.repository.delete(user_id)
        if not deleted:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        logger.info(f"User deleted", user_id=user_id)
        
        return True
    
    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Change user password.
        
        Args:
            user_id: User ID
            current_password: Current password for verification
            new_password: New password
        
        Returns:
            True if password changed
        
        Raises:
            ResourceNotFoundError: If user not found
            AuthenticationError: If current password is incorrect
        """
        # Get user with password hash
        user = await self.repository.get_with_password(user_id)
        if not user:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        # Verify current password
        if not verify_password(current_password, user.password_hash):
            raise AuthenticationError("Current password is incorrect")
        
        # Hash and update new password
        new_hash = hash_password(new_password)
        success = await self.repository.update_password(user_id, new_hash)
        
        if success:
            logger.info(f"Password changed", user_id=user_id)
        
        return success
    
    async def reset_password(self, user_id: str, new_password: str) -> bool:
        """
        Admin password reset (no current password verification).
        
        Args:
            user_id: User ID
            new_password: New password
        
        Returns:
            True if password reset
        
        Raises:
            ResourceNotFoundError: If user not found
        """
        user = await self.repository.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        # Hash and update password
        new_hash = hash_password(new_password)
        success = await self.repository.update_password(user_id, new_hash)
        
        if success:
            logger.info(f"Password reset by admin", user_id=user_id)
        
        return success
    
    async def deactivate_user(self, user_id: str) -> bool:
        """
        Deactivate user account.
        
        Args:
            user_id: User ID
        
        Returns:
            True if deactivated
        
        Raises:
            ResourceNotFoundError: If user not found
        """
        success = await self.repository.deactivate(user_id)
        if not success:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        logger.info(f"User deactivated", user_id=user_id)
        
        return True
    
    async def activate_user(self, user_id: str) -> bool:
        """
        Activate user account.
        
        Args:
            user_id: User ID
        
        Returns:
            True if activated
        
        Raises:
            ResourceNotFoundError: If user not found
        """
        success = await self.repository.activate(user_id)
        if not success:
            raise ResourceNotFoundError(resource_type="User", resource_id=user_id)
        
        logger.info(f"User activated", user_id=user_id)
        
        return True
    
    async def authenticate(self, credentials: LoginRequest) -> TokenResponse:
        """
        Authenticate user and return token.
        
        Args:
            credentials: Login credentials
        
        Returns:
            Token response with user data
        
        Raises:
            AuthenticationError: If authentication fails
        """
        # Get user with password hash
        user_model = await self.repository.get_with_password(credentials.username)
        
        if not user_model:
            raise AuthenticationError("Invalid username or password")
        
        # Verify password
        if not verify_password(credentials.password, user_model.password_hash):
            raise AuthenticationError("Invalid username or password")
        
        # Check if user is active
        if not user_model.is_active:
            raise AuthenticationError("User account is inactive")
        
        # Create access token
        token_data = {
            "sub": user_model.id,
            "username": user_model.username,
            "role": user_model.role
        }
        
        expires_delta = timedelta(minutes=self.settings.access_token_expire_minutes)
        access_token = create_access_token(
            data=token_data,
            secret_key=self.settings.secret_key,
            algorithm=self.settings.algorithm,
            expires_delta=expires_delta
        )
        
        # Convert to Pydantic User
        user = self.repository._to_pydantic(user_model)
        
        logger.info(f"User authenticated", user_id=user.id, username=user.username)
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.settings.access_token_expire_minutes * 60,
            user=user
        )
