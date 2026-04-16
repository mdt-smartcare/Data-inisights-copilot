"""
SQLAlchemy ORM model for data sources.

Unified data source model for both database connections and file uploads.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey,
    String, Text, text
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.database.connection import Base


class DataSourceModel(Base):
    """
    Unified data source model for both database connections and file uploads.
    
    source_type = 'database': Uses db_url, db_engine_type
    source_type = 'file': Uses file fields (original_file_path, duckdb_*, columns_json)
    """
    __tablename__ = "data_sources"
    
    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True), 
        primary_key=True, 
        server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)  # 'database' or 'file'
    
    # Database fields (source_type = 'database')
    db_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    db_engine_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # postgresql, mysql, sqlite
    
    # File fields (source_type = 'file')
    original_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # csv, xlsx, pdf, json
    duckdb_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duckdb_table_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    columns_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
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
    creator = relationship("UserModel", foreign_keys=[created_by])
    agent_configs = relationship("AgentConfigModel", back_populates="data_source")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('database', 'file')", 
            name="ck_data_sources_source_type"
        ),
    )
    
    def __repr__(self) -> str:
        return f"<DataSource(id={self.id}, title={self.title}, type={self.source_type})>"
