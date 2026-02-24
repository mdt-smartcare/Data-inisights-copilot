"""
Unit tests for backend/services/model_registry_service.py

Tests ModelRegistryService CRUD, compatibility, and versioning with a real
temporary SQLite database (no mocks for DB layer — these are true integration tests).
"""
import pytest
import sqlite3
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import MagicMock

# Set test environment variables
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with model registry tables."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create tables (same as migration 011)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS embedding_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            max_tokens INTEGER DEFAULT 512,
            is_custom INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        );

        CREATE TABLE IF NOT EXISTS llm_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            context_length INTEGER NOT NULL,
            max_output_tokens INTEGER DEFAULT 4096,
            parameters TEXT DEFAULT '{}',
            is_custom INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        );

        CREATE TABLE IF NOT EXISTS embedding_llm_compatibility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            embedding_model_id INTEGER NOT NULL,
            llm_model_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(embedding_model_id) REFERENCES embedding_models(id) ON DELETE CASCADE,
            FOREIGN KEY(llm_model_id) REFERENCES llm_models(id) ON DELETE CASCADE,
            UNIQUE(embedding_model_id, llm_model_id)
        );

        CREATE TABLE IF NOT EXISTS model_config_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_type TEXT NOT NULL,
            config_snapshot TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_by TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Seed embedding models
        INSERT INTO embedding_models (provider, model_name, display_name, dimensions, max_tokens, is_custom, is_active)
        VALUES ('bge-m3', 'BAAI/bge-m3', 'BGE-M3', 1024, 8192, 0, 1),
               ('openai', 'text-embedding-3-small', 'OpenAI Small', 1536, 8191, 0, 0);

        -- Seed LLM models
        INSERT INTO llm_models (provider, model_name, display_name, context_length, max_output_tokens, parameters, is_custom, is_active)
        VALUES ('openai', 'gpt-4o', 'GPT-4o', 128000, 16384, '{"temperature": 0.0}', 0, 1),
               ('anthropic', 'claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet', 200000, 8192, '{"temperature": 0.0}', 0, 0);

        -- Seed compatibility
        INSERT INTO embedding_llm_compatibility (embedding_model_id, llm_model_id)
        SELECT e.id, l.id FROM embedding_models e CROSS JOIN llm_models l;
    """)
    conn.commit()
    conn.close()

    yield db_path

    os.unlink(db_path)


@pytest.fixture
def mock_db_service(temp_db):
    """Create a mock db_service that returns connections to the temp DB."""
    service = MagicMock()
    service.get_connection.side_effect = lambda: _make_conn(temp_db)
    return service


def _make_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def registry_service(mock_db_service):
    """Create a ModelRegistryService with the mock db."""
    from backend.services.model_registry_service import ModelRegistryService
    return ModelRegistryService(db_service=mock_db_service)


# ============================================================================
# Embedding Model CRUD Tests
# ============================================================================

class TestEmbeddingModelCRUD:
    """Tests for embedding model CRUD operations."""

    def test_list_embedding_models(self, registry_service):
        """Test listing returns seeded embedding models."""
        models = registry_service.list_embedding_models()
        assert len(models) == 2
        names = [m["model_name"] for m in models]
        assert "BAAI/bge-m3" in names
        assert "text-embedding-3-small" in names

    def test_get_active_embedding_model(self, registry_service):
        """Test getting the active embedding model."""
        active = registry_service.get_active_embedding_model()
        assert active is not None
        assert active["model_name"] == "BAAI/bge-m3"
        assert active["is_active"] == 1

    def test_add_embedding_model(self, registry_service):
        """Test adding a custom embedding model."""
        from backend.services.model_registry_service import EmbeddingModelCreate
        data = EmbeddingModelCreate(
            provider="custom",
            model_name="my-custom-emb",
            display_name="My Custom Embedding",
            dimensions=768,
            max_tokens=512
        )
        result = registry_service.add_embedding_model(data, created_by="testuser")
        assert result["model_name"] == "my-custom-emb"
        assert result["is_custom"] == 1
        assert result["is_active"] == 0  # Not activated by default

        # Verify it's in the list now
        models = registry_service.list_embedding_models()
        assert len(models) == 3

    def test_add_duplicate_embedding_model_raises(self, registry_service):
        """Test adding a duplicate model raises ValueError."""
        from backend.services.model_registry_service import EmbeddingModelCreate
        data = EmbeddingModelCreate(
            provider="bge-m3",
            model_name="BAAI/bge-m3",  # Already exists
            display_name="Duplicate",
            dimensions=1024,
        )
        with pytest.raises(ValueError, match="already exists"):
            registry_service.add_embedding_model(data)

    def test_activate_embedding_model(self, registry_service):
        """Test activating an embedding model deactivates others."""
        # Activate the second model (id=2)
        result = registry_service.activate_embedding_model(2, updated_by="admin")
        assert result["is_active"] == 1
        assert result["model_name"] == "text-embedding-3-small"

        # Old model should be deactivated
        models = registry_service.list_embedding_models()
        active_models = [m for m in models if m["is_active"] == 1]
        assert len(active_models) == 1
        assert active_models[0]["model_name"] == "text-embedding-3-small"

    def test_activate_nonexistent_model_raises(self, registry_service):
        """Test activating a nonexistent model raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            registry_service.activate_embedding_model(999)


# ============================================================================
# LLM Model CRUD Tests
# ============================================================================

class TestLLMModelCRUD:
    """Tests for LLM model CRUD operations."""

    def test_list_llm_models(self, registry_service):
        """Test listing returns seeded LLM models."""
        models = registry_service.list_llm_models()
        assert len(models) == 2
        names = [m["model_name"] for m in models]
        assert "gpt-4o" in names

    def test_get_active_llm_model(self, registry_service):
        """Test getting the active LLM model."""
        active = registry_service.get_active_llm_model()
        assert active is not None
        assert active["model_name"] == "gpt-4o"

    def test_add_llm_model(self, registry_service):
        """Test adding a custom LLM model."""
        from backend.services.model_registry_service import LLMModelCreate
        data = LLMModelCreate(
            provider="custom",
            model_name="my-custom-llm",
            display_name="My Custom LLM",
            context_length=4096,
            max_output_tokens=2048,
            parameters={"temperature": 0.5}
        )
        result = registry_service.add_llm_model(data, created_by="testuser")
        assert result["model_name"] == "my-custom-llm"
        assert result["is_custom"] == 1
        assert result["is_active"] == 0

    def test_add_duplicate_llm_model_raises(self, registry_service):
        """Test adding a duplicate LLM model raises ValueError."""
        from backend.services.model_registry_service import LLMModelCreate
        data = LLMModelCreate(
            provider="openai",
            model_name="gpt-4o",
            display_name="Dup",
            context_length=128000,
        )
        with pytest.raises(ValueError, match="already exists"):
            registry_service.add_llm_model(data)

    def test_activate_llm_model_compatible(self, registry_service):
        """Test activating a compatible LLM model succeeds."""
        result = registry_service.activate_llm_model(2, updated_by="admin")
        assert result["is_active"] == 1
        assert result["model_name"] == "claude-3-5-sonnet-20241022"

    def test_activate_incompatible_llm_raises(self, registry_service):
        """Test activating an LLM without compatibility mapping raises."""
        from backend.services.model_registry_service import LLMModelCreate
        # Add unlinked LLM
        data = LLMModelCreate(
            provider="custom", model_name="unlinked-llm",
            display_name="Unlinked", context_length=4096
        )
        new_model = registry_service.add_llm_model(data)
        # No compatibility mapping → should fail
        with pytest.raises(ValueError, match="not compatible"):
            registry_service.activate_llm_model(new_model["id"])

    def test_activate_nonexistent_llm_raises(self, registry_service):
        """Test activating a nonexistent LLM raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            registry_service.activate_llm_model(999)


# ============================================================================
# Compatibility Tests
# ============================================================================

class TestCompatibilityMapping:
    """Tests for compatibility mapping CRUD."""

    def test_get_compatibility_table(self, registry_service):
        """Test getting the full compatibility table."""
        table = registry_service.get_compatibility_table()
        assert len(table) == 4  # 2 embeddings × 2 LLMs
        assert all("embedding_model_name" in r for r in table)
        assert all("llm_model_name" in r for r in table)

    def test_get_compatible_llms_for_active(self, registry_service):
        """Test getting compatible LLMs for active embedding."""
        compatible = registry_service.get_compatible_llms()
        assert len(compatible) == 2
        names = [c["model_name"] for c in compatible]
        assert "gpt-4o" in names

    def test_get_compatible_llms_by_id(self, registry_service):
        """Test getting compatible LLMs by embedding model ID."""
        compatible = registry_service.get_compatible_llms(embedding_model_id=2)
        assert len(compatible) == 2

    def test_add_compatibility(self, registry_service):
        """Test adding a new compatibility mapping."""
        from backend.services.model_registry_service import LLMModelCreate, CompatibilityCreate
        # Add a new LLM
        new_llm = registry_service.add_llm_model(LLMModelCreate(
            provider="custom", model_name="new-llm",
            display_name="New", context_length=4096
        ))
        # Add compatibility
        data = CompatibilityCreate(embedding_model_id=1, llm_model_id=new_llm["id"])
        result = registry_service.add_compatibility(data)
        assert result["embedding_model_id"] == 1
        assert result["llm_model_id"] == new_llm["id"]

        # Verify
        compatible = registry_service.get_compatible_llms(embedding_model_id=1)
        assert len(compatible) == 3

    def test_add_duplicate_compatibility_raises(self, registry_service):
        """Test adding a duplicate mapping raises ValueError."""
        from backend.services.model_registry_service import CompatibilityCreate
        data = CompatibilityCreate(embedding_model_id=1, llm_model_id=1)
        with pytest.raises(ValueError, match="already exists"):
            registry_service.add_compatibility(data)

    def test_remove_compatibility(self, registry_service):
        """Test removing a compatibility mapping."""
        table = registry_service.get_compatibility_table()
        first_id = table[0]["id"]
        deleted = registry_service.remove_compatibility(first_id)
        assert deleted is True

        # Verify removal
        new_table = registry_service.get_compatibility_table()
        assert len(new_table) == len(table) - 1

    def test_remove_nonexistent_mapping(self, registry_service):
        """Test removing a nonexistent mapping returns False."""
        deleted = registry_service.remove_compatibility(999)
        assert deleted is False


# ============================================================================
# Config Versioning Tests
# ============================================================================

class TestConfigVersioning:
    """Tests for config version snapshots and rollback."""

    def test_version_created_on_activate(self, registry_service):
        """Test that activating a model creates a version snapshot."""
        # Activate a different model
        registry_service.activate_embedding_model(2, updated_by="admin")

        versions = registry_service.list_config_versions(config_type="embedding")
        assert len(versions) >= 1
        assert versions[0]["config_type"] == "embedding"
        assert versions[0]["updated_by"] == "admin"

    def test_list_config_versions(self, registry_service):
        """Test listing config versions."""
        # Create some versions
        registry_service.activate_embedding_model(1, updated_by="user1")
        registry_service.activate_embedding_model(2, updated_by="user2")

        versions = registry_service.list_config_versions()
        assert len(versions) >= 2

    def test_get_config_version_detail(self, registry_service):
        """Test getting a specific version snapshot."""
        registry_service.activate_embedding_model(2, updated_by="admin")
        versions = registry_service.list_config_versions(config_type="embedding")
        assert len(versions) > 0

        detail = registry_service.get_config_version(versions[0]["id"])
        assert detail is not None
        assert isinstance(detail["config_snapshot"], list)

    def test_rollback_to_version(self, registry_service):
        """Test rolling back to a previous version."""
        # Activate model 1 (creates version)
        registry_service.activate_embedding_model(1, updated_by="admin")
        v1_versions = registry_service.list_config_versions(config_type="embedding")

        # Activate model 2 (creates version)
        registry_service.activate_embedding_model(2, updated_by="admin")

        # Verify model 2 is active
        active = registry_service.get_active_embedding_model()
        assert active["model_name"] == "text-embedding-3-small"

        # Rollback to version where model 1 was active
        result = registry_service.rollback_to_version(v1_versions[0]["id"], updated_by="admin")
        assert result["success"] is True

        # Verify model 1 is active again
        active = registry_service.get_active_embedding_model()
        assert active["model_name"] == "BAAI/bge-m3"

    def test_rollback_nonexistent_version_raises(self, registry_service):
        """Test rollback to nonexistent version raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            registry_service.rollback_to_version(999)


# ============================================================================
# Schema Validation Tests
# ============================================================================

class TestSchemaValidation:
    """Tests for Pydantic schema validation."""

    def test_embedding_model_create_valid(self):
        """Test valid embedding model creation schema."""
        from backend.services.model_registry_service import EmbeddingModelCreate
        model = EmbeddingModelCreate(
            provider="openai", model_name="test", display_name="Test",
            dimensions=256, max_tokens=512
        )
        assert model.provider == "openai"

    def test_embedding_model_create_invalid_provider(self):
        """Test invalid provider is rejected."""
        from backend.services.model_registry_service import EmbeddingModelCreate
        with pytest.raises(Exception):
            EmbeddingModelCreate(
                provider="invalid", model_name="test",
                display_name="Test", dimensions=256
            )

    def test_embedding_model_create_invalid_dimensions(self):
        """Test invalid dimensions are rejected."""
        from backend.services.model_registry_service import EmbeddingModelCreate
        with pytest.raises(Exception):
            EmbeddingModelCreate(
                provider="openai", model_name="test",
                display_name="Test", dimensions=10  # Too small (min 64)
            )

    def test_llm_model_create_valid(self):
        """Test valid LLM model creation schema."""
        from backend.services.model_registry_service import LLMModelCreate
        model = LLMModelCreate(
            provider="openai", model_name="test", display_name="Test",
            context_length=4096
        )
        assert model.provider == "openai"

    def test_llm_model_create_invalid_provider(self):
        """Test invalid provider is rejected."""
        from backend.services.model_registry_service import LLMModelCreate
        with pytest.raises(Exception):
            LLMModelCreate(
                provider="invalid", model_name="test",
                display_name="Test", context_length=4096
            )

    def test_compatibility_create_valid(self):
        """Test valid compatibility mapping schema."""
        from backend.services.model_registry_service import CompatibilityCreate
        mapping = CompatibilityCreate(embedding_model_id=1, llm_model_id=1)
        assert mapping.embedding_model_id == 1

    def test_compatibility_create_invalid_id(self):
        """Test invalid IDs are rejected."""
        from backend.services.model_registry_service import CompatibilityCreate
        with pytest.raises(Exception):
            CompatibilityCreate(embedding_model_id=0, llm_model_id=1)
