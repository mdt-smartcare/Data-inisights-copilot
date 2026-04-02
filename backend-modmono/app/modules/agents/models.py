"""
SQLAlchemy ORM models for agents and their configurations.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, 
    String, Text, text
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from app.core.database.session import Base


class AgentModel(Base):
    """
    ORM model for agents table.
    
    Agents are the core entities that encapsulate RAG configurations,
    embedding models, LLM settings, and data source connections.
    """
    __tablename__ = "agents"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    type = Column(String, default="sql", nullable=False)  # sql, rag, hybrid
    db_connection_uri = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    embedding_model = Column(String, default="bge-m3", nullable=True)
    embedding_dimension = Column(Integer, default=1024, nullable=True)
    embedding_provider = Column(String, default="sentence-transformers", nullable=True)
    created_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    creator = relationship("UserModel", foreign_keys=[created_by], backref="created_agents")
    user_agents = relationship("UserAgentModel", back_populates="agent", cascade="all, delete-orphan")
    system_prompts = relationship("SystemPromptModel", back_populates="agent", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<AgentModel(id={self.id}, name={self.name}, type={self.type})>"


class UserAgentModel(Base):
    """
    ORM model for user_agents table (RBAC mapping).
    
    Defines which users have access to which agents and with what role.
    Roles: user, admin (agent-specific permissions).
    """
    __tablename__ = "user_agents"
    
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    agent_id = Column(PGUUID(as_uuid=True), ForeignKey("agents.id"), primary_key=True)
    role = Column(String, default="user", nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    granted_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Relationships
    user = relationship("UserModel", foreign_keys=[user_id])
    agent = relationship("AgentModel", back_populates="user_agents")
    granter = relationship("UserModel", foreign_keys=[granted_by])
    
    def __repr__(self) -> str:
        return f"<UserAgentModel(user_id={self.user_id}, agent_id={self.agent_id}, role={self.role})>"


class SystemPromptModel(Base):
    """
    ORM model for system_prompts table.
    
    Stores versioned system prompts for agents with activation tracking.
    """
    __tablename__ = "system_prompts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt_text = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    is_active = Column(Integer, default=0, nullable=False)  # 0 = inactive, 1 = active
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String, nullable=True)
    agent_id = Column(PGUUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True)
    
    # Relationships
    agent = relationship("AgentModel", back_populates="system_prompts")
    prompt_config = relationship("PromptConfigModel", back_populates="system_prompt", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<SystemPromptModel(id={self.id}, agent_id={self.agent_id}, version={self.version}, active={bool(self.is_active)})>"


class PromptConfigModel(Base):
    """
    ORM model for prompt_configs table.
    
    Stores all agent configurations as JSON text fields:
    - chunking_config: Parent/child chunk sizes, overlap, separators
    - llm_config: Model, temperature, max_tokens, streaming
    - embedding_config: Provider, model, dimensions, batch_size
    - retriever_config: top_k, similarity_threshold, reranking
    - Other configs: schema_selection, data_dictionary, reasoning, examples
    """
    __tablename__ = "prompt_configs"
    
    prompt_id = Column(Integer, ForeignKey("system_prompts.id"), primary_key=True)
    connection_id = Column(Integer, nullable=True)
    schema_selection = Column(Text, nullable=True)
    data_dictionary = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    example_questions = Column(Text, nullable=True)
    data_source_type = Column(String, default="database", nullable=False)
    ingestion_documents = Column(Text, nullable=True)
    ingestion_file_name = Column(Text, nullable=True)
    ingestion_file_type = Column(Text, nullable=True)
    embedding_config = Column(Text, nullable=True)  # JSON string
    retriever_config = Column(Text, nullable=True)  # JSON string
    chunking_config = Column(Text, nullable=True)   # JSON string
    llm_config = Column(Text, nullable=True)        # JSON string
    
    # Relationships
    system_prompt = relationship("SystemPromptModel", back_populates="prompt_config")
    
    def __repr__(self) -> str:
        return f"<PromptConfigModel(prompt_id={self.prompt_id}, data_source_type={self.data_source_type})>"
