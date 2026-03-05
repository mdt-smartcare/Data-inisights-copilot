"""
Role-based access control dependencies.
Defines FastAPI dependencies for enforcing role-based access.

Role definitions and permission logic are centralized in core/roles.py.
"""
from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import get_settings
from backend.core.error_codes import ErrorCode
from backend.core.security import (
    decode_keycloak_token,
    extract_user_claims,
)
from backend.core.roles import (
    Role,
    UserRole,  # Backward compatibility alias
    ROLE_HIERARCHY,
    VALID_ROLES,
    DEFAULT_ROLE,
    role_at_least,
    map_keycloak_role,
    # Permission helpers
    can_manage_users,
    can_view_all_audit_logs,
    can_manage_connections,
    can_edit_config,
    can_publish_prompt,
    can_execute_queries,
    can_view_config,
    can_manage_agents,
    get_all_roles,
    is_valid_role,
)
from backend.sqliteDb.db import get_db_service
from backend.models.schemas import User
from backend.services.audit_service import AuditService, AuditAction


# HTTP Bearer for extracting tokens
_security = HTTPBearer()


# ============================================
# FastAPI Dependencies
# ============================================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security)
) -> User:
    """
    Validate the OIDC token and return the current user.
    
    This performs Just-In-Time (JIT) user provisioning:
    1. Validates the token against Keycloak's JWKS
    2. Extracts user claims (sub, email, name, roles)
    3. Looks up or creates the user in local database
    4. Syncs super_admin role from Keycloak (promotions and demotions)
       - admin/user role changes are managed locally, not synced
    """
    settings = get_settings()
    token = credentials.credentials
    
    # Validate token with Keycloak
    payload = await decode_keycloak_token(
        token=token,
        issuer_url=settings.oidc_issuer_url,
        client_id=settings.oidc_client_id,
        audience=settings.oidc_audience,
        jwks_cache_ttl=settings.oidc_jwks_cache_ttl
    )
    
    # Extract user claims from token
    claims = extract_user_claims(payload, role_claim=settings.oidc_role_claim)
    
    # Get or create user in local database (JIT provisioning)
    db_service = get_db_service()
    user_data = db_service.get_user_by_external_id(claims.sub)
    
    if user_data:
        # User exists - check if active
        if not user_data.get('is_active'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": "User account is inactive", "error_code": ErrorCode.USER_INACTIVE}
            )
        
        local_role = user_data.get('role', settings.oidc_default_role)
        
        # Sync super_admin role from Keycloak token (promotions and demotions)
        # Only super_admin changes are synced; admin/user changes are managed locally
        keycloak_role = map_keycloak_role(claims.roles)
        is_keycloak_super_admin = keycloak_role == Role.SUPER_ADMIN.value
        is_local_super_admin = local_role == Role.SUPER_ADMIN.value
        
        if is_keycloak_super_admin and not is_local_super_admin:
            # Promotion: Keycloak has super_admin, local doesn't
            db_service.update_user_role(user_data['id'], Role.SUPER_ADMIN.value)
            audit_service = AuditService()
            audit_service.log(
                action=AuditAction.USER_ROLE_SYNC,
                actor_id=user_data['id'],
                actor_username=user_data.get('username'),
                actor_role=Role.SUPER_ADMIN.value,
                resource_type="user",
                resource_id=str(user_data['id']),
                resource_name=user_data.get('username'),
                details={
                    "previous_role": local_role,
                    "new_role": Role.SUPER_ADMIN.value,
                    "action": "promotion",
                    "source": "keycloak_token"
                }
            )
            role = Role.SUPER_ADMIN.value
        elif is_local_super_admin and not is_keycloak_super_admin:
            # Demotion: Local has super_admin, Keycloak doesn't
            db_service.update_user_role(user_data['id'], keycloak_role)
            audit_service = AuditService()
            audit_service.log(
                action=AuditAction.USER_ROLE_SYNC,
                actor_id=user_data['id'],
                actor_username=user_data.get('username'),
                actor_role=keycloak_role,
                resource_type="user",
                resource_id=str(user_data['id']),
                resource_name=user_data.get('username'),
                details={
                    "previous_role": local_role,
                    "new_role": keycloak_role,
                    "action": "demotion",
                    "source": "keycloak_token"
                }
            )
            role = keycloak_role
        else:
            role = local_role
    else:
        # First-time login - create user with default role from Keycloak
        keycloak_default_role = map_keycloak_role(claims.roles)
        
        user_data = db_service.upsert_oidc_user(
            external_id=claims.sub,
            email=claims.email,
            username=claims.preferred_username,
            full_name=claims.name or f"{claims.given_name or ''} {claims.family_name or ''}".strip(),
            default_role=keycloak_default_role or settings.oidc_default_role
        )
        role = user_data.get('role', settings.oidc_default_role)
    
    return User(
        username=user_data.get('username'),
        role=role,
        id=user_data.get('id'),
        email=user_data.get('email'),
        full_name=user_data.get('full_name'),
        external_id=user_data.get('external_id')
    )


def require_role(allowed_roles: List[str]):
    """
    Dependency to enforce role-based access control.
    Usage: Depends(require_role([Role.ADMIN.value]))
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role: {current_user.role}"
            )
        return current_user
    return role_checker


def require_at_least(min_role: str):
    """
    Dependency to enforce minimum role level.
    Usage: Depends(require_at_least(Role.USER.value))
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        if not role_at_least(current_user.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires at least '{min_role}' role. Your role: {current_user.role}"
            )
        return current_user
    return role_checker


# ============================================
# Convenience Dependencies
# ============================================
# These use the centralized Role enum for consistency

# Super admin only - highest privilege level
require_super_admin = require_role([Role.SUPER_ADMIN.value])

# Admin or super admin - both can perform admin operations
require_admin = require_role([Role.SUPER_ADMIN.value, Role.ADMIN.value])

# Any authenticated user with at least user role
require_user = require_at_least(Role.USER.value)

# Backward compatibility alias
require_editor = require_admin  # Alias for migration (editor -> admin)
