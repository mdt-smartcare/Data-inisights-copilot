"""
Model Registry Service - DB-backed CRUD for embedding & LLM model metadata,
compatibility mappings, and versioned configuration snapshots.

This service complements the existing EmbeddingRegistry / LLMRegistry singletons
(which manage runtime provider instances) by providing persistent model metadata,
custom model registration, and embedding↔LLM compatibility rules.

ENHANCED with:
- Curated Model Catalog with pre-validated specs
- Automatic system_settings sync when activating models
- Dimension change detection with rebuild warnings
- Model validation before activation
"""
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from backend.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# CURATED MODEL CATALOG
# Pre-validated models with accurate specifications
# ============================================================================

class ModelCategory(str, Enum):
    """Categories for embedding models based on use case."""
    GENERAL = "general"
    MULTILINGUAL = "multilingual"
    CODE = "code"
    MEDICAL = "medical"
    FAST = "fast"


class CatalogModel(BaseModel):
    """Schema for a catalog model entry."""
    provider: str
    model_name: str
    display_name: str
    dimensions: int
    max_tokens: int
    category: ModelCategory
    description: str
    speed_rating: int  # 1-5, 5 being fastest
    quality_rating: int  # 1-5, 5 being best quality
    local: bool  # True if runs locally, False if API-based
    requires_api_key: bool
    recommended_batch_size: int
    model_size_mb: Optional[int] = None  # For local models


# Curated catalog of supported embedding models
EMBEDDING_MODEL_CATALOG: Dict[str, CatalogModel] = {
    # ========== LOCAL MODELS (No API key required) ==========
    "BAAI/bge-base-en-v1.5": CatalogModel(
        provider="sentence-transformers",
        model_name="BAAI/bge-base-en-v1.5",
        display_name="BGE-Base-EN v1.5 (Local)",
        dimensions=768,
        max_tokens=512,
        category=ModelCategory.GENERAL,
        description="Best balance of speed and quality for English text. Recommended for tabular/structured data.",
        speed_rating=4,
        quality_rating=4,
        local=True,
        requires_api_key=False,
        recommended_batch_size=128,
        model_size_mb=438,
    ),
    "BAAI/bge-m3": CatalogModel(
        provider="bge-m3",
        model_name="BAAI/bge-m3",
        display_name="BGE-M3 (Local)",
        dimensions=1024,
        max_tokens=8192,
        category=ModelCategory.MULTILINGUAL,
        description="Multi-lingual, multi-granularity model. Best for documents in multiple languages.",
        speed_rating=2,
        quality_rating=5,
        local=True,
        requires_api_key=False,
        recommended_batch_size=64,
        model_size_mb=2200,
    ),
    "BAAI/bge-small-en-v1.5": CatalogModel(
        provider="sentence-transformers",
        model_name="BAAI/bge-small-en-v1.5",
        display_name="BGE-Small-EN v1.5 (Local)",
        dimensions=384,
        max_tokens=512,
        category=ModelCategory.FAST,
        description="Fastest local model. Good for prototyping or when speed is critical.",
        speed_rating=5,
        quality_rating=3,
        local=True,
        requires_api_key=False,
        recommended_batch_size=256,
        model_size_mb=133,
    ),
    "BAAI/bge-large-en-v1.5": CatalogModel(
        provider="sentence-transformers",
        model_name="BAAI/bge-large-en-v1.5",
        display_name="BGE-Large-EN v1.5 (Local)",
        dimensions=1024,
        max_tokens=512,
        category=ModelCategory.GENERAL,
        description="Highest quality local English model. Best for complex semantic search.",
        speed_rating=3,
        quality_rating=5,
        local=True,
        requires_api_key=False,
        recommended_batch_size=64,
        model_size_mb=1340,
    ),
    "sentence-transformers/all-MiniLM-L6-v2": CatalogModel(
        provider="sentence-transformers",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        display_name="MiniLM-L6-v2 (Local)",
        dimensions=384,
        max_tokens=512,
        category=ModelCategory.FAST,
        description="Ultra-fast, lightweight model. Good for simple semantic matching.",
        speed_rating=5,
        quality_rating=3,
        local=True,
        requires_api_key=False,
        recommended_batch_size=256,
        model_size_mb=91,
    ),
    "sentence-transformers/all-mpnet-base-v2": CatalogModel(
        provider="sentence-transformers",
        model_name="sentence-transformers/all-mpnet-base-v2",
        display_name="MPNet-Base v2 (Local)",
        dimensions=768,
        max_tokens=512,
        category=ModelCategory.GENERAL,
        description="High quality general-purpose model. Good alternative to BGE-base.",
        speed_rating=4,
        quality_rating=4,
        local=True,
        requires_api_key=False,
        recommended_batch_size=128,
        model_size_mb=438,
    ),
    # ========== API-BASED MODELS (Require API key) ==========
    "text-embedding-3-small": CatalogModel(
        provider="openai",
        model_name="text-embedding-3-small",
        display_name="OpenAI Embedding 3 Small",
        dimensions=1536,
        max_tokens=8191,
        category=ModelCategory.GENERAL,
        description="OpenAI's efficient embedding model. Good balance of cost and quality.",
        speed_rating=4,
        quality_rating=4,
        local=False,
        requires_api_key=True,
        recommended_batch_size=500,
    ),
    "text-embedding-3-large": CatalogModel(
        provider="openai",
        model_name="text-embedding-3-large",
        display_name="OpenAI Embedding 3 Large",
        dimensions=3072,
        max_tokens=8191,
        category=ModelCategory.GENERAL,
        description="OpenAI's highest quality embedding model. Best for complex retrieval tasks.",
        speed_rating=3,
        quality_rating=5,
        local=False,
        requires_api_key=True,
        recommended_batch_size=500,
    ),
    "text-embedding-ada-002": CatalogModel(
        provider="openai",
        model_name="text-embedding-ada-002",
        display_name="OpenAI Ada 002 (Legacy)",
        dimensions=1536,
        max_tokens=8191,
        category=ModelCategory.GENERAL,
        description="OpenAI's legacy embedding model. Use embedding-3 models instead.",
        speed_rating=4,
        quality_rating=3,
        local=False,
        requires_api_key=True,
        recommended_batch_size=500,
    ),
}


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
        allowed = {"bge-m3", "openai", "sentence-transformers", "cohere", "custom", "huggingface", "ollama", "azure", "local"}
        if v not in allowed:
            raise ValueError(f"Provider must be one of {allowed}")
        return v


class EmbeddingModelFromCatalog(BaseModel):
    """Schema for adding a model from the curated catalog."""
    model_name: str = Field(..., description="Model name from the catalog (e.g., BAAI/bge-base-en-v1.5)")
    
    @field_validator("model_name")
    @classmethod
    def validate_in_catalog(cls, v: str) -> str:
        if v not in EMBEDDING_MODEL_CATALOG:
            available = list(EMBEDDING_MODEL_CATALOG.keys())
            raise ValueError(f"Model '{v}' not in catalog. Available: {available}")
        return v


class ModelActivationResult(BaseModel):
    """Result of activating a model, including rebuild warnings."""
    model: Dict[str, Any]
    dimension_changed: bool
    previous_dimensions: Optional[int]
    new_dimensions: int
    requires_rebuild: bool
    rebuild_warning: Optional[str]
    system_settings_updated: bool


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

    ENHANCED FEATURES:
    - get_model_catalog(): Returns curated catalog with specs
    - add_model_from_catalog(): Add pre-validated model from catalog
    - activate_embedding_model(): Now syncs system_settings and warns about rebuilds
    - validate_model_availability(): Check if model can be loaded
    """

    def __init__(self, db_service=None):
        if db_service is None:
            from backend.sqliteDb.db import get_db_service
            db_service = get_db_service()
        self.db = db_service
        logger.info("ModelRegistryService initialized")

    # ------------------------------------------------------------------
    # Model Catalog (NEW)
    # ------------------------------------------------------------------

    def get_model_catalog(self, category: Optional[str] = None, local_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get the curated model catalog with filtering options.
        
        Args:
            category: Filter by category (general, multilingual, fast, etc.)
            local_only: If True, only return models that run locally
            
        Returns:
            List of catalog model entries with full specifications
        """
        result = []
        for model_name, model in EMBEDDING_MODEL_CATALOG.items():
            if category and model.category.value != category:
                continue
            if local_only and not model.local:
                continue
            
            entry = model.model_dump()
            entry["catalog_key"] = model_name
            entry["category"] = model.category.value
            
            # Check if already registered in DB
            entry["is_registered"] = self._is_model_registered(model_name)
            
            result.append(entry)
        
        # Sort by quality rating descending, then speed rating descending
        result.sort(key=lambda x: (-x["quality_rating"], -x["speed_rating"]))
        return result

    def _is_model_registered(self, model_name: str) -> bool:
        """Check if a model is already in the registry."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM embedding_models WHERE model_name = ?", (model_name,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def add_model_from_catalog(self, model_name: str, created_by: str = "system") -> Dict[str, Any]:
        """
        Add a model from the curated catalog to the registry.
        
        This ensures correct dimensions and settings are used.
        
        Args:
            model_name: The catalog key (e.g., "BAAI/bge-base-en-v1.5")
            created_by: Username adding the model
            
        Returns:
            The newly registered model record
        """
        if model_name not in EMBEDDING_MODEL_CATALOG:
            raise ValueError(f"Model '{model_name}' not found in catalog. Use get_model_catalog() to see available models.")
        
        catalog_model = EMBEDDING_MODEL_CATALOG[model_name]
        
        # Check if already registered
        if self._is_model_registered(model_name):
            raise ValueError(f"Model '{model_name}' is already registered")
        
        # Create from catalog specs
        data = EmbeddingModelCreate(
            provider=catalog_model.provider,
            model_name=catalog_model.model_name,
            display_name=catalog_model.display_name,
            dimensions=catalog_model.dimensions,
            max_tokens=catalog_model.max_tokens,
        )
        
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO embedding_models
                   (provider, model_name, display_name, dimensions, max_tokens, is_custom, is_active, updated_by)
                   VALUES (?, ?, ?, ?, ?, 0, 0, ?)""",
                (data.provider, data.model_name, data.display_name,
                 data.dimensions, data.max_tokens, created_by),
            )
            conn.commit()
            new_id = cursor.lastrowid
            cursor.execute("SELECT * FROM embedding_models WHERE id = ?", (new_id,))
            result = dict(cursor.fetchone())
            
            # Add catalog metadata
            result["catalog_info"] = catalog_model.model_dump()
            
            logger.info(f"Added catalog model '{model_name}' to registry by {created_by}")
            return result
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_catalog_model_info(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get catalog info for a specific model."""
        if model_name in EMBEDDING_MODEL_CATALOG:
            return EMBEDDING_MODEL_CATALOG[model_name].model_dump()
        return None

    # ------------------------------------------------------------------
    # Embedding Models (ENHANCED)
    # ------------------------------------------------------------------

    def list_embedding_models(self) -> List[Dict[str, Any]]:
        """List all registered embedding models with catalog info."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM embedding_models ORDER BY is_active DESC, provider, model_name"
            )
            models = [dict(r) for r in cursor.fetchall()]
            
            # Enrich with catalog info
            for model in models:
                catalog_info = self.get_catalog_model_info(model["model_name"])
                if catalog_info:
                    model["catalog_info"] = catalog_info
                    model["is_catalog_model"] = True
                else:
                    model["is_catalog_model"] = False
                    
            return models
        finally:
            conn.close()

    def get_active_embedding_model(self) -> Optional[Dict[str, Any]]:
        """Get the currently active embedding model row."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM embedding_models WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            if row:
                result = dict(row)
                catalog_info = self.get_catalog_model_info(result["model_name"])
                if catalog_info:
                    result["catalog_info"] = catalog_info
                return result
            return None
        finally:
            conn.close()

    def add_embedding_model(self, data: EmbeddingModelCreate, created_by: str = "system") -> Dict[str, Any]:
        """Register a new embedding model."""
        # Validate against catalog if it exists
        if data.model_name in EMBEDDING_MODEL_CATALOG:
            catalog_model = EMBEDDING_MODEL_CATALOG[data.model_name]
            if data.dimensions != catalog_model.dimensions:
                logger.warning(
                    f"Model '{data.model_name}' dimensions ({data.dimensions}) don't match catalog ({catalog_model.dimensions}). "
                    f"Using catalog value."
                )
                data.dimensions = catalog_model.dimensions
        
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

    def activate_embedding_model(
        self, 
        model_id: int, 
        updated_by: str = "system",
        force: bool = False
    ) -> ModelActivationResult:
        """
        Set a model as the active embedding model (deactivates others).
        
        ENHANCED: 
        - Automatically syncs system_settings with new model config
        - Detects dimension changes and warns about required rebuilds
        - Returns detailed activation result
        
        Args:
            model_id: ID of the model to activate
            updated_by: Username making the change
            force: If True, skip validation checks
            
        Returns:
            ModelActivationResult with rebuild warnings if applicable
        """
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Get current active model for comparison
            cursor.execute("SELECT * FROM embedding_models WHERE is_active = 1 LIMIT 1")
            current_active = cursor.fetchone()
            previous_dimensions = dict(current_active)["dimensions"] if current_active else None

            # Verify target model exists
            cursor.execute("SELECT * FROM embedding_models WHERE id = ?", (model_id,))
            model = cursor.fetchone()
            if not model:
                raise ValueError(f"Embedding model with id={model_id} not found")
            
            model_dict = dict(model)
            new_dimensions = model_dict["dimensions"]
            
            # Check for dimension change
            dimension_changed = previous_dimensions is not None and previous_dimensions != new_dimensions
            requires_rebuild = dimension_changed
            rebuild_warning = None
            
            if dimension_changed:
                rebuild_warning = (
                    f"⚠️ DIMENSION CHANGE: {previous_dimensions}d → {new_dimensions}d. "
                    f"All existing vector databases must be rebuilt. "
                    f"Run a 'Full Rebuild' on each agent's Vector DB to apply the new model."
                )
                logger.warning(rebuild_warning)

            # Deactivate all, activate target
            cursor.execute("UPDATE embedding_models SET is_active = 0, updated_at = CURRENT_TIMESTAMP")
            cursor.execute(
                "UPDATE embedding_models SET is_active = 1, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = ?",
                (updated_by, model_id),
            )
            conn.commit()

            # Save version snapshot
            self._save_version_snapshot("embedding", updated_by, conn)

            # Sync system_settings (NEW)
            system_settings_updated = self._sync_system_settings(model_dict, updated_by)

            logger.info(f"Embedding model {model_id} ({model_dict['model_name']}) activated by {updated_by}")
            
            # Refresh model data
            cursor.execute("SELECT * FROM embedding_models WHERE id = ?", (model_id,))
            final_model = dict(cursor.fetchone())
            
            return ModelActivationResult(
                model=final_model,
                dimension_changed=dimension_changed,
                previous_dimensions=previous_dimensions,
                new_dimensions=new_dimensions,
                requires_rebuild=requires_rebuild,
                rebuild_warning=rebuild_warning,
                system_settings_updated=system_settings_updated,
            )
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _sync_system_settings(self, model: Dict[str, Any], updated_by: str) -> bool:
        """
        Sync the system_settings table with the newly activated model.
        
        This ensures the embedding provider uses the correct model configuration.
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Update system_settings for embedding category
            settings_updates = [
                ("model_name", model["model_name"]),
                ("dimensions", str(model["dimensions"])),
                ("provider", model["provider"]),
            ]
            
            # Determine model path for local models
            if model["provider"] in ("sentence-transformers", "bge-m3", "huggingface"):
                model_path = f"./models/{model['model_name'].replace('/', '_').replace('BAAI_', '')}"
                settings_updates.append(("model_path", model_path))
            
            for key, value in settings_updates:
                cursor.execute("""
                    UPDATE system_settings 
                    SET value = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                    WHERE category = 'embedding' AND key = ?
                """, (value, updated_by, key))
            
            conn.commit()
            logger.info(f"Synced system_settings with model: {model['model_name']}")
            return True
        except Exception as e:
            logger.error(f"Failed to sync system_settings: {e}")
            return False
        finally:
            conn.close()

    def validate_model_availability(self, model_name: str) -> Tuple[bool, str]:
        """
        Check if a model can be loaded/used.
        
        For local models, checks if model files exist or can be downloaded.
        For API models, checks if required API key is configured.
        
        Returns:
            Tuple of (is_available, message)
        """
        catalog_model = EMBEDDING_MODEL_CATALOG.get(model_name)
        
        if not catalog_model:
            # Custom model - assume available
            return True, "Custom model (availability not validated)"
        
        if catalog_model.requires_api_key:
            # Check for API key
            import os
            if catalog_model.provider == "openai":
                if not os.getenv("OPENAI_API_KEY"):
                    return False, "OpenAI API key not configured (set OPENAI_API_KEY environment variable)"
            elif catalog_model.provider == "cohere":
                if not os.getenv("COHERE_API_KEY"):
                    return False, "Cohere API key not configured (set COHERE_API_KEY environment variable)"
            return True, "API key configured"
        
        # Local model - check if downloadable
        try:
            from sentence_transformers import SentenceTransformer
            # Just check if the model name is valid (don't actually load it)
            return True, f"Local model available ({catalog_model.model_size_mb}MB)"
        except ImportError:
            return False, "sentence-transformers not installed"
        except Exception as e:
            return False, f"Model validation failed: {str(e)}"

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
    if (_model_registry_service is None):
        _model_registry_service = ModelRegistryService()
    return _model_registry_service
