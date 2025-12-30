"""
Integration tests for the Chat API endpoint.
"""
import pytest
from fastapi.testclient import TestClient


class TestChatAPI:
    """Test suite for /api/v1/chat endpoint."""
    
    def test_chat_requires_authentication(self, client: TestClient, sample_chat_request):
        """Test that chat endpoint requires authentication."""
        response = client.post("/api/v1/chat", json=sample_chat_request)
        assert response.status_code == 403  # No auth header
    
    def test_chat_invalid_token(self, client: TestClient, sample_chat_request):
        """Test that invalid tokens are rejected."""
        response = client.post(
            "/api/v1/chat",
            json=sample_chat_request,
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401
    
    def test_chat_empty_query(self, client: TestClient, auth_headers):
        """Test validation for empty query."""
        response = client.post(
            "/api/v1/chat",
            json={"query": ""},
            headers=auth_headers
        )
        assert response.status_code == 422  # Validation error
    
    def test_chat_query_too_long(self, client: TestClient, auth_headers):
        """Test validation for query length."""
        long_query = "a" * 2001  # Exceeds max length
        response = client.post(
            "/api/v1/chat",
            json={"query": long_query},
            headers=auth_headers
        )
        assert response.status_code == 422
    
    @pytest.mark.skip(reason="Requires live database and LLM - enable for integration testing")
    def test_chat_success(self, client: TestClient, auth_headers, sample_chat_request):
        """Test successful chat query (requires live services)."""
        response = client.post(
            "/api/v1/chat",
            json=sample_chat_request,
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "answer" in data
        assert "trace_id" in data
        assert "timestamp" in data
        assert isinstance(data["suggested_questions"], list)


class TestAuthAPI:
    """Test suite for /api/v1/auth endpoints."""
    
    def test_login_success(self, client: TestClient):
        """Test successful login."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["username"] == "admin"
    
    def test_login_invalid_credentials(self, client: TestClient):
        """Test login with invalid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong"}
        )
        assert response.status_code == 401
    
    def test_login_missing_fields(self, client: TestClient):
        """Test login with missing fields."""
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin"}
        )
        assert response.status_code == 422


class TestFeedbackAPI:
    """Test suite for /api/v1/feedback endpoint."""
    
    def test_feedback_requires_auth(self, client: TestClient, sample_feedback_request):
        """Test that feedback requires authentication."""
        response = client.post("/api/v1/feedback", json=sample_feedback_request)
        assert response.status_code == 403
    
    def test_feedback_success(self, client: TestClient, auth_headers, sample_feedback_request):
        """Test successful feedback submission."""
        response = client.post(
            "/api/v1/feedback",
            json=sample_feedback_request,
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "feedback_id" in data
    
    def test_feedback_invalid_rating(self, client: TestClient, auth_headers):
        """Test feedback with invalid rating."""
        invalid_feedback = {
            "trace_id": "test-id",
            "query": "test query",
            "rating": 5  # Invalid - must be -1 or 1
        }
        response = client.post(
            "/api/v1/feedback",
            json=invalid_feedback,
            headers=auth_headers
        )
        assert response.status_code == 422


class TestHealthAPI:
    """Test suite for /api/v1/health endpoint."""
    
    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "services" in data
    
    def test_health_no_auth_required(self, client: TestClient):
        """Test that health check doesn't require auth."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200


class TestRootEndpoint:
    """Test suite for root endpoint."""
    
    def test_root(self, client: TestClient):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "docs" in data
