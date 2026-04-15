"""
Base repository pattern with SQLAlchemy ORM.

Provides generic CRUD operations using SQLAlchemy 2.0 async ORM.
"""
from typing import Generic, TypeVar, Type, Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.connection import Base
from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# Type variables
T = TypeVar('T', bound=Base)  # SQLAlchemy ORM model
CreateSchemaType = TypeVar('CreateSchemaType', bound=BaseModel)  # Pydantic input
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=BaseModel)  # Pydantic input
ResponseSchemaType = TypeVar('ResponseSchemaType', bound=BaseModel)  # Pydantic output


class BaseRepository(Generic[T, CreateSchemaType, UpdateSchemaType, ResponseSchemaType]):
    """
    Base repository with generic CRUD operations using SQLAlchemy ORM.
    
    Combines SQLAlchemy ORM models (for DB) with Pydantic models (for API).
    Uses async SQLAlchemy for non-blocking database operations.
    
    Type Parameters:
        T: SQLAlchemy ORM model (inherits from Base)
        CreateSchemaType: Pydantic model for creation
        UpdateSchemaType: Pydantic model for updates
        ResponseSchemaType: Pydantic model for responses
    
    Usage:
        class UserRepository(BaseRepository[
            UserModel,      # SQLAlchemy model
            UserCreate,     # Pydantic input
            UserUpdate,     # Pydantic input
            User            # Pydantic output
        ]):
            def __init__(self, session: AsyncSession):
                super().__init__(
                    session=session,
                    model=UserModel,
                    response_schema=User
                )
    """
    
    def __init__(
        self,
        session: AsyncSession,
        model: Type[T],
        response_schema: Type[ResponseSchemaType]
    ):
        """
        Initialize repository.
        
        Args:
            session: SQLAlchemy async session
            model: SQLAlchemy ORM model class
            response_schema: Pydantic response model class
        """
        self.session = session
        self.model = model
        self.response_schema = response_schema
    
    def _to_pydantic(self, db_obj: T) -> ResponseSchemaType:
        """
        Convert SQLAlchemy model to Pydantic response model.
        
        Args:
            db_obj: SQLAlchemy model instance
        
        Returns:
            Pydantic model instance
        """
        return self.response_schema.model_validate(db_obj)
    
    def _to_orm(self, data: CreateSchemaType) -> T:
        """
        Convert Pydantic create schema to SQLAlchemy model.
        
        Args:
            data: Pydantic create model
        
        Returns:
            SQLAlchemy model instance (not yet added to session)
        """
        return self.model(**data.model_dump(exclude_none=True))
    
    async def get_by_id(self, id: UUID) -> Optional[ResponseSchemaType]:
        """
        Get a single entity by ID.
        
        Args:
            id: Entity UUID
        
        Returns:
            Pydantic response model or None if not found
        """
        try:
            result = await self.session.execute(
                select(self.model).where(self.model.id == id)
            )
            db_obj = result.scalar_one_or_none()
            
            if db_obj is None:
                return None
            
            return self._to_pydantic(db_obj)
            
        except Exception as e:
            logger.error(f"Error fetching {self.model.__tablename__} by ID {id}: {e}")
            raise
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None
    ) -> List[ResponseSchemaType]:
        """
        Get multiple entities with pagination and filtering.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            filters: Dictionary of column:value filters
            order_by: Column name to sort by (prefix with - for DESC)
        
        Returns:
            List of Pydantic response models
        """
        try:
            query = select(self.model)
            
            # Apply filters
            if filters:
                for column, value in filters.items():
                    if hasattr(self.model, column):
                        query = query.where(getattr(self.model, column) == value)
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    # Descending order
                    col_name = order_by[1:]
                    if hasattr(self.model, col_name):
                        query = query.order_by(getattr(self.model, col_name).desc())
                else:
                    # Ascending order
                    if hasattr(self.model, order_by):
                        query = query.order_by(getattr(self.model, order_by))
            else:
                # Default ordering by id desc
                query = query.order_by(self.model.id.desc())
            
            # Apply pagination
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            db_objs = result.scalars().all()
            
            return [self._to_pydantic(obj) for obj in db_objs]
            
        except Exception as e:
            logger.error(f"Error fetching {self.model.__tablename__} list: {e}")
            raise
    
    async def create(self, data: CreateSchemaType) -> ResponseSchemaType:
        """
        Create a new entity.
        
        Args:
            data: Pydantic creation model
        
        Returns:
            Pydantic response model
        """
        try:
            db_obj = self._to_orm(data)
            
            self.session.add(db_obj)
            await self.session.flush()  # Flush to get generated ID
            await self.session.refresh(db_obj)  # Refresh to get all defaults
            
            return self._to_pydantic(db_obj)
            
        except Exception as e:
            logger.error(f"Error creating {self.model.__tablename__}: {e}")
            raise
    
    async def update(self, id: UUID, data: UpdateSchemaType) -> Optional[ResponseSchemaType]:
        """
        Update an existing entity.
        
        Args:
            id: Entity UUID
            data: Pydantic update model (only non-None fields are updated)
        
        Returns:
            Updated Pydantic response model or None if not found
        """
        try:
            # Convert to dict, excluding None values
            update_data = data.model_dump(exclude_none=True)
            
            if not update_data:
                # No fields to update, just return existing
                return await self.get_by_id(id)
            
            # Add updated_at timestamp if column exists
            if hasattr(self.model, 'updated_at'):
                update_data['updated_at'] = datetime.utcnow()
            
            # Execute update
            stmt = (
                update(self.model)
                .where(self.model.id == id)
                .values(**update_data)
                .returning(self.model)
            )
            
            result = await self.session.execute(stmt)
            db_obj = result.scalar_one_or_none()
            
            if db_obj is None:
                return None
            
            await self.session.flush()
            await self.session.refresh(db_obj)
            
            return self._to_pydantic(db_obj)
            
        except Exception as e:
            logger.error(f"Error updating {self.model.__tablename__} {id}: {e}")
            raise
    
    async def delete(self, id: UUID) -> bool:
        """
        Delete an entity by ID.
        
        Args:
            id: Entity UUID
        
        Returns:
            True if deleted, False if not found
        """
        try:
            stmt = delete(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error deleting {self.model.__tablename__} {id}: {e}")
            raise
    
    async def exists(self, id: UUID) -> bool:
        """
        Check if an entity exists.
        
        Args:
            id: Entity UUID
        
        Returns:
            True if exists, False otherwise
        """
        try:
            stmt = select(func.count()).select_from(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            count = result.scalar()
            
            return count > 0
            
        except Exception as e:
            logger.error(f"Error checking existence of {self.model.__tablename__} {id}: {e}")
            raise
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities with optional filtering.
        
        Args:
            filters: Dictionary of column:value filters
        
        Returns:
            Count of matching entities
        """
        try:
            query = select(func.count()).select_from(self.model)
            
            if filters:
                for column, value in filters.items():
                    if hasattr(self.model, column):
                        query = query.where(getattr(self.model, column) == value)
            
            result = await self.session.execute(query)
            return result.scalar()
            
        except Exception as e:
            logger.error(f"Error counting {self.model.__tablename__}: {e}")
            raise
