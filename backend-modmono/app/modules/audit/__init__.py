"""Audit logging module.

Module structure:
- models.py: SQLAlchemy ORM model for audit_logs
- repository.py: Data access layer
- service.py: Business logic
- schemas.py: Pydantic request/response models
- routes.py: API endpoints (/audit/logs, /audit/logs/count, /audit/actions)
- helpers.py: Utility functions (log_audit, AuditLogger, get_audit_logger)
"""
from app.modules.audit.schemas import AuditAction, AuditLogCreate, AuditLogResponse
from app.modules.audit.service import AuditService
from app.modules.audit.routes import router
from app.modules.audit.helpers import (
    log_audit, 

    AuditLogger,
    get_audit_logger,
)

__all__ = [
    "AuditAction",
    "AuditLogCreate",
    "AuditLogResponse",
    "AuditService",
    "router",
    "log_audit",
    "AuditLogger",
    "get_audit_logger",
]