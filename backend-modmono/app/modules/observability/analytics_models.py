"""
SQLAlchemy ORM models for query analytics.

Tracks query execution metrics for analyzing NL2SQL accuracy and identifying
areas needing improvement.

PRIVACY NOTE: This module NEVER stores actual query content, SQL, or result data.
Only metadata (categories, timing, success/failure) is logged.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, Boolean, Float, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database.connection import Base


class QueryAnalyticsModel(Base):
    """
    Query analytics database model.
    
    Records privacy-safe metrics about query execution for analytics.
    
    IMPORTANT: This table does NOT store:
    - Actual query text
    - Generated SQL
    - Query results or data
    - Any PII
    
    Only stores:
    - Query hash (for deduplication only, not identification)
    - Category classification
    - Success/failure status
    - Timing metrics
    - Row counts
    """
    __tablename__ = "query_analytics"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Query identification (hash only, not content)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    
    # Classification
    query_category: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    query_complexity: Mapped[str] = mapped_column(String(20), nullable=True)  # simple, medium, complex
    
    # Execution status
    sql_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sql_executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Error tracking (type only, not message content)
    error_type: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    error_category: Mapped[str] = mapped_column(String(50), nullable=True)  # syntax, semantic, timeout, etc.
    
    # Performance metrics
    generation_time_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    total_time_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # Result metadata (not actual data)
    result_row_count: Mapped[int] = mapped_column(Integer, nullable=True)
    result_column_count: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # Context (optional, non-PII)
    data_source_type: Mapped[str] = mapped_column(String(50), nullable=True)  # database, csv, etc.
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow, 
        index=True
    )
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_query_analytics_category_created', 'query_category', 'created_at'),
        Index('ix_query_analytics_error_created', 'error_type', 'created_at'),
        Index('ix_query_analytics_success_created', 'execution_success', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return (
            f"<QueryAnalytics(id={self.id}, category={self.query_category}, "
            f"success={self.execution_success}, time_ms={self.total_time_ms})>"
        )
