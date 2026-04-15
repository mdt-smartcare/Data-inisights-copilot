"""
SQLAlchemy models for authentication and RBAC.

These models correspond to the database schema defined in 008_auth_rbac_schema.sql.
Uses SQLAlchemy 2.0 style with Mapped types for better type inference.
"""
from datetime import datetime
from typing import List, Optional, Any
from sqlalchemy import (
    Column, Integer, String, Boolean, Text, DateTime, 
    ForeignKey, Table, Index, CheckConstraint, JSON
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB


class AuthBase(DeclarativeBase):
    """Base class for auth models."""
    pass


# Alias for compatibility
Base = AuthBase


# ===========================================
# ASSOCIATION TABLES (defined before models)
# ===========================================

# User-Role junction table for many-to-many relationship
user_roles_table = Table(
    "user_roles",
    AuthBase.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime, default=datetime.utcnow),
    Column("assigned_by", Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
)

# Role-Permission junction table for many-to-many relationship
role_permissions_table = Table(
    "role_permissions",
    AuthBase.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


# ===========================================
# USER MODEL
# ===========================================

class User(AuthBase):
    """
    Application user model.
    
    Users are invite-only and link their OIDC identity on first login.
    Status flow: invited -> active <-> disabled
    """
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True,
        comment="OIDC provider subject (sub) claim"
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="invited",
        comment="invited: awaiting first login; active: can access; disabled: blocked"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    invited_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=user_roles_table,
        primaryjoin=lambda: User.id == user_roles_table.c.user_id,
        secondaryjoin=lambda: Role.id == user_roles_table.c.role_id,
        back_populates="users",
        lazy="selectin"
    )
    inviter: Mapped[Optional["User"]] = relationship(
        "User",
        remote_side=[id],
        foreign_keys=[invited_by]
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
        lazy="dynamic"
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('invited', 'active', 'disabled')",
            name="check_user_status"
        ),
        Index("idx_users_status", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', status='{self.status}')>"
    
    @property
    def is_active(self) -> bool:
        """Check if user is active."""
        return self.status == "active"
    
    @property
    def is_invited(self) -> bool:
        """Check if user is in invited state (awaiting first login)."""
        return self.status == "invited"
    
    @property
    def is_super_admin(self) -> bool:
        """Check if user has super_admin role."""
        return any(role.name == "super_admin" for role in self.roles)


# ===========================================
# ROLE MODEL
# ===========================================

class Role(AuthBase):
    """
    Role model for RBAC.
    
    Roles can be system-defined (is_system=True) or custom-created.
    System roles cannot be deleted.
    """
    __tablename__ = "roles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    
    # Relationships
    users: Mapped[List["User"]] = relationship(
        "User",
        secondary=user_roles_table,
        primaryjoin=lambda: Role.id == user_roles_table.c.role_id,
        secondaryjoin=lambda: User.id == user_roles_table.c.user_id,
        back_populates="roles",
        lazy="selectin"
    )
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions_table,
        back_populates="roles",
        lazy="selectin"
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by]
    )
    
    __table_args__ = (
        Index("idx_roles_is_system", "is_system"),
    )
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}', is_system={self.is_system})>"
    
    @property
    def permission_codes(self) -> List[str]:
        """Get list of permission codes for this role."""
        return [p.code for p in self.permissions]


# ===========================================
# PERMISSION MODEL
# ===========================================

class Permission(AuthBase):
    """
    Permission model for fine-grained access control.
    
    Permissions are predefined and assigned to roles.
    """
    __tablename__ = "permissions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
        comment="Permission code, e.g., 'users:read'"
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permissions_table,
        back_populates="permissions",
        lazy="selectin"
    )
    
    __table_args__ = (
        Index("idx_permissions_category", "category"),
    )
    
    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, code='{self.code}')>"


# ===========================================
# ===========================================
# AUDIT LOG MODEL
# ===========================================

class AuditLog(AuthBase):
    """
    Audit log model for security and compliance.
    
    Logs all significant user actions for forensics and compliance.
    """
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="audit_logs"
    )
    
    __table_args__ = (
        Index("idx_audit_user_action", "user_id", "action"),
        Index("idx_audit_created", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', user_id={self.user_id})>"


# ===========================================
# TOKEN BLACKLIST MODEL
# ===========================================

class TokenBlacklist(AuthBase):
    """
    Token blacklist model for logout before expiry.
    
    Stores blacklisted JWT IDs (jti claims).
    Redis is the primary blacklist storage; this is a backup.
    """
    __tablename__ = "token_blacklist"
    
    jti: Mapped[str] = mapped_column(
        String(255), primary_key=True,
        comment="JWT ID claim - unique identifier for the token"
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(100), default="logout")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
    __table_args__ = (
        Index("idx_token_blacklist_expires", "expires_at"),
        Index("idx_token_blacklist_user", "user_id"),
    )
    
    def __repr__(self) -> str:
        return f"<TokenBlacklist(jti='{self.jti[:8]}...', user_id={self.user_id})>"


# ===========================================
# RATE LIMIT EVENTS MODEL
# ===========================================

class RateLimitEvent(AuthBase):
    """
    Rate limit event tracking (optional - can use Redis instead).
    
    Tracks rate limiting events for monitoring and alerting.
    """
    __tablename__ = "rate_limit_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
    __table_args__ = (
        Index("idx_rate_limit", "ip_address", "endpoint", "timestamp"),
    )
    
    def __repr__(self) -> str:
        return f"<RateLimitEvent(ip='{self.ip_address}', endpoint='{self.endpoint}')>"


# ===========================================
# PREDEFINED PERMISSION CODES
# ===========================================

class PermissionCode:
    """
    Predefined permission codes for type safety.
    
    Usage:
        from models.auth_models import PermissionCode
        if PermissionCode.USERS_READ in user_permissions:
            ...
    """
    # Chat permissions
    CHAT_QUERY = "chat:query"
    CHART_VIEW = "chart:view"
    
    # User management
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    
    # Role management
    ROLES_READ = "roles:read"
    ROLES_CREATE = "roles:create"
    
    # Configuration
    CONFIG_READ = "config:read"
    CONFIG_MANAGE = "config:manage"
    
    # Audit
    AUDIT_READ = "audit:read"
    
    # RAG
    RAG_READ = "rag:read"
    RAG_MANAGE = "rag:manage"
    EMBEDDING_MANAGE = "embedding:manage"
    
    # Connections
    CONNECTIONS_READ = "connections:read"
    CONNECTIONS_MANAGE = "connections:manage"
    
    # Super admin wildcard
    ALL = "*"


# ===========================================
# ROLE NAMES
# ===========================================

class RoleName:
    """
    Predefined role names for type safety.
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"
