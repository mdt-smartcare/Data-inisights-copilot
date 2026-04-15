"""
Role-based access control (RBAC) utilities.

Defines roles, hierarchy, permission checks, and FastAPI dependencies
for enforcing role-based access.
"""
from enum import Enum
from typing import List, Set, Optional, Callable
from functools import wraps

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.session import get_db_session
from app.core.auth.security import decode_oidc_token, extract_user_claims
from app.core.config import get_settings
from app.core.models.auth import Role, TokenData
from app.modules.users.schemas import User  # Use module User schema (matches repository)
from app.core.utils.logging import get_logger

logger = get_logger(__name__)

# HTTP Bearer for extracting tokens
security = HTTPBearer()


# ============================================
# Role Hierarchy & Utilities
# ============================================

# Role hierarchy: lower index = higher privilege
ROLE_HIERARCHY: List[str] = [
    Role.SUPER_ADMIN.value,
    Role.ADMIN.value,
    Role.EDITOR.value,
    Role.USER.value,
]

# Valid roles set
VALID_ROLES: Set[str] = {r.value for r in Role}

# Default role for new users
DEFAULT_ROLE: str = Role.USER.value


def role_index(role: str) -> int:
    """
    Get the index of a role in the hierarchy.
    
    Lower index = higher privilege.
    
    Args:
        role: Role name
    
    Returns:
        Index in hierarchy (or max int if not found)
    """
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return len(ROLE_HIERARCHY)  # Unknown roles have lowest privilege


def role_at_least(user_role: str, required_role: str) -> bool:
    """
    Check if user's role meets or exceeds the required role.
    
    Args:
        user_role: User's current role
        required_role: Minimum required role
    
    Returns:
        True if user has sufficient privileges
    """
    return role_index(user_role) <= role_index(required_role)


def is_valid_role(role: str) -> bool:
    """Check if a role is valid."""
    return role in VALID_ROLES


def get_all_roles() -> List[str]:
    """Get list of all valid roles."""
    return ROLE_HIERARCHY.copy()


# ============================================
# Keycloak Role Mapping
# ============================================

# Mapping of Keycloak roles to internal roles
# Multiple Keycloak role names can map to the same app role
# Checked in order (first match wins, highest privilege first)
KEYCLOAK_ROLE_MAPPINGS: List[tuple] = [
    # (list of keycloak role names, app role)
    (["super_admin", "superadmin"], Role.SUPER_ADMIN.value),
    (["admin", "administrator"], Role.ADMIN.value),
    (["user", "default-roles-data-insights-copilot", "member"], Role.USER.value),
]


def map_keycloak_role(keycloak_roles: List[str]) -> str:
    """
    Map Keycloak roles to internal role.
    
    Returns the highest privilege role found.
    Performs case-insensitive matching for flexibility.
    
    Args:
        keycloak_roles: List of roles from Keycloak token
    
    Returns:
        Internal role name (defaults to USER if no mapping found)
    """
    # Normalize roles to lowercase for case-insensitive comparison
    roles_lower = [r.lower() for r in keycloak_roles]
    
    for keycloak_role_names, app_role in KEYCLOAK_ROLE_MAPPINGS:
        for kc_role in keycloak_role_names:
            if kc_role.lower() in roles_lower:
                return app_role
    
    return DEFAULT_ROLE


def detect_role_change(old_role: Optional[str], new_role: Optional[str]) -> Optional[str]:
    """
    Detect if a role change is a promotion or demotion.
    
    Uses the ROLE_HIERARCHY to determine direction of change.
    Only logs changes involving admin+ roles.
    
    Args:
        old_role: Previous role
        new_role: New role
        
    Returns:
        'promoted' if promotion to admin+, 'demoted' if demotion from admin+, None otherwise
    """
    if not old_role or not new_role or old_role == new_role:
        return None
    
    old_index = role_index(old_role)
    new_index = role_index(new_role)
    admin_index = role_index(Role.ADMIN.value)
    
    if new_index < old_index:
        # Promotion (lower index = higher privilege)
        # Only log if promoted TO admin or higher
        if new_index <= admin_index:
            return "promoted"
    elif new_index > old_index:
        # Demotion
        # Only log if demoted FROM admin or higher
        if old_index <= admin_index:
            return "demoted"
    
    return None


# ============================================
# Permission Checks
# ============================================

def can_manage_users(role: str) -> bool:
    """Check if role can manage users (create, update, delete)."""
    return role_at_least(role, Role.ADMIN.value)


def can_manage_agents(role: str) -> bool:
    """Check if role can manage agents and configurations."""
    return role_at_least(role, Role.ADMIN.value)


def can_edit_config(role: str) -> bool:
    """Check if role can edit agent configurations."""
    return role_at_least(role, Role.ADMIN.value)


def can_execute_queries(role: str) -> bool:
    """Check if role can execute queries and chat."""
    return role_at_least(role, Role.USER.value)


def can_view_all_audit_logs(role: str) -> bool:
    """Check if role can view all audit logs."""
    return role_at_least(role, Role.ADMIN.value)


def can_manage_connections(role: str) -> bool:
    """Check if role can manage database connections."""
    return role_at_least(role, Role.ADMIN.value)


# ============================================
# FastAPI Dependencies
# ============================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    """
    Validate OIDC/Keycloak token and return current user.
    
    Performs Just-In-Time (JIT) user provisioning for OIDC users:
    - Validates token against Keycloak's JWKS
    - Creates new users automatically on first login
    - Syncs super_admin role from Keycloak
    
    Args:
        credentials: HTTP Bearer credentials
        session: Database session
    
    Returns:
        User instance
    
    Raises:
        HTTPException: If token is invalid or user is inactive
    """
    token = credentials.credentials
    settings = get_settings()
    
    # Try OIDC validation first (if enabled)
    if settings.oidc_enabled:
        try:
            payload = await decode_oidc_token(
                token=token,
                issuer_url=settings.oidc_issuer_url,
                client_id=settings.oidc_client_id,
                audience=settings.oidc_audience,
                jwks_cache_ttl=settings.oidc_jwks_cache_ttl
            )
            
            # Extract user claims
            claims = extract_user_claims(payload, role_claim=settings.oidc_role_claim)
            
            # Get or create user (JIT provisioning)
            from app.modules.users.repository import UserRepository
            user_repo = UserRepository(session)
            
            user = await user_repo.get_by_external_id(claims.sub)
            
            if user:
                # Check if active
                if not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User account is inactive"
                    )
                
                # Sync super_admin role from Keycloak
                keycloak_role = map_keycloak_role(claims.roles)
                if keycloak_role == Role.SUPER_ADMIN.value and user.role != Role.SUPER_ADMIN.value:
                    # Promote to super_admin
                    old_role = user.role
                    from app.modules.users.schemas import UserUpdate
                    await user_repo.update(user.id, UserUpdate(role=Role.SUPER_ADMIN.value))
                    user.role = Role.SUPER_ADMIN.value
                    
                    # Audit: Role promoted via Keycloak sync
                    from app.modules.audit.schemas import AuditAction
                    from app.modules.audit.helpers import log_audit
                    await log_audit(
                        session=session,
                        action=AuditAction.ROLE_PROMOTED,
                        actor=user,
                        resource_type="user",
                        resource_id=str(user.id),
                        resource_name=user.username,
                        details={
                            "old_role": old_role,
                            "new_role": Role.SUPER_ADMIN.value,
                            "source": "keycloak_sync"
                        },
                    )
                elif keycloak_role != Role.SUPER_ADMIN.value and user.role == Role.SUPER_ADMIN.value:
                    # Demote from super_admin
                    old_role = user.role
                    from app.modules.users.schemas import UserUpdate
                    await user_repo.update(user.id, UserUpdate(role=keycloak_role))
                    user.role = keycloak_role
                    
                    # Audit: Role demoted via Keycloak sync
                    from app.modules.audit.schemas import AuditAction
                    from app.modules.audit.helpers import log_audit
                    await log_audit(
                        session=session,
                        action=AuditAction.ROLE_DEMOTED,
                        actor=user,
                        resource_type="user",
                        resource_id=str(user.id),
                        resource_name=user.username,
                        details={
                            "old_role": old_role,
                            "new_role": keycloak_role,
                            "source": "keycloak_sync"
                        },
                    )
                
                return user
            else:
                # Create new user (JIT provisioning)
                from app.modules.users.schemas import UserCreate
                role = map_keycloak_role(claims.roles)
                
                # Use email as username for OIDC users
                username = claims.email or claims.preferred_username or claims.sub
                
                user = await user_repo.create(UserCreate(
                    username=username,
                    external_id=claims.sub,
                    email=claims.email,
                    full_name=claims.name,
                    role=role,
                    is_active=True
                ))
                
                logger.info(f"JIT provisioned new user: {user.email} with role {role}")
                
                # Audit: Log if admin/superadmin is registered via JIT provisioning
                if can_manage_users(role):
                    from app.modules.audit.schemas import AuditAction
                    from app.modules.audit.helpers import log_audit
                    await log_audit(
                        session=session,
                        action=AuditAction.ADMIN_REGISTERED,
                        actor=user,
                        resource_type="user",
                        resource_id=str(user.id),
                        resource_name=user.username,
                        details={
                            "role": role,
                            "source": "jit_provisioning",
                            "email": user.email
                        },
                    )
                
                return user
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OIDC token validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # OIDC is not enabled
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service not configured"
        )


def require_role(required_role: Role) -> Callable:
    """
    Dependency factory for role-based access control.
    
    Args:
        required_role: Minimum required role
    
    Returns:
        FastAPI dependency function
    
    Usage:
        @router.delete("/users/{user_id}")
        async def delete_user(
            user_id: UUID,
            current_user: User = Depends(require_role(Role.ADMIN))
        ):
            ...
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not role_at_least(current_user.role, required_role.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role.value}"
            )
        return current_user
    
    return role_checker


# Convenience dependencies for common role checks
require_user = require_role(Role.USER)
require_editor = require_role(Role.EDITOR)
require_admin = require_role(Role.ADMIN)
require_super_admin = require_role(Role.SUPER_ADMIN)


def require_permission(permission_check: Callable[[str], bool], permission_name: str = "this action") -> Callable:
    """
    Dependency factory for permission-based access control.
    
    Args:
        permission_check: Function that takes role and returns bool
        permission_name: Human-readable permission name for error messages
    
    Returns:
        FastAPI dependency function
    
    Usage:
        @router.post("/agents")
        async def create_agent(
            current_user: User = Depends(require_permission(can_manage_agents, "manage agents"))
        ):
            ...
    """
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not permission_check(current_user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {permission_name}"
            )
        return current_user
    
    return permission_checker
