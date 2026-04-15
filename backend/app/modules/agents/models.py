"""
SQLAlchemy ORM models for agents and configurations.

Schema:
- agents: Core agent entity (id, title, description)
- agent_configs: Links agent ↔ data source with all configs
- user_agents: RBAC for agent access

Note: DataSourceModel is in app.modules.data_sources.models
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime, ForeignKey, Index,
    Integer, String, Text, text
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.database.connection import Base


class AgentModel(Base):
    """
    Simplified agent model.
    
    Agents are lightweight entities - all configuration lives in agent_configs.
    """
    __tablename__ = "agents"
    
    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True), 
        primary_key=True, 
        server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )
    
    # Relationships
    creator = relationship("UserModel", foreign_keys=[created_by], backref="created_agents")
    configs = relationship("AgentConfigModel", back_populates="agent", cascade="all, delete-orphan")
    user_agents = relationship("UserAgentModel", back_populates="agent", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, title={self.title})>"


class AgentConfigModel(Base):
    """
    Agent configuration linking agent ↔ data source with all settings.
    
    Stores:
    - Schema/column selection for embedding
    - LLM, embedding, chunking, RAG configs (as JSON)
    - System prompt and examples
    - Vector store paths and status
    - Version tracking (multiple versions per agent)
    """
    __tablename__ = "agent_configs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("agents.id", ondelete="CASCADE"), 
        nullable=False
    )
    data_source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("data_sources.id"), 
        nullable=False
    )
    
    # Schema/Data config
    selected_columns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    data_dictionary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON
    
    # Model configs (JSON strings)
    llm_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunking_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rag_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # AI Registry model IDs (foreign keys to ai_models.id)
    llm_model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    embedding_model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    reranker_model_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    
    # Prompt
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example_questions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    
    # Vector store
    embedding_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vector_collection_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embedding_status: Mapped[str] = mapped_column(String, default="not_started", nullable=False)
    
    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0 or 1
    status: Mapped[str] = mapped_column(String, default="draft", nullable=False)  # draft, published
    completed_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-6: highest completed wizard step
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )
    
    # Relationships
    agent = relationship("AgentModel", back_populates="configs")
    data_source = relationship("app.modules.data_sources.models.DataSourceModel", back_populates="agent_configs")
    
    # Indexes
    __table_args__ = (
        Index(
            "idx_agent_configs_active", 
            "agent_id", 
            "is_active", 
            postgresql_where=text("is_active = 1")
        ),
    )
    
    def __repr__(self) -> str:
        return f"<AgentConfig(id={self.id}, agent_id={self.agent_id}, v{self.version}, active={bool(self.is_active)})>"


class UserAgentModel(Base):
    """
    User-Agent access control (RBAC).
    
    Defines which users have access to which agents and with what role.
    Roles: user, editor, admin
    """
    __tablename__ = "user_agents"
    
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("users.id"), 
        primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("agents.id", ondelete="CASCADE"), 
        primary_key=True
    )
    role: Mapped[str] = mapped_column(String, default="user", nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    granted_by: Mapped[Optional[str]] = mapped_column(
        PGUUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=True
    )
    
    # Relationships
    user = relationship("UserModel", foreign_keys=[user_id])
    agent = relationship("AgentModel", back_populates="user_agents")
    granter = relationship("UserModel", foreign_keys=[granted_by])
    
    def __repr__(self) -> str:
        return f"<UserAgent(user_id={self.user_id}, agent_id={self.agent_id}, role={self.role})>"
