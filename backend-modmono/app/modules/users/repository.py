"""
User repository for database operations.

Extends BaseRepository with user-specific queries.
"""
from typing import Optional, List
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base_repository import BaseRepository
from app.modules.users.models import UserModel
from app.modules.users.schemas import User, UserCreate, UserUpdate
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class UserRepository(BaseRepository[UserModel, UserCreate, UserUpdate, User]):
    """Repository for user database operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(
            session=session,
            model=UserModel,
            response_schema=User
        )
    
    def _to_orm(self, data: UserCreate) -> UserModel:
        """
        Convert UserCreate to UserModel.
        
        Note: Password hashing should be done in the service layer,
        not in the repository.
        """
        values = data.model_dump(exclude_none=True, exclude={"password"})
        
        # If password is provided, it should already be hashed
        if hasattr(data, 'password') and data.password:
            values['password_hash'] = data.password
        
        return UserModel(**values)
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username to search for
        
        Returns:
            User instance or None if not found
        """
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.username == username)
            )
            db_obj = result.scalar_one_or_none()
            
            if db_obj is None:
                return None
            
            return self._to_pydantic(db_obj)
            
        except Exception as e:
            logger.error(f"Error fetching user by username {username}: {e}")
            raise
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.
        
        Args:
            email: Email to search for
        
        Returns:
            User instance or None if not found
        """
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.email == email)
            )
            db_obj = result.scalar_one_or_none()
            
            if db_obj is None:
                return None
            
            return self._to_pydantic(db_obj)
            
        except Exception as e:
            logger.error(f"Error fetching user by email {email}: {e}")
            raise
    
    async def get_by_external_id(self, external_id: str) -> Optional[User]:
        """
        Get user by external ID (from OIDC provider).
        
        Args:
            external_id: External ID from OIDC (typically 'sub' claim)
        
        Returns:
            User instance or None if not found
        """
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.external_id == external_id)
            )
            db_obj = result.scalar_one_or_none()
            
            if db_obj is None:
                return None
            
            return self._to_pydantic(db_obj)
            
        except Exception as e:
            logger.error(f"Error fetching user by external_id {external_id}: {e}")
            raise
    
    async def get_with_password(self, username: str) -> Optional[UserModel]:
        """
        Get user with password hash for authentication.
        
        Returns UserModel (not Pydantic) to access password_hash.
        
        Args:
            username: Username to search for
        
        Returns:
            UserModel instance or None if not found
        """
        try:
            result = await self.session.execute(
                select(UserModel).where(UserModel.username == username)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Error fetching user with password for {username}: {e}")
            raise
    
    async def search_users(
        self,
        query: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        Search users with filters.
        
        Args:
            query: Search query (matches username, email, full_name)
            role: Filter by role
            is_active: Filter by active status
            skip: Number of records to skip
            limit: Maximum number of records to return
        
        Returns:
            List of matching users
        """
        try:
            stmt = select(UserModel)
            
            # Apply search query
            if query:
                search_pattern = f"%{query}%"
                stmt = stmt.where(
                    or_(
                        UserModel.username.ilike(search_pattern),
                        UserModel.email.ilike(search_pattern),
                        UserModel.full_name.ilike(search_pattern)
                    )
                )
            
            # Apply role filter
            if role:
                stmt = stmt.where(UserModel.role == role)
            
            # Apply active status filter
            if is_active is not None:
                stmt = stmt.where(UserModel.is_active == is_active)
            
            # Apply ordering and pagination
            stmt = stmt.order_by(UserModel.created_at.desc()).offset(skip).limit(limit)
            
            result = await self.session.execute(stmt)
            db_objs = result.scalars().all()
            
            return [self._to_pydantic(obj) for obj in db_objs]
            
        except Exception as e:
            logger.error(f"Error searching users: {e}")
            raise
    
    async def count_users(
        self,
        query: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> int:
        """
        Count users matching filters.
        
        Args:
            query: Search query
            role: Filter by role
            is_active: Filter by active status
        
        Returns:
            Count of matching users
        """
        try:
            stmt = select(func.count()).select_from(UserModel)
            
            # Apply filters (same as search_users)
            if query:
                search_pattern = f"%{query}%"
                stmt = stmt.where(
                    or_(
                        UserModel.username.ilike(search_pattern),
                        UserModel.email.ilike(search_pattern),
                        UserModel.full_name.ilike(search_pattern)
                    )
                )
            
            if role:
                stmt = stmt.where(UserModel.role == role)
            
            if is_active is not None:
                stmt = stmt.where(UserModel.is_active == is_active)
            
            result = await self.session.execute(stmt)
            return result.scalar()
            
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            raise
    
    async def update_password(self, user_id: str, password_hash: str) -> bool:
        """
        Update user password hash.
        
        Args:
            user_id: User ID
            password_hash: New password hash
        
        Returns:
            True if updated successfully
        """
        try:
            user = await self.session.get(UserModel, user_id)
            if not user:
                return False
            
            user.password_hash = password_hash
            await self.session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating password for user {user_id}: {e}")
            raise
    
    async def deactivate(self, user_id: str) -> bool:
        """
        Deactivate a user.
        
        Args:
            user_id: User ID
        
        Returns:
            True if deactivated successfully
        """
        try:
            user = await self.session.get(UserModel, user_id)
            if not user:
                return False
            
            user.is_active = False
            await self.session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Error deactivating user {user_id}: {e}")
            raise
    
    async def activate(self, user_id: str) -> bool:
        """
        Activate a user.
        
        Args:
            user_id: User ID
        
        Returns:
            True if activated successfully
        """
        try:
            user = await self.session.get(UserModel, user_id)
            if not user:
                return False
            
            user.is_active = True
            await self.session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Error activating user {user_id}: {e}")
            raise
