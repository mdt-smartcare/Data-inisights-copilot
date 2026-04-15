"""
Database connection management with SQLAlchemy 2.0 async.

Provides async PostgreSQL connection pooling, health checks,
and ORM session management.
"""
from typing import Optional, AsyncGenerator, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager
import asyncio
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DatabaseConfig:
    """
    Database configuration.
    
    All connection parameters should come from environment variables
    via the Settings class. Do not hardcode production values.
    """
    host: str
    port: int
    database: str
    user: str
    password: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    
    @property
    def async_url(self) -> str:
        """Get async PostgreSQL connection URL for asyncpg driver."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @classmethod
    def from_env(cls, settings=None) -> "DatabaseConfig":
        """
        Create database config from environment settings.
        
        Args:
            settings: Optional Settings instance. If None, creates from environment.
        
        Returns:
            DatabaseConfig instance
        
        Usage:
            from app.core.config import get_settings
            config = DatabaseConfig.from_env(get_settings())
        """
        if settings is None:
            # Import here to avoid circular dependency
            from app.core.config import get_settings
            settings = get_settings()
        
        return cls(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
            pool_size=getattr(settings, 'postgres_pool_size', 10),
            max_overflow=getattr(settings, 'postgres_max_overflow', 20),
            pool_timeout=getattr(settings, 'postgres_pool_timeout', 30),
            pool_recycle=getattr(settings, 'postgres_pool_recycle', 3600),
            echo=getattr(settings, 'postgres_echo', settings.debug),
        )


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class DatabaseConnection:
    """
    Async database connection manager with SQLAlchemy 2.0.
    
    Provides connection pooling, automatic reconnection, health checks,
    and async session management for ORM operations.
    
    Usage:
        db = DatabaseConnection(config)
        await db.connect()
        
        async with db.session() as session:
            result = await session.execute(select(User))
            users = result.scalars().all()
        
        await db.disconnect()
    """
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize database connection manager.
        
        Args:
            config: Database configuration
        """
        self.config = config
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._is_connected = False
    
    async def connect(self, max_retries: int = 5, retry_delay: float = 1.0) -> None:
        """
        Establish database connection with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Initial delay between retries (doubles each attempt)
        
        Raises:
            ConnectionError: If connection fails after all retries
        """
        if self._is_connected and self.engine:
            logger.warning("Database already connected")
            return
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Connecting to database (attempt {attempt}/{max_retries})...")
                
                self.engine = create_async_engine(
                    self.config.async_url,
                    pool_size=self.config.pool_size,
                    max_overflow=self.config.max_overflow,
                    pool_timeout=self.config.pool_timeout,
                    pool_recycle=self.config.pool_recycle,
                    echo=self.config.echo,
                    future=True,
                )
                
                # Create session factory
                self.session_factory = async_sessionmaker(
                    self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
                
                # Test connection
                async with self.engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                
                self._is_connected = True
                logger.info("Database connected successfully")
                
                # Start background health check
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                
                return
                
            except Exception as e:
                logger.error(f"Database connection failed (attempt {attempt}/{max_retries}): {e}")
                
                if attempt < max_retries:
                    wait_time = retry_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise ConnectionError(f"Failed to connect to database after {max_retries} attempts") from e
    
    async def disconnect(self) -> None:
        """
        Close database connection gracefully.
        """
        if not self._is_connected:
            logger.warning("Database not connected")
            return
        
        # Stop health check
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close engine
        if self.engine:
            await self.engine.dispose()
            self.engine = None
        
        self.session_factory = None
        self._is_connected = False
        logger.info("Database disconnected")
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for acquiring a database session.
        
        Automatically commits on success, rolls back on exception.
        
        Yields:
            AsyncSession instance
        
        Usage:
            async with db.session() as session:
                result = await session.execute(select(User))
                users = result.scalars().all()
        """
        if not self.session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for explicit transactional operations.
        
        Use this when you need explicit transaction control.
        Automatically commits on success or rolls back on exception.
        
        Yields:
            AsyncSession instance within a transaction
        
        Usage:
            async with db.transaction() as session:
                session.add(User(name="John"))
                session.add(Profile(user_id=user.id))
        """
        if not self.session_factory:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        async with self.session_factory() as session:
            async with session.begin():
                yield session
    
    async def health_check(self) -> bool:
        """
        Check database connection health.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self._is_connected or not self.engine:
            return False
        
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def _health_check_loop(self) -> None:
        """
        Background task that periodically checks database health.
        
        Runs every 30 seconds and attempts reconnection if needed.
        """
        while True:
            try:
                await asyncio.sleep(30)
                
                is_healthy = await self.health_check()
                
                if not is_healthy:
                    logger.warning("Database unhealthy, attempting reconnection...")
                    
                    # Try to reconnect
                    try:
                        await self.disconnect()
                        await self.connect(max_retries=3, retry_delay=2.0)
                        logger.info("Database reconnected successfully")
                    except Exception as e:
                        logger.error(f"Reconnection failed: {e}")
                
            except asyncio.CancelledError:
                # Task cancelled, exit gracefully
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
    
    async def execute_raw(self, query: str, params: dict = None) -> Any:
        """
        Execute a raw SQL query.
        
        Args:
            query: SQL query string (can use :param syntax)
            params: Dictionary of parameters
        
        Returns:
            Query result
        
        Usage:
            result = await db.execute_raw(
                "SELECT * FROM users WHERE role = :role",
                {"role": "admin"}
            )
        """
        async with self.session() as session:
            result = await session.execute(text(query), params or {})
            return result
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._is_connected


# Global database instance
_database: Optional[DatabaseConnection] = None


def init_database(config: DatabaseConfig) -> DatabaseConnection:
    """
    Initialize global database connection.
    
    Args:
        config: Database configuration
    
    Returns:
        DatabaseConnection instance
    """
    global _database
    _database = DatabaseConnection(config)
    return _database


def get_database() -> Optional[DatabaseConnection]:
    """
    Get global database connection instance.
    
    Returns:
        DatabaseConnection instance or None
    """
    return _database


async def create_tables() -> None:
    """
    Create all database tables defined in ORM models.
    
    This imports all model modules to ensure they are registered
    with SQLAlchemy's Base.metadata before creating tables.
    
    For production, use proper migrations (Alembic). This is for development.
    """
    if not _database or not _database.engine:
        raise RuntimeError("Database not connected. Call init_database() and connect() first.")
    
    # Import all models to register them with Base.metadata
    # These imports trigger model registration
    from app.modules.users.models import UserModel  # noqa: F401
    from app.modules.agents.models import AgentModel, AgentConfigModel, UserAgentModel  # noqa: F401
    from app.modules.data_sources.models import DataSourceModel  # noqa: F401
    from app.modules.observability.models import AuditLogModel  # noqa: F401
    from app.modules.ai_models.models import AIModel  # noqa: F401
    from app.modules.embeddings.models import EmbeddingJobModel  # noqa: F401
    
    logger.info("Creating database tables...")
    
    async with _database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database tables created successfully")
