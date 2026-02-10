"""
Configuration management using Pydantic Settings.
Loads and validates environment variables with type safety.
"""
from typing import Optional, List
from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""
    
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent / ".env"),  # Look for .env in backend/ directory
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ============================================
    # OpenAI Configuration
    # ============================================
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model name")
    openai_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    
    # ============================================
    # Database Configuration
    # ============================================
    db_user: str = Field(default="admin")
    db_password: str = Field(default="admin")
    db_name: str = Field(default="Spice_BD")
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    
    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    # ============================================
    # Embedding Model Configuration
    # ============================================
    embedding_model_path: str = Field(default="./models/bge-m3")
    embedding_model_name: str = Field(default="BAAI/bge-m3")
    vector_db_path: str = Field(default="./data/indexes/chroma_db_advanced")
    
    # ============================================
    # Security Configuration
    # ============================================
    secret_key: str = Field(..., min_length=32, description="JWT signing key")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=720, gt=0)  # 12 hours
    refresh_token_expire_days: int = Field(default=7, gt=0)
    
    # ============================================
    # API Configuration
    # ============================================
    api_v1_prefix: str = Field(default="/api/v1")
    project_name: str = Field(default="Data Insights Copilot API")
    version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    
    # ============================================
    # CORS Configuration
    # ============================================
    cors_origins: str = Field(default="http://localhost:3000,http://localhost:5173")
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: str = Field(default="GET,POST,PUT,DELETE,OPTIONS")
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
    # Langfuse Tracing (Optional)
    # ============================================
    langfuse_public_key: Optional[str] = Field(default=None)
    langfuse_secret_key: Optional[str] = Field(default=None)
    langfuse_host: str = Field(default="http://localhost:3001")
    enable_langfuse: bool = Field(default=False)
    
    # ============================================
    # Feature Flags
    # ============================================
    enable_followup_questions: bool = Field(
        default=True,
        description="Generate LLM-powered follow-up question suggestions"
    )
    
    # ============================================
    # Logging Configuration
    # ============================================
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")
    log_file: str = Field(default="./logs/backend.log")
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of {valid_levels}")
        return v.upper()
    
    # ============================================
    # RAG Configuration
    # ============================================
    rag_top_k: int = Field(default=5, gt=0)
    rag_similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    rag_rerank: bool = Field(default=True)
    rag_config_path: str = Field(default="./config/embedding_config.yaml")
    
    # ============================================
    # Rate Limiting (Optional)
    # ============================================
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=60, gt=0)
    
    # ============================================
    # Testing Configuration
    # ============================================
    test_database_url: Optional[str] = Field(default=None)
    pytest_timeout: int = Field(default=30)


def get_settings() -> Settings:
    """
    Get settings instance.
    Use this function throughout the application to access settings.
    
    Note: Cache removed to allow .env changes to take effect on server reload.
    """
    return Settings()


# Default hardcoded users (will be migrated to database)
DEFAULT_USERS = {
    "admin": "admin",
    "analyst": "analyst2024",
    "viewer": "view123"
}
