import pytest
import os
from unittest.mock import MagicMock

# Set test environment variables FIRST before any imports
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"
os.environ["DEBUG"] = "true"

# Mock SQL service for tests that need it
mock_sql_service = MagicMock()
mock_sql_service.get_schema_info_for_connection.return_value = {"tables": [], "details": {}}

# Import after env vars are set
from typing import Generator

# Lazy imports to avoid circular import issues
_app = None
_test_client = None

def get_test_app():
    """Lazy load the FastAPI app."""
    global _app
    if _app is None:
        from backend.app import app
        from backend.services.sql_service import get_sql_service
        app.dependency_overrides[get_sql_service] = lambda: mock_sql_service
        _app = app
    return _app

@pytest.fixture(scope="session")
def test_settings():
    """Fixture to provide test settings."""
    from backend.config import get_settings
    return get_settings()


@pytest.fixture(scope="module")
def client() -> Generator:
    """
    Fixture to provide FastAPI test client.
    Uses module scope to reuse client across tests in same module.
    """
    from fastapi.testclient import TestClient
    app = get_test_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth_token(client) -> str:
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
