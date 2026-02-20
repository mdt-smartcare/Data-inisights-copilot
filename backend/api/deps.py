"""
Dependency injection for FastAPI routes.
Provides reusable dependencies for authentication via OIDC/Keycloak.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.config import get_settings
from backend.core.security import (
    decode_keycloak_token,
    extract_user_claims,
    map_keycloak_role_to_app_role,
)
from backend.models.schemas import User
from backend.sqliteDb.db import get_db_service

settings = get_settings()
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to extract and validate the current user from OIDC/Keycloak token.
    
    This performs Just-In-Time (JIT) user provisioning:
    1. Validates the token against Keycloak's JWKS
    2. Extracts user claims (sub, email, name, roles)
    3. Looks up or creates the user in local database
    4. Uses local role if set, otherwise maps Keycloak roles
    
    Args:
        credentials: Bearer token from Authorization header
    
    Returns:
        User object with user info and role
    
    Raises:
        HTTPException: If token is invalid or OIDC provider unavailable
    """
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
                detail="User account is inactive"
            )
        
        # Use local role (hybrid approach - local takes precedence)
        role = user_data.get('role', settings.oidc_default_role)
    else:
        # First-time login - create user with default role from Keycloak
        keycloak_default_role = map_keycloak_role_to_app_role(claims.roles)
        
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


# Re-export role-based dependencies from permissions (they now use the new get_current_user)
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
