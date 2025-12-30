"""
Pytest configuration and shared fixtures.
"""
import pytest
import os
from fastapi.testclient import TestClient
from typing import Generator

# Set test environment variables before importing app
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"
os.environ["DEBUG"] = "true"

from backend.app import app
from backend.config import get_settings


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
        json={"username": "admin", "password": "admin"}
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
