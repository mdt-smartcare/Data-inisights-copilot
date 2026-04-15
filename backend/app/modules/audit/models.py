"""
SQLAlchemy ORM models for observability module.

Defines database tables for audit logs and notifications.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database.connection import Base


class AuditLogModel(Base):
    """
    Audit log database model.
    
    Records all significant actions in the system for compliance and security.
    """
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    actor_id: Mapped[str] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_username: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    actor_role: Mapped[str] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(Text, nullable=True)
    resource_id: Mapped[str] = mapped_column(Text, nullable=True)
    resource_name: Mapped[str] = mapped_column(Text, nullable=True)
    details: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    ip_address: Mapped[str] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, nullable=True)
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, actor={self.actor_username}, timestamp={self.timestamp})>"
