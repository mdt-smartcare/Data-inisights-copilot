"""
SQLAlchemy ORM model for AI Models - Simplified Single-Table Design.

Key features:
- Single table for all models (cloud and local)
- API key per model (not per provider)
- Clear cloud vs local distinction
- HuggingFace integration for downloads
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.connection import Base


class AIModel(Base):
    """
    AI Model configuration - single table for cloud and local models.
    
    Examples:
    - Cloud: openai/gpt-4o, anthropic/claude-3-opus
    - Local: huggingface/BAAI/bge-base-en-v1.5, ollama/llama3
    
    model_id format: "{provider}/{model-name}"
    """
    __tablename__ = "ai_models"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Model identification
    model_id: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'llm', 'embedding', 'reranker'
    
    # Provider info
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    deployment_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'cloud' or 'local'
    
    # Cloud configuration
    api_base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key_env_var: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Local configuration
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    download_status: Mapped[str] = mapped_column(String(50), default='not_downloaded', nullable=False)
    download_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    download_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Model specifications
    context_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # RAG compatibility
    recommended_chunk_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compatibility_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # HuggingFace metadata
    hf_model_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hf_revision: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "model_type IN ('llm', 'embedding', 'reranker')",
            name="ck_ai_models_model_type"
        ),
        CheckConstraint(
            "deployment_type IN ('cloud', 'local')",
            name="ck_ai_models_deployment_type"
        ),
        CheckConstraint(
            "download_status IN ('not_downloaded', 'pending', 'downloading', 'ready', 'error')",
            name="ck_ai_models_download_status"
        ),
    )
    
    @property
    def is_ready(self) -> bool:
        """Check if model is ready to use."""
        if self.deployment_type == 'cloud':
            return True
        return self.download_status == 'ready'
    
    @property
    def has_api_key(self) -> bool:
        """Check if model has API key configured."""
        return bool(self.api_key_encrypted or self.api_key_env_var)
    
    def __repr__(self) -> str:
        return f"<AIModel(id={self.id}, model_id='{self.model_id}', type='{self.model_type}')>"
