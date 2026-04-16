"""
Alembic environment configuration for async SQLAlchemy.

Supports both online and offline migration modes with PostgreSQL.
"""
import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import settings and models
from app.core.config import get_settings
from app.core.database.connection import Base

# Import all models to register them with Base.metadata
from app.modules.users.models import UserModel  # noqa: F401
from app.modules.agents.models import AgentModel, AgentConfigModel, UserAgentModel  # noqa: F401
from app.modules.data_sources.models import DataSourceModel  # noqa: F401
from app.modules.observability.models import AuditLogModel  # noqa: F401
from app.modules.ai_models.models import AIModel  # noqa: F401

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate support
target_metadata = Base.metadata

# Get database URL from settings
settings = get_settings()


def get_url() -> str:
    """Get async database URL from settings."""
    return f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    
    This configures the context with just a URL and not an Engine,
    which is useful for generating SQL scripts without a live database.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.
    
    Creates an async Engine and runs migrations within a connection.
    """
    connectable = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
