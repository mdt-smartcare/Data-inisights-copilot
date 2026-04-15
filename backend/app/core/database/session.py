"""
FastAPI dependency injection for SQLAlchemy sessions.

Provides request-scoped database session handling and
dependency injection for route handlers.
"""
from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.connection import get_database, DatabaseConnection
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database session.
    
    Provides a database session for the duration of a request.
    Automatically handles session lifecycle, commits, and rollbacks.
    
    Usage:
        from sqlalchemy import select
        
        @router.get("/users")
        async def get_users(session: AsyncSession = Depends(get_db_session)):
            result = await session.execute(select(User))
            users = result.scalars().all()
            return users
        
        @router.post("/users")
        async def create_user(
            data: UserCreate,
            session: AsyncSession = Depends(get_db_session)
        ):
            user = User(**data.dict())
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    Yields:
        AsyncSession instance
    """
    db: DatabaseConnection = get_database()
    
    if db is None or not db.is_connected:
        logger.error("Database not initialized or not connected")
        raise RuntimeError("Database connection not initialized. Call init_database() first.")
    
    async with db.session() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            raise


async def get_db() -> DatabaseConnection:
    """
    FastAPI dependency for DatabaseConnection instance.
    
    Use this when you need direct access to the database connection
    for raw queries or connection management.
    
    Usage:
        @router.get("/health")
        async def health_check(db: DatabaseConnection = Depends(get_db)):
            is_healthy = await db.health_check()
            return {"status": "healthy" if is_healthy else "unhealthy"}
    
    Returns:
        DatabaseConnection instance
    """
    db = get_database()
    
    if db is None or not db.is_connected:
        logger.error("Database not initialized or not connected")
        raise RuntimeError("Database connection not initialized. Call init_database() first.")
    
    return db
