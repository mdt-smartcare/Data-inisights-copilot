"""
User service for business logic.

Handles user CRUD operations, password management, and user searches.
"""
from typing import Optional, List
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    User, UserCreate, UserUpdate
)
# Note: password/JWT functions removed - auth handled by Keycloak/OIDC
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
        
        Note: Password management is handled by Keycloak/OIDC.
        """
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
    
    # Note: change_password and reset_password removed - handled by Keycloak/OIDC
    
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
    
    # Note: authenticate() method removed - authentication is handled by Keycloak/OIDC
    # Users authenticate via Keycloak and receive tokens directly from the identity provider
