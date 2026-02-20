"""
Centralized role configuration for the application.

This module defines all available roles, their hierarchy, and provides
utilities for role-based access control. To add a new role:

1. Add the role to the `Role` enum
2. Add the role to `ROLE_HIERARCHY` list (higher index = less privilege)
3. Optionally add Keycloak role mappings in `KEYCLOAK_ROLE_MAPPINGS`

The rest of the application will automatically pick up the new role.
"""
from enum import Enum
from typing import List, Dict, Set


class Role(str, Enum):
    """
    Application roles with descending privilege levels.
    
    ADMIN > USER
    
    To add a new role:
    1. Add it here
    2. Add it to ROLE_HIERARCHY in the correct position
    3. Optionally add Keycloak mappings in KEYCLOAK_ROLE_MAPPINGS
    """
    ADMIN = "admin"
    USER = "user"


# Backward compatibility alias
UserRole = Role


# Role hierarchy: index 0 = highest privilege
# Lower index = more privileges
ROLE_HIERARCHY: List[str] = [
    Role.ADMIN.value,
    Role.USER.value,
]

# All valid role values as a set (for validation)
VALID_ROLES: Set[str] = {r.value for r in Role}

# Default role for new users
DEFAULT_ROLE: str = Role.USER.value

# Mapping from Keycloak role names to application roles
# Multiple Keycloak roles can map to the same app role
# Checked in order (first match wins)
KEYCLOAK_ROLE_MAPPINGS: List[tuple] = [
    # (list of keycloak role names, app role)
    (["admin", "super_admin", "superadmin", "administrator"], Role.ADMIN.value),
    (["user", "default-roles-data-insights-copilot", "member"], Role.USER.value),
]


def get_all_roles() -> List[str]:
    """Get list of all valid role values."""
    return list(VALID_ROLES)


def is_valid_role(role: str) -> bool:
    """Check if a role value is valid."""
    return role in VALID_ROLES


def role_at_least(user_role: str, required_role: str) -> bool:
    """
    Check if user_role has at least the privilege level of required_role.
    
    Args:
        user_role: The user's current role
        required_role: The minimum required role
        
    Returns:
        True if user_role >= required_role in the hierarchy
    """
    if user_role not in ROLE_HIERARCHY or required_role not in ROLE_HIERARCHY:
        return False
    return ROLE_HIERARCHY.index(user_role) <= ROLE_HIERARCHY.index(required_role)


def map_keycloak_role(keycloak_roles: List[str]) -> str:
    """
    Map Keycloak realm roles to application role.
    
    Keycloak roles are checked in order of privilege (highest first).
    Returns the first matching app role, or DEFAULT_ROLE if no match.
    
    Args:
        keycloak_roles: List of role names from Keycloak token
    
    Returns:
        Application role string
    """
    # Normalize roles to lowercase for comparison
    roles_lower = [r.lower() for r in keycloak_roles]
    
    for keycloak_role_names, app_role in KEYCLOAK_ROLE_MAPPINGS:
        for kc_role in keycloak_role_names:
            if kc_role.lower() in roles_lower:
                return app_role
    
    return DEFAULT_ROLE


# ============================================
# Permission Definitions
# ============================================
# Define which roles can perform which actions
# This makes it easy to adjust permissions without changing code

class Permission(str, Enum):
    """Available permissions in the system."""
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_CONNECTIONS = "manage_connections"
    EDIT_CONFIG = "edit_config"
    PUBLISH_PROMPT = "publish_prompt"
    EXECUTE_QUERIES = "execute_queries"
    VIEW_CONFIG = "view_config"
    MANAGE_AGENTS = "manage_agents"


# Map permissions to minimum required role
# Using role_at_least, so admin gets all user permissions too
PERMISSION_REQUIREMENTS: Dict[Permission, str] = {
    Permission.MANAGE_USERS: Role.ADMIN.value,
    Permission.VIEW_AUDIT_LOGS: Role.ADMIN.value,
    Permission.MANAGE_CONNECTIONS: Role.ADMIN.value,
    Permission.EDIT_CONFIG: Role.ADMIN.value,
    Permission.PUBLISH_PROMPT: Role.ADMIN.value,
    Permission.MANAGE_AGENTS: Role.ADMIN.value,
    Permission.EXECUTE_QUERIES: Role.USER.value,
    Permission.VIEW_CONFIG: Role.USER.value,
}


def has_permission(user_role: str, permission: Permission) -> bool:
    """
    Check if a user role has a specific permission.
    
    Args:
        user_role: The user's role
        permission: The permission to check
        
    Returns:
        True if the user has the permission
    """
    required_role = PERMISSION_REQUIREMENTS.get(permission)
    if not required_role:
        return False
    return role_at_least(user_role, required_role)


# Convenience functions for common permission checks
def can_manage_users(role: str) -> bool:
    """Check if role can manage users."""
    return has_permission(role, Permission.MANAGE_USERS)


def can_view_all_audit_logs(role: str) -> bool:
    """Check if role can view all audit logs."""
    return has_permission(role, Permission.VIEW_AUDIT_LOGS)


def can_manage_connections(role: str) -> bool:
    """Check if role can manage database connections."""
    return has_permission(role, Permission.MANAGE_CONNECTIONS)


def can_edit_config(role: str) -> bool:
    """Check if role can edit configuration."""
    return has_permission(role, Permission.EDIT_CONFIG)


def can_publish_prompt(role: str) -> bool:
    """Check if role can publish prompts."""
    return has_permission(role, Permission.PUBLISH_PROMPT)


def can_execute_queries(role: str) -> bool:
    """Check if role can execute queries."""
    return has_permission(role, Permission.EXECUTE_QUERIES)


def can_view_config(role: str) -> bool:
    """Check if role can view configuration."""
    return has_permission(role, Permission.VIEW_CONFIG)


def can_manage_agents(role: str) -> bool:
    """Check if role can manage agents."""
    return has_permission(role, Permission.MANAGE_AGENTS)
