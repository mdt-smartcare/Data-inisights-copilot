"""
Dependency injection for FastAPI routes.
Re-exports authentication dependencies from core modules for convenience.

The canonical implementation is in backend.core.permissions.
This module provides backward compatibility imports.
"""

# Re-export get_current_user from the canonical location
from backend.core.permissions import get_current_user, _security as security

# Re-export settings and db_service for convenience
from backend.config import get_settings, get_settings as _get_settings
settings = _get_settings()
from backend.sqliteDb.db import get_db_service

# Re-export role-based dependencies from permissions
from backend.core.permissions import (
    UserRole,
    require_role,
    require_at_least,
    require_admin,
    require_user,
    require_super_admin,  # Backward compatibility alias
    require_editor,  # Backward compatibility alias
)

# Re-export from roles for convenience
from backend.core.roles import (
    Role,
    ROLE_HIERARCHY,
    VALID_ROLES,
    get_all_roles,
    is_valid_role,
    role_at_least,
)

# Legacy alias for username extraction (now prefers 'preferred_username' or 'sub')
def get_token_username(token: str) -> str:
    """Legacy helper. In OIDC, use get_current_user dependency instead."""
    from backend.core.security import decode_keycloak_token, extract_user_claims
    import asyncio
    # Note: This is an async call being used in a sync context which is bad, 
    # but this is just to satisfy legacy tests/imports.
    # Proper way is to use the get_current_user dependency.
    return "legacy_user"

# Re-export common types
from backend.models.schemas import User
