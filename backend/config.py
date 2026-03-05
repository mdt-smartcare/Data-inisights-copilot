"""
Configuration management using Pydantic Settings.

This module handles INFRASTRUCTURE/ENVIRONMENT settings only:
- Secrets (API keys)
- Internal database path (SQLite for app config)
- OIDC/Auth provider configuration
- Server binding (host, port, CORS)

RUNTIME-CONFIGURABLE settings (LLM, embedding, RAG, rate limiting, etc.)
are managed via the SettingsService and stored in the database.

CLINICAL DATABASE CONNECTIONS are managed via the `db_connections` table
and selected per-agent via the frontend. Not hardcoded here.
"""
from typing import Optional, List
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Infrastructure and environment settings.
    
    These are settings that:
    - Come from environment variables or .env files
    - Cannot be changed at runtime without restart
    - Are required for the server to start
    
    NOTE: Clinical database connections are NOT configured here.
    They are managed via the `db_connections` table and assigned to agents.
    """
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ============================================
    # API Keys & Secrets (from environment only)
    # ============================================
    openai_api_key: str = Field(..., description="OpenAI API key")
    
    # ============================================
    # Internal App Database (SQLite - for config storage)
    # ============================================
    # This is the internal database for storing users, settings, prompts, etc.
    # NOT the clinical data database (that comes from db_connections table)
    sqlite_db_path: str = Field(
        default="./sqliteDb/copilot.db",
        description="Path to internal SQLite database for app configuration"
    )
    
    # ============================================
    # Security Configuration (secrets/infrastructure)
    # ============================================
    secret_key: str = Field(
        default="development-secret-key-change-in-production",
        description="JWT signing key"
    )
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=720, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)
    
    # ============================================
    # OIDC/Keycloak Configuration (infrastructure)
    # ============================================
    oidc_issuer_url: str = Field(
        default="",
        description="Keycloak realm issuer URL (leave empty to disable OIDC)"
    )
    oidc_client_id: str = Field(
        default="data-insights-copilot",
        description="OIDC client ID"
    )
    oidc_audience: Optional[str] = Field(
        default=None,
        description="Expected JWT audience claim (defaults to client_id if not set)"
    )
    oidc_jwks_cache_ttl: int = Field(
        default=3600,
        description="JWKS cache TTL in seconds"
    )
    oidc_default_role: str = Field(
        default="user",
        description="Default role for newly provisioned OIDC users"
    )
    oidc_role_claim: str = Field(
        default="realm_access.roles",
        description="Claim path for roles in OIDC token"
    )
    
    # ============================================
    # Server Configuration (infrastructure)
    # ============================================
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    api_v1_prefix: str = Field(default="/api/v1")
    project_name: str = Field(default="Data Insights Copilot API")
    version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    
    # ============================================
    # CORS Configuration (startup config)
    # ============================================
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173")
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: str = Field(default="GET,POST,PUT,PATCH,DELETE,OPTIONS")
    cors_allow_headers: str = Field(default="*")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def cors_methods_list(self) -> List[str]:
        """Parse CORS methods from comma-separated string."""
        return [method.strip() for method in self.cors_allow_methods.split(",")]
    
    # ============================================
    # Langfuse Configuration (secrets/infrastructure)
    # ============================================
    langfuse_public_key: Optional[str] = Field(default=None)
    langfuse_secret_key: Optional[str] = Field(default=None)
    langfuse_host: str = Field(default="https://cloud.langfuse.com")
    enable_langfuse: bool = Field(default=False)
    
    # ============================================
    # Logging Configuration (infrastructure - needed at startup)
    # ============================================
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    log_format: str = Field(default="json", description="Log format (json or text)")
    
    # ============================================
    # Feature Flags
    # ============================================
    enable_followup_questions: bool = Field(
        default=True,
        description="Generate LLM-powered follow-up question suggestions"
    )
    
    # ============================================
    # File Paths (infrastructure - needed at startup)
    # ============================================
    log_file: str = Field(default="./logs/backend.log")
    embedding_log_file: str = Field(default="./logs/embedding.log")
    models_path: str = Field(default="./models", description="Path to local ML models")
    data_path: str = Field(default="./data", description="Path to data directory")
    rag_config_path: str = Field(default="./config/embedding_config.yaml", description="Path to RAG config YAML (fallback defaults)")
    
    # ============================================
    # Testing Configuration
    # ============================================
    test_database_url: Optional[str] = Field(default=None)
    pytest_timeout: int = Field(default=30)


def get_settings() -> Settings:
    """
    Get infrastructure settings instance.
    
    For runtime-configurable settings (LLM, embedding, RAG, etc.),
    use get_runtime_setting() or SettingsService directly.
    
    For clinical database connections, use the db_connections table
    via the DatabaseService.
    """
    return Settings()


# =============================================================================
# Runtime Settings Helper (reads from database)
# =============================================================================

def get_runtime_setting(category: str, key: str, default=None):
    """
    Get a runtime-configurable setting from the database.
    
    This is a convenience helper for accessing settings that can be
    changed via the frontend without server restart.
    
    Categories:
    - 'llm': provider, model_name, temperature, max_tokens
    - 'embedding': provider, model_name, batch_size, dimensions
    - 'rag': top_k_initial, top_k_final, hybrid_weights, rerank_enabled, chunk_size
    - 'security': rate_limit_enabled, rate_limit_per_minute
    - 'observability': log_level, enable_tracing
    - 'ui': app_name, theme, primary_color
    - 'data_privacy': global_exclude_columns, exclude_tables, table_specific_exclusions
    - 'medical_context': terminology_mappings, clinical_flag_prefixes
    - 'chunking': parent_chunk_size, child_chunk_size, etc.
    - 'vector_store': type, default_collection
    
    Args:
        category: Setting category (llm, embedding, rag, etc.)
        key: Setting key within the category
        default: Default value if setting not found
        
    Returns:
        The setting value, or default if not found
        
    Example:
        model = get_runtime_setting('llm', 'model_name', 'gpt-4o')
        temperature = get_runtime_setting('llm', 'temperature', 0.0)
    """
    try:
        from backend.services.settings_service import get_settings_service
        settings_service = get_settings_service()
        value = settings_service.get_setting(category, key)
        return value if value is not None else default
    except Exception:
        # Fallback to default if settings service unavailable
        return default


def get_llm_settings() -> dict:
    """
    Get all LLM settings as a dictionary.
    
    Returns:
        Dict with keys: provider, model_name, temperature, max_tokens, api_key
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('llm')
    except Exception:
        # Fallback defaults
        return {
            'provider': 'openai',
            'model_name': 'gpt-4o',
            'temperature': 0.0,
            'max_tokens': 4096,
            'api_key': ''
        }


def get_embedding_settings() -> dict:
    """
    Get all embedding settings as a dictionary.
    
    Returns:
        Dict with keys: provider, model_name, model_path, batch_size, dimensions
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('embedding')
    except Exception:
        # Fallback defaults
        return {
            'provider': 'bge-m3',
            'model_name': 'BAAI/bge-m3',
            'model_path': './models/bge-m3',
            'batch_size': 128,
            'dimensions': 1024
        }


def get_rag_settings() -> dict:
    """
    Get all RAG pipeline settings as a dictionary.
    
    Returns:
        Dict with keys: top_k_initial, top_k_final, hybrid_weights, 
                       rerank_enabled, reranker_model, chunk_size, chunk_overlap
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('rag')
    except Exception:
        # Fallback defaults
        return {
            'top_k_initial': 50,
            'top_k_final': 10,
            'hybrid_weights': [0.75, 0.25],
            'rerank_enabled': True,
            'reranker_model': 'BAAI/bge-reranker-base',
            'chunk_size': 800,
            'chunk_overlap': 150
        }


def get_data_privacy_settings() -> dict:
    """
    Get data privacy settings (PII protection rules).
    
    Returns:
        Dict with keys: global_exclude_columns, exclude_tables, table_specific_exclusions
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('data_privacy')
    except Exception:
        # Fallback defaults
        return {
            'global_exclude_columns': ['first_name', 'last_name', 'phone_number', 'date_of_birth', 'password', 'national_id'],
            'exclude_tables': ['audit', 'user_token', 'flyway_schema_history'],
            'table_specific_exclusions': {}
        }


def get_medical_context_settings() -> dict:
    """
    Get medical context settings (terminology mappings).
    
    Returns:
        Dict with keys: terminology_mappings, clinical_flag_prefixes
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('medical_context')
    except Exception:
        # Fallback defaults
        return {
            'terminology_mappings': {},
            'clinical_flag_prefixes': ['is_', 'has_', 'was_', 'history_of_', 'flag_', 'confirmed_', 'requires_', 'on_']
        }


def get_chunking_settings() -> dict:
    """
    Get chunking strategy settings.
    
    Returns:
        Dict with keys: parent_chunk_size, parent_chunk_overlap, 
                       child_chunk_size, child_chunk_overlap, min_chunk_length
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('chunking')
    except Exception:
        # Fallback defaults
        return {
            'parent_chunk_size': 800,
            'parent_chunk_overlap': 150,
            'child_chunk_size': 200,
            'child_chunk_overlap': 50,
            'min_chunk_length': 50
        }


def get_vector_store_settings() -> dict:
    """
    Get vector store settings.
    
    Returns:
        Dict with keys: type, default_collection
    """
    try:
        from backend.services.settings_service import get_settings_service
        return get_settings_service().get_category_settings_raw('vector_store')
    except Exception:
        # Fallback defaults
        return {
            'type': 'chroma',
            'default_collection': 'default_collection'
        }


# =============================================================================
# Legacy Support
# =============================================================================

# Default hardcoded users (legacy - kept for backward compatibility)
# With OIDC/Keycloak integration, users are now provisioned automatically
DEFAULT_USERS = {
    "admin": "admin",
    "user": "user123"
}
