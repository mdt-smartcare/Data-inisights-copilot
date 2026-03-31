"""
Example: SQLAlchemy 2.0 usage patterns in the new modular monolith.

This file demonstrates how to:
1. Define SQLAlchemy ORM models
2. Create repositories using BaseRepository
3. Use repositories in FastAPI routes
"""

# ============================================
# 1. Define SQLAlchemy ORM Model
# ============================================
# Location: app/modules/users/infrastructure/models.py

from uuid import uuid4
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database.connection import Base


class UserModel(Base):
    """SQLAlchemy ORM model for users table."""
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================
# 2. Define Pydantic Schemas (API Layer)
# ============================================
# Location: app/modules/users/presentation/schemas.py

from pydantic import BaseModel, EmailStr
from datetime import datetime


class UserCreate(BaseModel):
    """Input schema for creating users."""
    email: EmailStr
    name: str
    role: str = "user"


class UserUpdate(BaseModel):
    """Input schema for updating users."""
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class User(BaseModel):
    """Output schema for user responses."""
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}  # Enable ORM mode


# ============================================
# 3. Create Repository
# ============================================
# Location: app/modules/users/infrastructure/user_repository.py

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.base_repository import BaseRepository
from app.modules.users.infrastructure.models import UserModel
from app.modules.users.presentation.schemas import User, UserCreate, UserUpdate


class UserRepository(BaseRepository[UserModel, UserCreate, UserUpdate, User]):
    """Repository for user database operations."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(
            session=session,
            model=UserModel,
            response_schema=User
        )
    
    # Add custom queries beyond CRUD
    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        from sqlalchemy import select
        
        result = await self.session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        db_obj = result.scalar_one_or_none()
        
        if db_obj is None:
            return None
        
        return self._to_pydantic(db_obj)
    
    async def get_active_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Get all active users."""
        return await self.get_all(
            skip=skip,
            limit=limit,
            filters={"is_active": True}
        )


# ============================================
# 4. Use in FastAPI Routes
# ============================================
# Location: app/modules/users/presentation/routes.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database.session import get_db_session
from app.modules.users.infrastructure.user_repository import UserRepository
from app.modules.users.presentation.schemas import User, UserCreate, UserUpdate
from app.core.models.common import BaseResponse, PaginatedResponse

router = APIRouter(prefix="/users", tags=["users"])


def get_user_repo(session: AsyncSession = Depends(get_db_session)) -> UserRepository:
    """Dependency for user repository."""
    return UserRepository(session)


@router.get("", response_model=PaginatedResponse[User])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    repo: UserRepository = Depends(get_user_repo)
):
    """List all users with pagination."""
    users = await repo.get_all(skip=skip, limit=limit)
    total = await repo.count()
    
    return PaginatedResponse(
        status="success",
        message="Users retrieved successfully",
        data=users,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{user_id}", response_model=BaseResponse[User])
async def get_user(
    user_id: UUID,
    repo: UserRepository = Depends(get_user_repo)
):
    """Get a specific user by ID."""
    user = await repo.get_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return BaseResponse(
        status="success",
        message="User retrieved",
        data=user
    )


@router.post("", response_model=BaseResponse[User], status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    repo: UserRepository = Depends(get_user_repo)
):
    """Create a new user."""
    # Check if email already exists
    existing = await repo.get_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user = await repo.create(data)
    
    return BaseResponse(
        status="success",
        message="User created successfully",
        data=user
    )


@router.put("/{user_id}", response_model=BaseResponse[User])
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    repo: UserRepository = Depends(get_user_repo)
):
    """Update a user."""
    user = await repo.update(user_id, data)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return BaseResponse(
        status="success",
        message="User updated successfully",
        data=user
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    repo: UserRepository = Depends(get_user_repo)
):
    """Delete a user."""
    deleted = await repo.delete(user_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )


# ============================================
# 5. Application Startup
# ============================================
# Location: app/app.py

from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.database.connection import DatabaseConfig, init_database
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # Startup: Initialize database from environment
    settings = get_settings()
    config = DatabaseConfig.from_env(settings)
    
    db = init_database(config)
    await db.connect()
    
    print(f"✅ Connected to database: {settings.postgres_db}")
    
    yield  # Application runs
    
    # Shutdown: Close database
    await db.disconnect()
    print("✅ Database disconnected")


app = FastAPI(
    title="FHIR RAG API",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================
# Key Benefits of SQLAlchemy 2.0 Approach:
# ============================================
# 
# 1. Less boilerplate (~70% code reduction in repositories)
# 2. Type-safe queries with IDE autocomplete
# 3. Automatic connection pooling and management
# 4. Built-in retry and reconnection logic
# 5. ORM handles SQL generation (less error-prone)
# 6. Easy to test with dependency injection
# 7. Alembic integration for migrations
# 8. Separation: SQLAlchemy models (DB) + Pydantic models (API)
# 9. Async throughout entire stack
# 10. Industry standard with massive community support
