"""
Pytest fixtures and configuration for unit tests.

Common fixtures available:
- mock_db: Mocked async database session
- mock_user: Mocked User object
- mock_agent: Mocked Agent object
- mock_config: Mocked AgentConfig object
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


@pytest.fixture
def mock_db():
    """
    Mock async database session.
    
    Provides:
    - execute: AsyncMock for query execution
    - commit: AsyncMock for transaction commit
    - rollback: AsyncMock for transaction rollback
    - refresh: AsyncMock for object refresh
    """
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_user():
    """Mock User object with standard attributes."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.name = "Test User"
    user.role = "user"
    user.is_active = True
    return user


@pytest.fixture
def mock_admin_user(mock_user):
    """Mock admin User object."""
    mock_user.role = "admin"
    return mock_user


@pytest.fixture
def mock_agent():
    """Mock Agent object."""
    agent = MagicMock()
    agent.id = uuid4()
    agent.name = "Test Agent"
    agent.description = "A test agent"
    agent.created_by = uuid4()
    agent.is_active = True
    return agent


@pytest.fixture
def mock_config(mock_agent):
    """Mock AgentConfig object."""
    config = MagicMock()
    config.id = uuid4()
    config.agent_id = mock_agent.id
    config.version = 1
    config.is_active = True
    config.data_source_id = uuid4()
    config.chunking_config = {}
    config.embedding_config = {}
    config.rag_config = {}
    config.llm_config = {}
    return config


@pytest.fixture
def mock_data_source():
    """Mock DataSource object."""
    source = MagicMock()
    source.id = uuid4()
    source.name = "Test Source"
    source.source_type = "postgresql"
    source.connection_params = {"host": "localhost", "port": 5432}
    return source
