"""
User role definitions.
Re-exports from core/permissions for backward compatibility.
"""
from backend.core.permissions import (
    UserRole,
    ROLE_HIERARCHY,
    role_at_least,
    can_manage_users,
    can_view_all_audit_logs,
    can_manage_connections,
    can_edit_config,
    can_publish_prompt,
    can_execute_queries,
    can_view_config,
)

__all__ = [
    'UserRole',
    'ROLE_HIERARCHY',
    'role_at_least',
    'can_manage_users',
    'can_view_all_audit_logs',
    'can_manage_connections',
    'can_edit_config',
    'can_publish_prompt',
    'can_execute_queries',
    'can_view_config',
]
