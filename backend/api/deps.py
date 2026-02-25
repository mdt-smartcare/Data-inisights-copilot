"""
Dependency injection for FastAPI routes.
Re-exports authentication dependencies from core modules for convenience.

The canonical implementation is in backend.core.permissions.
This module provides backward compatibility imports.
"""

# Re-export get_current_user from the canonical location
from backend.core.permissions import get_current_user

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

# Re-export common types
from backend.models.schemas import User
