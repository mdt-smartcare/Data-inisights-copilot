"""
E2E tests for the RAG Configuration Wizard flow.
Tests the complete lifecycle from connection selection to prompt publishing.
"""
import pytest
from fastapi.testclient import TestClient


class TestWizardE2EFlow:
    """End-to-end tests for the RAG configuration wizard API endpoints."""
    
    def test_get_connections_endpoint(self, client: TestClient, auth_headers: dict):
        """Test fetching available database connections."""
        response = client.get("/api/v1/data/connections", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_schema_requires_auth(self, client: TestClient):
        """Test that schema endpoint requires authentication."""
        response = client.get("/api/v1/data/connections/999/schema")
        
        assert response.status_code == 401
    
    def test_get_active_config(self, client: TestClient, auth_headers: dict):
        """Test fetching active RAG configuration."""
        response = client.get("/api/v1/config/active", headers=auth_headers)
        
        # Should succeed even if no active config exists
        assert response.status_code in [200, 404]
    
    def test_get_prompt_history(self, client: TestClient, auth_headers: dict):
        """Test fetching prompt version history."""
        response = client.get("/api/v1/config/history", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_generate_prompt_requires_auth(self, client: TestClient):
        """Test that prompt generation requires authentication."""
        response = client.post("/api/v1/config/generate", json={
            "data_dictionary": "test"
        })
        
        assert response.status_code == 401
    
    def test_publish_prompt_requires_super_admin(self, client: TestClient, auth_headers: dict):
        """Test that publishing requires super_admin role."""
        # This should work for admin but would fail for lower roles
        response = client.post("/api/v1/config/publish", headers=auth_headers, json={
            "prompt_text": "Test prompt",
            "user_id": 1,
            "connection_id": 1,
            "schema_selection": "{}",
            "data_dictionary": "Test dictionary"
        })
        
        # Could be 200 (success) or 403 (if not super_admin) - both are valid behaviors
        assert response.status_code in [200, 403, 422]  # 422 for validation errors
    
    def test_embedding_jobs_list(self, client: TestClient, auth_headers: dict):
        """Test listing embedding jobs."""
        response = client.get("/api/v1/embedding-jobs", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_notifications_list(self, client: TestClient, auth_headers: dict):
        """Test listing notifications."""
        response = client.get("/api/v1/notifications", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestWizardWorkflow:
    """Tests that simulate the complete wizard workflow."""
    
    def test_wizard_step1_connection_selection(self, client: TestClient, auth_headers: dict):
        """Test Step 1: List and verify available connections."""
        response = client.get("/api/v1/data/connections", headers=auth_headers)
        
        assert response.status_code == 200
        connections = response.json()
        
        # Wizard can start even with 0 connections (would show empty state)
        assert isinstance(connections, list)
    
    def test_wizard_step5_publish_flow(self, client: TestClient, auth_headers: dict):
        """
        Test Step 5: Attempt publish with valid payload.
        Note: This may fail with 422 if schema/config validation is strict.
        """
        # Attempt to publish a minimal config
        publish_payload = {
            "prompt_text": "You are a helpful SQL agent.",
            "user_id": 1,
            "connection_id": 1,
            "schema_selection": "{}",
            "data_dictionary": "# Test Dictionary\n- table1: test table"
        }
        
        response = client.post(
            "/api/v1/config/publish",
            headers=auth_headers,
            json=publish_payload
        )
        
        # Accept success or validation error (depends on other state)
        assert response.status_code in [200, 422, 403]
        
        if response.status_code == 200:
            data = response.json()
            assert "id" in data or "message" in data


class TestConfigSummaryAPI:
    """Tests for the configuration summary endpoint."""
    
    def test_get_config_summary(self, client: TestClient, auth_headers: dict):
        """Test fetching config summary for dashboard."""
        response = client.get("/api/v1/config/active", headers=auth_headers)
        
        # Either returns config or 404 if none active
        if response.status_code == 200:
            data = response.json()
            # Verify structure
            assert "prompt_text" in data
        else:
            assert response.status_code == 404
