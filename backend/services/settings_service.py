"""
Settings Service - Unified configuration management with caching and validation.
Provides CRUD operations for system settings with history tracking.
"""
import json
import logging
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from functools import lru_cache
from pydantic import BaseModel, Field, field_validator
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class SettingCategory(str, Enum):
    """Valid setting categories."""
    AUTH = "auth"
    EMBEDDING = "embedding"
    LLM = "llm"
    RAG = "rag"
    UI = "ui"
    SECURITY = "security"
    OBSERVABILITY = "observability"


class SettingValueType(str, Enum):
    """Types for setting values."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"
    SECRET = "secret"


# ============================================================================
# Pydantic Models for Settings Validation
# ============================================================================

class AuthSettings(BaseModel):
    """Authentication configuration settings."""
    provider: Literal["local", "oauth2", "ldap", "saml"] = "local"
    session_timeout_minutes: int = Field(default=720, gt=0)
    require_mfa: bool = False
    password_min_length: int = Field(default=8, ge=6, le=128)
    max_login_attempts: int = Field(default=5, ge=1, le=100)


class EmbeddingSettings(BaseModel):
    """Embedding model configuration settings."""
    provider: Literal["bge-m3", "openai", "sentence-transformers", "cohere"] = "bge-m3"
    model_name: str = "BAAI/bge-m3"
    model_path: str = "./models/bge-m3"
    batch_size: int = Field(default=128, ge=1, le=1024)
    dimensions: int = Field(default=1024, ge=64, le=4096)


class LLMSettings(BaseModel):
    """LLM provider configuration settings."""
    provider: Literal["openai", "azure", "anthropic", "ollama"] = "openai"
    model_name: str = "gpt-4o"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    api_key: str = ""  # Empty means use env var


class RAGSettings(BaseModel):
    """RAG pipeline configuration settings."""
    top_k_initial: int = Field(default=50, ge=1, le=500)
    top_k_final: int = Field(default=10, ge=1, le=100)
    hybrid_weights: List[float] = Field(default=[0.75, 0.25])
    rerank_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=150, ge=0, le=500)
    
    @field_validator('hybrid_weights')
    @classmethod
    def validate_weights(cls, v):
        if len(v) != 2:
            raise ValueError("hybrid_weights must have exactly 2 values")
        if abs(sum(v) - 1.0) > 0.01:
            raise ValueError("hybrid_weights must sum to 1.0")
        return v


class UISettings(BaseModel):
    """UI/theming configuration settings."""
    app_name: str = "Data Insights AI-Copilot"
    theme: Literal["light", "dark", "system"] = "light"
    primary_color: str = "#3B82F6"
    logo_url: str = ""


class SecuritySettings(BaseModel):
    """Security configuration settings."""
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    audit_retention_days: int = Field(default=90, ge=1, le=365)


class ObservabilitySettings(BaseModel):
    """Observability/logging configuration settings."""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    enable_tracing: bool = False
    trace_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    log_destinations: List[str] = ["console", "file"]
    log_file_path: str = "./logs/backend.log"
    log_max_size_mb: int = 100
    log_backup_count: int = 5
    langfuse_enabled: bool = False
    opentelemetry_enabled: bool = False
    otlp_endpoint: str = "http://localhost:4317"
    tracing_provider: Literal["none", "langfuse", "opentelemetry", "both"] = "none"
    observability_enabled: bool = False


# Mapping of category to validation model
SETTINGS_VALIDATORS = {
    SettingCategory.AUTH: AuthSettings,
    SettingCategory.EMBEDDING: EmbeddingSettings,
    SettingCategory.LLM: LLMSettings,
    SettingCategory.RAG: RAGSettings,
    SettingCategory.UI: UISettings,
    SettingCategory.SECURITY: SecuritySettings,
    SettingCategory.OBSERVABILITY: ObservabilitySettings,
}


# ============================================================================
# Settings Service
# ============================================================================

class SettingsService:
    """
    Unified settings management service.
    
    Provides:
    - CRUD operations for settings by category
    - In-memory caching with invalidation
    - Validation via Pydantic models
    - History tracking for audit and rollback
    """
    
    def __init__(self, db_service=None):
        """
        Initialize settings service.
        
        Args:
            db_service: Optional DatabaseService instance. If not provided,
                       will use the singleton from sqliteDb.db
        """
        if db_service is None:
            from backend.sqliteDb.db import get_db_service
            db_service = get_db_service()
        
        self.db = db_service
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_valid = False
        logger.info("SettingsService initialized")
    
    def _invalidate_cache(self):
        """Invalidate the settings cache."""
        self._cache = {}
        self._cache_valid = False
        logger.debug("Settings cache invalidated")
    
    def _ensure_cache(self):
        """Load all settings into cache if not already loaded."""
        if self._cache_valid:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT category, key, value, value_type, is_sensitive
                FROM system_settings
            """)
            rows = cursor.fetchall()
            
            self._cache = {}
            for row in rows:
                category = row['category']
                if category not in self._cache:
                    self._cache[category] = {}
                
                # Parse value based on type
                value = self._parse_value(row['value'], row['value_type'])
                self._cache[category][row['key']] = {
                    'value': value,
                    'value_type': row['value_type'],
                    'is_sensitive': row['is_sensitive']
                }
            
            self._cache_valid = True
            logger.debug(f"Settings cache loaded with {len(rows)} settings")
            
        finally:
            conn.close()
    
    def _parse_value(self, value_str: str, value_type: str) -> Any:
        """Parse a stored value string into its proper type."""
        try:
            if value_type == 'number':
                # Try int first, then float
                try:
                    return int(value_str)
                except ValueError:
                    return float(value_str)
            elif value_type == 'boolean':
                return value_str.lower() in ('true', '1', 'yes')
            elif value_type in ('json', 'string', 'secret'):
                return json.loads(value_str)
            else:
                return value_str
        except (json.JSONDecodeError, ValueError):
            return value_str
    
    def _serialize_value(self, value: Any, value_type: str) -> str:
        """Serialize a value for storage."""
        if value_type == 'number':
            return str(value)
        elif value_type == 'boolean':
            return 'true' if value else 'false'
        elif value_type in ('json', 'string', 'secret'):
            return json.dumps(value)
        else:
            return str(value)
    
    def get_all_settings(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all settings grouped by category.
        
        Returns:
            Dictionary with category keys and setting dictionaries as values.
        """
        self._ensure_cache()
        
        result = {}
        for category, settings in self._cache.items():
            result[category] = {}
            for key, data in settings.items():
                # Mask sensitive values
                if data.get('is_sensitive'):
                    result[category][key] = "***MASKED***" if data['value'] else ""
                else:
                    result[category][key] = data['value']
        
        return result
    
    def get_category_settings(self, category: str) -> Dict[str, Any]:
        """
        Get all settings for a specific category.
        
        Args:
            category: The setting category (auth, embedding, llm, etc.)
            
        Returns:
            Dictionary of settings for the category.
            
        Raises:
            ValueError: If category is invalid.
        """
        if category not in [c.value for c in SettingCategory]:
            raise ValueError(f"Invalid category: {category}")
        
        self._ensure_cache()
        
        result = {}
        category_data = self._cache.get(category, {})
        for key, data in category_data.items():
            if data.get('is_sensitive'):
                result[key] = "***MASKED***" if data['value'] else ""
            else:
                result[key] = data['value']
        
        return result
    
    def get_category_settings_raw(self, category: str) -> Dict[str, Any]:
        """
        Get all settings for a category without masking (for internal use).
        
        Args:
            category: The setting category
            
        Returns:
            Dictionary of raw settings for the category
        """
        if category not in [c.value for c in SettingCategory]:
            raise ValueError(f"Invalid category: {category}")
        
        self._ensure_cache()
        
        result = {}
        category_data = self._cache.get(category, {})
        for key, data in category_data.items():
            result[key] = data['value']
        
        return result
    
    def get_setting(self, category: str, key: str) -> Any:
        """
        Get a single setting value.
        
        Args:
            category: The setting category
            key: The setting key
            
        Returns:
            The setting value, or None if not found.
        """
        self._ensure_cache()
        
        category_data = self._cache.get(category, {})
        setting_data = category_data.get(key)
        
        if setting_data is None:
            return None
        
        return setting_data['value']
    
    def update_category_settings(
        self,
        category: str,
        settings: Dict[str, Any],
        updated_by: str,
        change_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update multiple settings for a category.
        
        Args:
            category: The setting category
            settings: Dictionary of key-value pairs to update
            updated_by: Username making the update
            change_reason: Optional reason for the change
            
        Returns:
            Updated settings dictionary
            
        Raises:
            ValueError: If validation fails
        """
        if category not in [c.value for c in SettingCategory]:
            raise ValueError(f"Invalid category: {category}")
        
        # Get current settings
        current = self.get_category_settings_raw(category)
        
        # Merge with updates
        merged = {**current, **settings}
        
        # Validate using Pydantic model
        validator = SETTINGS_VALIDATORS.get(SettingCategory(category))
        if validator:
            try:
                validated = validator(**merged)
                merged = validated.model_dump()
            except Exception as e:
                raise ValueError(f"Validation failed for {category}: {str(e)}")
        
        # Update database
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            for key, value in settings.items():
                # Get current setting info
                cursor.execute("""
                    SELECT id, value, value_type
                    FROM system_settings
                    WHERE category = ? AND key = ?
                """, (category, key))
                row = cursor.fetchone()
                
                if row:
                    setting_id = row['id']
                    old_value = row['value']
                    value_type = row['value_type']
                    
                    # Serialize new value
                    new_value = self._serialize_value(value, value_type)
                    
                    # Record history
                    cursor.execute("""
                        INSERT INTO settings_history 
                        (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (setting_id, category, key, old_value, new_value, updated_by, change_reason))
                    
                    # Update setting
                    cursor.execute("""
                        UPDATE system_settings
                        SET value = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                        WHERE id = ?
                    """, (new_value, updated_by, setting_id))
                    
                    logger.info(f"Setting updated: {category}.{key} by {updated_by}")
                else:
                    logger.warning(f"Setting not found: {category}.{key}")
            
            conn.commit()
            self._invalidate_cache()
            
            return self.get_category_settings(category)
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update settings: {e}")
            raise
        finally:
            conn.close()
    
    def update_setting(
        self,
        category: str,
        key: str,
        value: Any,
        updated_by: str,
        change_reason: Optional[str] = None
    ) -> Any:
        """
        Update a single setting.
        
        Args:
            category: The setting category
            key: The setting key
            value: The new value
            updated_by: Username making the update
            change_reason: Optional reason for the change
            
        Returns:
            The updated value
        """
        result = self.update_category_settings(
            category, 
            {key: value}, 
            updated_by, 
            change_reason
        )
        return result.get(key)
    
    def get_settings_history(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get settings change history.
        
        Args:
            category: Optional filter by category
            limit: Maximum number of records to return
            
        Returns:
            List of history records
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            if category:
                cursor.execute("""
                    SELECT id, setting_id, category, key, previous_value, new_value, 
                           changed_by, change_reason, changed_at
                    FROM settings_history
                    WHERE category = ?
                    ORDER BY changed_at DESC
                    LIMIT ?
                """, (category, limit))
            else:
                cursor.execute("""
                    SELECT id, setting_id, category, key, previous_value, new_value,
                           changed_by, change_reason, changed_at
                    FROM settings_history
                    ORDER BY changed_at DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        finally:
            conn.close()
    
    def rollback_setting(
        self,
        history_id: int,
        rolled_back_by: str
    ) -> Dict[str, Any]:
        """
        Rollback a setting to a previous value from history.
        
        Args:
            history_id: ID of the history record to rollback to
            rolled_back_by: Username performing the rollback
            
        Returns:
            The restored setting details
            
        Raises:
            ValueError: If history record not found
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # Get history record
            cursor.execute("""
                SELECT setting_id, category, key, previous_value
                FROM settings_history
                WHERE id = ?
            """, (history_id,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"History record not found: {history_id}")
            
            setting_id = row['setting_id']
            category = row['category']
            key = row['key']
            previous_value = row['previous_value']
            
            # Get current value for history
            cursor.execute("""
                SELECT value FROM system_settings WHERE id = ?
            """, (setting_id,))
            current_row = cursor.fetchone()
            current_value = current_row['value'] if current_row else None
            
            # Record the rollback in history
            cursor.execute("""
                INSERT INTO settings_history 
                (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (setting_id, category, key, current_value, previous_value, 
                  rolled_back_by, f"Rollback from history #{history_id}"))
            
            # Update the setting
            cursor.execute("""
                UPDATE system_settings
                SET value = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                WHERE id = ?
            """, (previous_value, rolled_back_by, setting_id))
            
            conn.commit()
            self._invalidate_cache()
            
            logger.info(f"Setting {category}.{key} rolled back by {rolled_back_by}")
            
            return {
                "category": category,
                "key": key,
                "restored_value": previous_value,
                "rolled_back_by": rolled_back_by
            }
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Rollback failed: {e}")
            raise
        finally:
            conn.close()
    
    def export_settings(self, format: str = "json") -> str:
        """
        Export all settings to JSON or YAML format.
        
        Args:
            format: Export format ('json' or 'yaml')
            
        Returns:
            String representation of settings
        """
        settings = self.get_all_settings()
        
        if format == "yaml":
            try:
                import yaml
                return yaml.dump(settings, default_flow_style=False, sort_keys=False)
            except ImportError:
                logger.warning("PyYAML not installed, falling back to JSON")
                format = "json"
        
        return json.dumps(settings, indent=2)
    
    def import_settings(
        self,
        data: str,
        format: str = "json",
        imported_by: str = "system"
    ) -> Dict[str, int]:
        """
        Import settings from JSON or YAML format.
        
        Args:
            data: String containing settings data
            format: Import format ('json' or 'yaml')
            imported_by: Username performing the import
            
        Returns:
            Dictionary with counts of updated settings per category
        """
        if format == "yaml":
            try:
                import yaml
                settings = yaml.safe_load(data)
            except ImportError:
                raise ValueError("PyYAML not installed")
        else:
            settings = json.loads(data)
        
        results = {}
        for category, category_settings in settings.items():
            if category in [c.value for c in SettingCategory]:
                self.update_category_settings(
                    category, 
                    category_settings, 
                    imported_by,
                    f"Bulk import ({format})"
                )
                results[category] = len(category_settings)
        
        return results


# ============================================================================
# Singleton Pattern
# ============================================================================

_settings_service: Optional[SettingsService] = None


def get_settings_service() -> SettingsService:
    """Get the singleton SettingsService instance."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service
