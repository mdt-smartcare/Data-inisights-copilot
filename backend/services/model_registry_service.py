"""
Model Registry Service - DB-backed CRUD for embedding & LLM model metadata,
compatibility mappings, and versioned configuration snapshots.

This service complements the existing EmbeddingRegistry / LLMRegistry singletons
(which manage runtime provider instances) by providing persistent model metadata,
custom model registration, and embedding↔LLM compatibility rules.
"""
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class EmbeddingModelCreate(BaseModel):
    """Schema for registering a new embedding model."""
    provider: str = Field(..., min_length=1, max_length=50, description="Provider type (e.g., bge-m3, openai)")
    model_name: str = Field(..., min_length=1, max_length=200, description="Unique model identifier")
    display_name: str = Field(..., min_length=1, max_length=200, description="Human-readable label")
    dimensions: int = Field(..., ge=64, le=8192, description="Embedding vector dimension")
    max_tokens: int = Field(default=512, ge=1, le=32768, description="Max input token length")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"bge-m3", "openai", "sentence-transformers", "cohere", "custom"}
        if v not in allowed:
            raise ValueError(f"Provider must be one of {allowed}")
        return v


class LLMModelCreate(BaseModel):
    """Schema for registering a new LLM model."""
    provider: str = Field(..., min_length=1, max_length=50, description="Provider type (e.g., openai, anthropic)")
    model_name: str = Field(..., min_length=1, max_length=200, description="Unique model identifier")
    display_name: str = Field(..., min_length=1, max_length=200, description="Human-readable label")
    context_length: int = Field(..., ge=1, le=2_000_000, description="Max context window (tokens)")
    max_output_tokens: int = Field(default=4096, ge=1, le=128_000, description="Max output tokens")
    parameters: Dict[str, Any] = Field(default_factory=lambda: {"temperature": 0.0}, description="Default params")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"openai", "azure", "anthropic", "ollama", "huggingface", "local", "custom"}
        if v not in allowed:
            raise ValueError(f"Provider must be one of {allowed}")
        return v


class CompatibilityCreate(BaseModel):
    """Schema for adding a compatibility mapping."""
    embedding_model_id: int = Field(..., gt=0)
    llm_model_id: int = Field(..., gt=0)


class ConfigRollbackRequest(BaseModel):
    """Schema for rolling back to a config version."""
    version_id: int = Field(..., gt=0, description="ID of the version to rollback to")


# ============================================================================
# Service
# ============================================================================

class ModelRegistryService:
    """
    Persistent model registry with CRUD, compatibility, and versioning.

    Uses the same DatabaseService / connection pattern as SettingsService.
    """

    def __init__(self, db_service=None):
        if db_service is None:
            from backend.sqliteDb.db import get_db_service
            db_service = get_db_service()
        self.db = db_service
        logger.info("ModelRegistryService initialized")

    # ------------------------------------------------------------------
    # Embedding Models
    # ------------------------------------------------------------------

    def list_embedding_models(self) -> List[Dict[str, Any]]:
        """List all registered embedding models."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM embedding_models ORDER BY is_active DESC, provider, model_name"
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_active_embedding_model(self) -> Optional[Dict[str, Any]]:
        """Get the currently active embedding model row."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM embedding_models WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def add_embedding_model(self, data: EmbeddingModelCreate, created_by: str = "system") -> Dict[str, Any]:
        """Register a new embedding model."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO embedding_models
                   (provider, model_name, display_name, dimensions, max_tokens, is_custom, is_active, updated_by)
                   VALUES (?, ?, ?, ?, ?, 1, 0, ?)""",
                (data.provider, data.model_name, data.display_name,
                 data.dimensions, data.max_tokens, created_by),
            )
            conn.commit()
            new_id = cursor.lastrowid
            cursor.execute("SELECT * FROM embedding_models WHERE id = ?", (new_id,))
            return dict(cursor.fetchone())
        except Exception as e:
            conn.rollback()
            if "UNIQUE constraint" in str(e):
                raise ValueError(f"Embedding model '{data.model_name}' already exists")
            raise
        finally:
            conn.close()

    def activate_embedding_model(self, model_id: int, updated_by: str = "system") -> Dict[str, Any]:
        """
        Set a model as the active embedding model (deactivates others).
        Also saves a config version snapshot.
        """
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Verify model exists
            cursor.execute("SELECT * FROM embedding_models WHERE id = ?", (model_id,))
            model = cursor.fetchone()
            if not model:
                raise ValueError(f"Embedding model with id={model_id} not found")

            # Deactivate all, activate target
            cursor.execute("UPDATE embedding_models SET is_active = 0, updated_at = CURRENT_TIMESTAMP")
            cursor.execute(
                "UPDATE embedding_models SET is_active = 1, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                (updated_by, model_id),
            )
            conn.commit()

            # Save version snapshot
            self._save_version_snapshot("embedding", updated_by, conn)

            logger.info(f"Embedding model {model_id} activated by {updated_by}")
            cursor.execute("SELECT * FROM embedding_models WHERE id = ?", (model_id,))
            return dict(cursor.fetchone())
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # LLM Models
    # ------------------------------------------------------------------

    def list_llm_models(self) -> List[Dict[str, Any]]:
        """List all registered LLM models."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM llm_models ORDER BY is_active DESC, provider, model_name"
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_active_llm_model(self) -> Optional[Dict[str, Any]]:
        """Get the currently active LLM model row."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM llm_models WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def add_llm_model(self, data: LLMModelCreate, created_by: str = "system") -> Dict[str, Any]:
        """Register a new LLM model."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            params_json = json.dumps(data.parameters)
            cursor.execute(
                """INSERT INTO llm_models
                   (provider, model_name, display_name, context_length, max_output_tokens,
                    parameters, is_custom, is_active, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)""",
                (data.provider, data.model_name, data.display_name,
                 data.context_length, data.max_output_tokens, params_json, created_by),
            )
            conn.commit()
            new_id = cursor.lastrowid
            cursor.execute("SELECT * FROM llm_models WHERE id = ?", (new_id,))
            return dict(cursor.fetchone())
        except Exception as e:
            conn.rollback()
            if "UNIQUE constraint" in str(e):
                raise ValueError(f"LLM model '{data.model_name}' already exists")
            raise
        finally:
            conn.close()

    def activate_llm_model(self, model_id: int, updated_by: str = "system") -> Dict[str, Any]:
        """
        Set a model as the active LLM (deactivates others).
        Validates compatibility with the active embedding model first.
        """
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Verify model exists
            cursor.execute("SELECT * FROM llm_models WHERE id = ?", (model_id,))
            model = cursor.fetchone()
            if not model:
                raise ValueError(f"LLM model with id={model_id} not found")

            # Check compatibility with current active embedding
            cursor.execute("SELECT id FROM embedding_models WHERE is_active = 1 LIMIT 1")
            active_emb = cursor.fetchone()
            if active_emb:
                cursor.execute(
                    """SELECT 1 FROM embedding_llm_compatibility
                       WHERE embedding_model_id = ? AND llm_model_id = ?""",
                    (active_emb["id"], model_id),
                )
                if not cursor.fetchone():
                    raise ValueError(
                        f"LLM model '{dict(model)['model_name']}' is not compatible "
                        f"with the active embedding model. Add a compatibility mapping first."
                    )

            # Deactivate all, activate target
            cursor.execute("UPDATE llm_models SET is_active = 0, updated_at = CURRENT_TIMESTAMP")
            cursor.execute(
                "UPDATE llm_models SET is_active = 1, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                (updated_by, model_id),
            )
            conn.commit()

            # Save version snapshot
            self._save_version_snapshot("llm", updated_by, conn)

            logger.info(f"LLM model {model_id} activated by {updated_by}")
            cursor.execute("SELECT * FROM llm_models WHERE id = ?", (model_id,))
            return dict(cursor.fetchone())
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Compatibility
    # ------------------------------------------------------------------

    def get_compatibility_table(self) -> List[Dict[str, Any]]:
        """Full compatibility table with model names."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.id, c.embedding_model_id, c.llm_model_id,
                       e.model_name AS embedding_model_name, e.display_name AS embedding_display_name,
                       l.model_name AS llm_model_name, l.display_name AS llm_display_name,
                       c.created_at
                FROM embedding_llm_compatibility c
                JOIN embedding_models e ON c.embedding_model_id = e.id
                JOIN llm_models l ON c.llm_model_id = l.id
                ORDER BY e.model_name, l.model_name
            """)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_compatible_llms(self, embedding_model_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get LLM models compatible with a specific (or the active) embedding model.
        """
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            if embedding_model_id is None:
                cursor.execute("SELECT id FROM embedding_models WHERE is_active = 1 LIMIT 1")
                row = cursor.fetchone()
                if not row:
                    return []
                embedding_model_id = row["id"]

            cursor.execute("""
                SELECT l.*
                FROM llm_models l
                JOIN embedding_llm_compatibility c ON l.id = c.llm_model_id
                WHERE c.embedding_model_id = ?
                ORDER BY l.is_active DESC, l.provider, l.model_name
            """, (embedding_model_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def add_compatibility(self, data: CompatibilityCreate) -> Dict[str, Any]:
        """Add a compatibility mapping."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Verify both models exist
            cursor.execute("SELECT id FROM embedding_models WHERE id = ?", (data.embedding_model_id,))
            if not cursor.fetchone():
                raise ValueError(f"Embedding model {data.embedding_model_id} not found")
            cursor.execute("SELECT id FROM llm_models WHERE id = ?", (data.llm_model_id,))
            if not cursor.fetchone():
                raise ValueError(f"LLM model {data.llm_model_id} not found")

            cursor.execute(
                """INSERT INTO embedding_llm_compatibility (embedding_model_id, llm_model_id)
                   VALUES (?, ?)""",
                (data.embedding_model_id, data.llm_model_id),
            )
            conn.commit()
            new_id = cursor.lastrowid
            return {"id": new_id, "embedding_model_id": data.embedding_model_id,
                    "llm_model_id": data.llm_model_id}
        except Exception as e:
            conn.rollback()
            if "UNIQUE constraint" in str(e):
                raise ValueError("This compatibility mapping already exists")
            raise
        finally:
            conn.close()

    def remove_compatibility(self, mapping_id: int) -> bool:
        """Remove a compatibility mapping by ID."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM embedding_llm_compatibility WHERE id = ?", (mapping_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    def _save_version_snapshot(self, config_type: str, updated_by: str, conn=None):
        """Save a config snapshot internally (uses existing or new connection)."""
        own_conn = conn is None
        if own_conn:
            conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Get next version number
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) FROM model_config_versions WHERE config_type = ?",
                (config_type,),
            )
            next_version = cursor.fetchone()[0] + 1

            # Build snapshot
            if config_type == "embedding":
                cursor.execute("SELECT * FROM embedding_models")
            elif config_type == "llm":
                cursor.execute("SELECT * FROM llm_models")
            else:
                # full snapshot
                cursor.execute("SELECT * FROM embedding_models")
                emb = [dict(r) for r in cursor.fetchall()]
                cursor.execute("SELECT * FROM llm_models")
                llm = [dict(r) for r in cursor.fetchall()]
                cursor.execute("SELECT * FROM embedding_llm_compatibility")
                compat = [dict(r) for r in cursor.fetchall()]
                snapshot = json.dumps({"embedding_models": emb, "llm_models": llm, "compatibility": compat})
                cursor.execute(
                    "INSERT INTO model_config_versions (config_type, config_snapshot, version, updated_by) VALUES (?, ?, ?, ?)",
                    (config_type, snapshot, next_version, updated_by),
                )
                conn.commit()
                return

            rows = [dict(r) for r in cursor.fetchall()]
            snapshot = json.dumps(rows)

            cursor.execute(
                "INSERT INTO model_config_versions (config_type, config_snapshot, version, updated_by) VALUES (?, ?, ?, ?)",
                (config_type, snapshot, next_version, updated_by),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save config version snapshot: {e}")
        finally:
            if own_conn:
                conn.close()

    def list_config_versions(self, config_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """List versioned config snapshots."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            if config_type:
                cursor.execute(
                    "SELECT id, config_type, version, updated_by, updated_at FROM model_config_versions WHERE config_type = ? ORDER BY version DESC LIMIT ?",
                    (config_type, limit),
                )
            else:
                cursor.execute(
                    "SELECT id, config_type, version, updated_by, updated_at FROM model_config_versions ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_config_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific config version snapshot."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM model_config_versions WHERE id = ?", (version_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result["config_snapshot"] = json.loads(result["config_snapshot"])
                return result
            return None
        finally:
            conn.close()

    def rollback_to_version(self, version_id: int, updated_by: str = "system") -> Dict[str, Any]:
        """
        Rollback model configuration to a previous version snapshot.
        Restores is_active flags from the snapshot.
        """
        version = self.get_config_version(version_id)
        if not version:
            raise ValueError(f"Config version {version_id} not found")

        config_type = version["config_type"]
        snapshot = version["config_snapshot"]
        conn = self.db.get_connection()

        try:
            cursor = conn.cursor()

            if config_type == "embedding" and isinstance(snapshot, list):
                for model in snapshot:
                    cursor.execute(
                        "UPDATE embedding_models SET is_active = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                        (model.get("is_active", 0), updated_by, model["id"]),
                    )
            elif config_type == "llm" and isinstance(snapshot, list):
                for model in snapshot:
                    cursor.execute(
                        "UPDATE llm_models SET is_active = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                        (model.get("is_active", 0), updated_by, model["id"]),
                    )
            elif config_type == "full" and isinstance(snapshot, dict):
                for model in snapshot.get("embedding_models", []):
                    cursor.execute(
                        "UPDATE embedding_models SET is_active = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                        (model.get("is_active", 0), updated_by, model["id"]),
                    )
                for model in snapshot.get("llm_models", []):
                    cursor.execute(
                        "UPDATE llm_models SET is_active = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                        (model.get("is_active", 0), updated_by, model["id"]),
                    )
            else:
                raise ValueError(f"Unknown config_type '{config_type}' or invalid snapshot format")

            conn.commit()

            # Save new version to track the rollback
            self._save_version_snapshot(config_type, updated_by)

            logger.info(f"Rolled back {config_type} config to version {version_id} by {updated_by}")
            return {
                "success": True,
                "config_type": config_type,
                "restored_version": version["version"],
                "rolled_back_by": updated_by,
            }
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================================
# Singleton
# ============================================================================

_model_registry_service: Optional[ModelRegistryService] = None


def get_model_registry_service() -> ModelRegistryService:
    """Get the singleton ModelRegistryService instance."""
    global _model_registry_service
    if _model_registry_service is None:
        _model_registry_service = ModelRegistryService()
    return _model_registry_service
