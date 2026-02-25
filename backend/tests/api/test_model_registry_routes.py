"""
API route tests for model registry endpoints added to
embedding_settings.py, llm_settings.py, and model_config.py.

Uses mocked ModelRegistryService to test HTTP layer only.
"""
import pytest
import os
from unittest.mock import MagicMock, patch

os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def mock_model_registry():
    """Module-scoped mock for ModelRegistryService."""
    mock = MagicMock()
    mock.list_embedding_models.return_value = [
        {"id": 1, "provider": "bge-m3", "model_name": "BAAI/bge-m3", "display_name": "BGE-M3",
         "dimensions": 1024, "max_tokens": 8192, "is_custom": 0, "is_active": 1},
        {"id": 2, "provider": "openai", "model_name": "text-embedding-3-small", "display_name": "OpenAI Small",
         "dimensions": 1536, "max_tokens": 8191, "is_custom": 0, "is_active": 0},
    ]
    mock.list_llm_models.return_value = [
        {"id": 1, "provider": "openai", "model_name": "gpt-4o", "display_name": "GPT-4o",
         "context_length": 128000, "is_custom": 0, "is_active": 1},
    ]
    mock.get_compatible_llms.return_value = [
        {"id": 1, "provider": "openai", "model_name": "gpt-4o", "display_name": "GPT-4o",
         "context_length": 128000, "is_active": 1},
    ]
    mock.get_compatibility_table.return_value = [
        {"id": 1, "embedding_model_id": 1, "llm_model_id": 1,
         "embedding_model_name": "BAAI/bge-m3", "llm_model_name": "gpt-4o"},
    ]
    mock.add_embedding_model.return_value = {
        "id": 3, "provider": "custom", "model_name": "test-emb",
        "display_name": "Test", "dimensions": 768, "is_custom": 1, "is_active": 0
    }
    mock.add_llm_model.return_value = {
        "id": 3, "provider": "custom", "model_name": "test-llm",
        "display_name": "Test LLM", "context_length": 4096, "is_custom": 1, "is_active": 0
    }
    mock.activate_embedding_model.return_value = {
        "id": 2, "model_name": "text-embedding-3-small", "is_active": 1
    }
    mock.activate_llm_model.return_value = {
        "id": 1, "model_name": "gpt-4o", "is_active": 1
    }
    mock.add_compatibility.return_value = {
        "id": 5, "embedding_model_id": 1, "llm_model_id": 3
    }
    mock.remove_compatibility.return_value = True
    mock.list_config_versions.return_value = [
        {"id": 1, "config_type": "embedding", "version": 1, "updated_by": "admin",
         "updated_at": "2026-02-24T12:00:00"},
    ]
    mock.get_config_version.return_value = {
        "id": 1, "config_type": "embedding", "version": 1,
        "config_snapshot": [{"id": 1, "is_active": 1}],
        "updated_by": "admin"
    }
    mock.rollback_to_version.return_value = {
        "success": True, "config_type": "embedding", "restored_version": 1
    }
    return mock


@pytest.fixture(scope="module")
def client(mock_model_registry):
    """Provide a TestClient with mocked model registry."""
    from fastapi.testclient import TestClient
    from backend.app import app
    from backend.services.sql_service import get_sql_service
    from backend.services.model_registry_service import get_model_registry_service

    mock_sql = MagicMock()
    mock_sql.get_schema_info_for_connection.return_value = {"tables": [], "details": {}}
    app.dependency_overrides[get_sql_service] = lambda: mock_sql
    app.dependency_overrides[get_model_registry_service] = lambda: mock_model_registry

    with TestClient(app) as tc:
        yield tc

    # Cleanup
    app.dependency_overrides.pop(get_model_registry_service, None)
    app.dependency_overrides.pop(get_sql_service, None)


@pytest.fixture(scope="module")
def auth_headers(client):
    """Get auth headers by logging in."""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Embedding Model Endpoints
# ============================================================================

class TestEmbeddingModelEndpoints:
    """Tests for embedding model registry endpoints."""

    def test_list_embedding_models(self, client, auth_headers, mock_model_registry):
        """GET /settings/embedding/models returns list."""
        response = client.get("/api/v1/settings/embedding/models", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        mock_model_registry.list_embedding_models.assert_called()

    def test_register_embedding_model(self, client, auth_headers, mock_model_registry):
        """POST /settings/embedding/models creates a model."""
        payload = {
            "provider": "custom",
            "model_name": "test-emb",
            "display_name": "Test",
            "dimensions": 768,
            "max_tokens": 512
        }
        response = client.post(
            "/api/v1/settings/embedding/models",
            json=payload, headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["model_name"] == "test-emb"
        assert data["is_custom"] == 1

    def test_activate_embedding_model(self, client, auth_headers, mock_model_registry):
        """PUT /settings/embedding/models/{id}/activate switches active model."""
        response = client.put(
            "/api/v1/settings/embedding/models/2/activate",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] == 1
        mock_model_registry.activate_embedding_model.assert_called_with(2, updated_by="admin")

    def test_register_duplicate_returns_409(self, client, auth_headers, mock_model_registry):
        """POST /settings/embedding/models returns 409 for duplicates."""
        mock_model_registry.add_embedding_model.side_effect = ValueError("already exists")
        payload = {
            "provider": "openai", "model_name": "dup",
            "display_name": "Test", "dimensions": 768
        }
        response = client.post(
            "/api/v1/settings/embedding/models",
            json=payload, headers=auth_headers
        )
        assert response.status_code == 409
        # Reset side effect
        mock_model_registry.add_embedding_model.side_effect = None
        mock_model_registry.add_embedding_model.return_value = {
            "id": 3, "provider": "custom", "model_name": "test-emb",
            "display_name": "Test", "dimensions": 768, "is_custom": 1, "is_active": 0
        }


# ============================================================================
# LLM Model Endpoints
# ============================================================================

class TestLLMModelEndpoints:
    """Tests for LLM model registry endpoints."""

    def test_list_llm_models(self, client, auth_headers, mock_model_registry):
        """GET /settings/llm/models returns list."""
        response = client.get("/api/v1/settings/llm/models", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_register_llm_model(self, client, auth_headers, mock_model_registry):
        """POST /settings/llm/models creates a model."""
        payload = {
            "provider": "custom",
            "model_name": "test-llm",
            "display_name": "Test LLM",
            "context_length": 4096,
            "max_output_tokens": 2048,
            "parameters": {"temperature": 0.5}
        }
        response = client.post(
            "/api/v1/settings/llm/models",
            json=payload, headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["model_name"] == "test-llm"

    def test_activate_llm_model(self, client, auth_headers, mock_model_registry):
        """PUT /settings/llm/models/{id}/activate switches active model."""
        response = client.put(
            "/api/v1/settings/llm/models/1/activate",
            headers=auth_headers
        )
        assert response.status_code == 200
        mock_model_registry.activate_llm_model.assert_called_with(1, updated_by="admin")

    def test_get_compatible_llms(self, client, auth_headers, mock_model_registry):
        """GET /settings/llm/models/compatible returns filtered list."""
        response = client.get("/api/v1/settings/llm/models/compatible", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


# ============================================================================
# Compatibility Endpoints
# ============================================================================

class TestCompatibilityEndpoints:
    """Tests for compatibility mapping endpoints."""

    def test_get_compatibility_table(self, client, auth_headers, mock_model_registry):
        """GET /settings/models/compatibility returns table."""
        response = client.get("/api/v1/settings/models/compatibility", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_add_compatibility(self, client, auth_headers, mock_model_registry):
        """POST /settings/models/compatibility adds mapping."""
        payload = {"embedding_model_id": 1, "llm_model_id": 3}
        response = client.post(
            "/api/v1/settings/models/compatibility",
            json=payload, headers=auth_headers
        )
        assert response.status_code == 201

    def test_remove_compatibility(self, client, auth_headers, mock_model_registry):
        """DELETE /settings/models/compatibility/{id} removes mapping."""
        response = client.delete(
            "/api/v1/settings/models/compatibility/1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_remove_nonexistent_returns_404(self, client, auth_headers, mock_model_registry):
        """DELETE /settings/models/compatibility/{id} returns 404 for missing."""
        mock_model_registry.remove_compatibility.return_value = False
        response = client.delete(
            "/api/v1/settings/models/compatibility/999",
            headers=auth_headers
        )
        assert response.status_code == 404
        # Reset
        mock_model_registry.remove_compatibility.return_value = True


# ============================================================================
# Config Version Endpoints
# ============================================================================

class TestConfigVersionEndpoints:
    """Tests for config versioning endpoints."""

    def test_list_config_versions(self, client, auth_headers, mock_model_registry):
        """GET /settings/models/config/versions returns list."""
        response = client.get("/api/v1/settings/models/config/versions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_get_config_version_detail(self, client, auth_headers, mock_model_registry):
        """GET /settings/models/config/versions/{id} returns snapshot."""
        response = client.get("/api/v1/settings/models/config/versions/1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "config_snapshot" in data

    def test_rollback_config(self, client, auth_headers, mock_model_registry):
        """POST /settings/models/config/rollback restores config."""
        response = client.post(
            "/api/v1/settings/models/config/rollback",
            json={"version_id": 1},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
