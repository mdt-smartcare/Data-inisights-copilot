"""
Configuration management using Pydantic Settings.

This module handles INFRASTRUCTURE/ENVIRONMENT settings only:
- Secrets (API keys)
- Internal database configuration (PostgreSQL for app config)
- OIDC/Auth provider configuration
- Server binding (host, port, CORS)

RUNTIME-CONFIGURABLE settings (LLM, embedding, RAG, rate limiting, etc.)
are managed via the database (agents module) and stored in agent configs.

CLINICAL DATABASE CONNECTIONS are managed via the `db_connections` table
and selected per-agent. Not hardcoded here.
"""
from typing import Optional, List
from pathlib import Path
from functools import lru_cache
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
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ============================================
    # API Keys & Secrets (from environment only)
    # ============================================
    openai_api_key: str = Field(..., description="OpenAI API key")
    
    # ============================================
    # Internal App Database (PostgreSQL - for config storage)
    # ============================================
    # This is the internal database for storing users, settings, prompts, etc.
    # NOT the clinical data database (that comes from db_connections table)
    postgres_host: str = Field(
        default="localhost",
        description="PostgreSQL host for internal app database"
    )
    postgres_port: int = Field(
        default=5432,
        description="PostgreSQL port"
    )
    postgres_db: str = Field(
        default="copilot",
        description="PostgreSQL database name"
    )
    postgres_user: str = Field(
        default="copilot_user",
        description="PostgreSQL username"
    )
    postgres_password: str = Field(
        default="copilot_password",
        description="PostgreSQL password"
    )
    
    # Connection pool settings
    postgres_pool_size: int = Field(
        default=10,
        description="SQLAlchemy connection pool size"
    )
    postgres_max_overflow: int = Field(
        default=20,
        description="SQLAlchemy max overflow connections"
    )
    postgres_pool_timeout: int = Field(
        default=30,
        description="Connection pool timeout in seconds"
    )
    postgres_pool_recycle: int = Field(
        default=3600,
        description="Connection recycle time in seconds"
    )
    postgres_echo: bool = Field(
        default=False,
        description="Echo SQL queries to logs (useful for debugging)"
    )
    
    @property
    def postgres_uri(self) -> str:
        """Construct PostgreSQL connection URI (sync driver)."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    @property
    def postgres_async_uri(self) -> str:
        """Construct async PostgreSQL connection URI (asyncpg driver)."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
    
    # ============================================
    # Security Configuration (secrets/infrastructure)
    # ============================================
    secret_key: str = Field(
        default="development-secret-key-change-in-production",
        description="JWT signing key"
    )
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=720, gt=0, description="Access token expiry in minutes")
    refresh_token_expire_days: int = Field(default=7, gt=0, description="Refresh token expiry in days")
    
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
    
    @property
    def oidc_enabled(self) -> bool:
        """Check if OIDC authentication is enabled."""
        return bool(self.oidc_issuer_url)
    
    # ============================================
    # Server Configuration (infrastructure)
    # ============================================
    host: str = Field(default="0.0.0.0", description="Server bind host")
    port: int = Field(default=8000, description="Server bind port")
    api_v1_prefix: str = Field(default="/api/v1", description="API version 1 prefix")
    project_name: str = Field(default="Data Insights Copilot API", description="Project name")
    version: str = Field(default="1.0.0", description="API version")
    debug: bool = Field(default=False, description="Debug mode")
    
    # ============================================
    # CORS Configuration (startup config)
    # ============================================
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins"
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS requests")
    cors_allow_methods: str = Field(
        default="GET,POST,PUT,PATCH,DELETE,OPTIONS",
        description="Comma-separated list of allowed HTTP methods"
    )
    cors_allow_headers: str = Field(default="*", description="Allowed CORS headers")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
    
    @property
    def cors_methods_list(self) -> List[str]:
        """Parse CORS methods from comma-separated string."""
        return [method.strip() for method in self.cors_allow_methods.split(",") if method.strip()]
    
    # ============================================
    # Observability Configuration
    # ============================================
    langfuse_public_key: Optional[str] = Field(
        default=None,
        description="Langfuse public key for LLM observability"
    )
    langfuse_secret_key: Optional[str] = Field(
        default=None,
        description="Langfuse secret key"
    )
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        description="Langfuse host URL"
    )
    
    @property
    def langfuse_enabled(self) -> bool:
        """Check if Langfuse observability is enabled."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)
    
    # ============================================
    # File Storage Configuration
    # ============================================
    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "data",
        description="Base directory for data storage"
    )
    indexes_path: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "data" / "indexes",
        description="Vector store indexes directory"
    )
    duckdb_path: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "data" / "duckdb_files",
        description="DuckDB files directory for uploaded file SQL queries"
    )
    
    # ============================================
    # Query Relevance Configuration
    # ============================================
    enable_query_relevance_check: bool = Field(
        default=True,
        description="Enable pre-filtering of queries for relevance before SQL generation"

    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.indexes_path.mkdir(parents=True, exist_ok=True)
        self.duckdb_path.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses LRU cache to ensure settings are loaded only once.
    Clear cache to reload: get_settings.cache_clear()
    
    Returns:
        Settings instance
    """
    return Settings()
