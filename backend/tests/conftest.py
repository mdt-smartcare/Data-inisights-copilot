import pytest
import os
from unittest.mock import MagicMock, patch

# Mock SQLService to avoid real database connections during tests
# MUST HAPPEN BEFORE ANY BACKEND IMPORTS
mock_sql_service = MagicMock()
mock_sql_service.get_schema_info_for_connection.return_value = {"tables": [], "details": {}}

# Use patch to globally replace get_sql_service wherever it is imported
# This handles calls inside constructors like AgentService and ConfigService
patcher = patch("backend.services.sql_service.get_sql_service", return_value=mock_sql_service)
patcher.start()

# Set test environment variables before importing app
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"
os.environ["DEBUG"] = "true"

from fastapi.testclient import TestClient
from typing import Generator
from backend.app import app
from backend.config import get_settings
from backend.services.sql_service import get_sql_service

# Also use dependency_overrides for extra safety in FastAPI routes
app.dependency_overrides[get_sql_service] = lambda: mock_sql_service

@pytest.fixture(scope="session")
def test_settings():
    """Fixture to provide test settings."""
    return get_settings()


@pytest.fixture(scope="module")
def client() -> Generator:
    """
    Fixture to provide FastAPI test client.
    Uses module scope to reuse client across tests in same module.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth_token(client: TestClient) -> str:
    """
    Fixture to provide valid JWT token for authenticated requests.
    Logs in with default admin credentials.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token: str) -> dict:
    """
    Fixture to provide authorization headers.
    """
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def sample_chat_request():
    """Fixture providing a sample chat request payload."""
    return {
        "query": "How many patients have hypertension?",
        "user_id": "admin"
    }


@pytest.fixture
def sample_feedback_request():
    """Fixture providing a sample feedback request payload."""
    return {
        "trace_id": "test-trace-id-123",
        "query": "How many patients have hypertension?",
        "selected_suggestion": "What is the average age?",
        "rating": 1,
        "comment": "Very helpful"
    }
