"""
Security utilities for OIDC/Keycloak authentication.

Provides OIDC/Keycloak token verification using JWKS (JSON Web Key Set).
User authentication and password management is handled by Keycloak.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import time

import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, status
from app.core.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================
# OIDC/Keycloak Token Verification
# ============================================

@dataclass
class JWKSCache:
    """Cache for JWKS keys with TTL support."""
    keys: Dict[str, Any]
    fetched_at: float
    ttl: int

    def is_expired(self) -> bool:
        """Check if cache has expired."""
        return time.time() - self.fetched_at > self.ttl


# Global JWKS cache
_jwks_cache: Optional[JWKSCache] = None


async def fetch_jwks(issuer_url: str, ttl: int = 3600) -> Dict[str, Any]:
    """
    Fetch JWKS from the OIDC provider's well-known endpoint.
    
    Uses caching to avoid fetching on every request.
    
    Args:
        issuer_url: OIDC issuer URL (e.g., https://keycloak.example.com/realms/myrealm)
        ttl: Cache time-to-live in seconds (default: 1 hour)
    
    Returns:
        Dictionary mapping key IDs (kid) to JWK objects
    
    Raises:
        HTTPException: If JWKS cannot be fetched
    """
    global _jwks_cache
    
    # Return cached keys if still valid
    if _jwks_cache and not _jwks_cache.is_expired():
        return _jwks_cache.keys
    
    # Fetch JWKS from well-known endpoint
    jwks_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # First, get the OIDC configuration to find JWKS URI
            config_response = await client.get(jwks_url)
            config_response.raise_for_status()
            oidc_config = config_response.json()
            
            jwks_uri = oidc_config.get("jwks_uri")
            if not jwks_uri:
                raise ValueError("jwks_uri not found in OIDC configuration")
            
            # Fetch the actual JWKS
            jwks_response = await client.get(jwks_uri)
            jwks_response.raise_for_status()
            jwks_data = jwks_response.json()
            
            # Build a mapping of kid -> key
            keys = {}
            for key_data in jwks_data.get("keys", []):
                kid = key_data.get("kid")
                if kid:
                    keys[kid] = key_data
            
            # Cache the keys
            _jwks_cache = JWKSCache(keys=keys, fetched_at=time.time(), ttl=ttl)
            logger.info(f"JWKS cache refreshed with {len(keys)} keys from {issuer_url}")
            
            return keys
            
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from {issuer_url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch OIDC keys for token validation"
        )


async def decode_oidc_token(
    token: str,
    issuer_url: str,
    client_id: str,
    audience: Optional[str] = None,
    jwks_cache_ttl: int = 3600
) -> Dict[str, Any]:
    """
    Decode and verify an OIDC token from Keycloak.
    
    Args:
        token: JWT token from Keycloak
        issuer_url: Expected issuer URL
        client_id: Expected client ID
        audience: Expected audience (defaults to client_id)
        jwks_cache_ttl: JWKS cache TTL in seconds
    
    Returns:
        Decoded token payload
    
    Raises:
        HTTPException: If token is invalid
    """
    if not audience:
        audience = client_id
    
    try:
        # Get JWKS keys
        jwks = await fetch_jwks(issuer_url, ttl=jwks_cache_ttl)
        
        # Decode header to get kid (key ID)
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid or kid not in jwks:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: key ID not found in JWKS"
            )
        
        # Get the public key for verification
        public_key = jwks[kid]
        
        # Decode and verify token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer_url
        )
        
        return payload
        
    except JWTError as e:
        logger.error(f"OIDC token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid OIDC token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


@dataclass
class OIDCUserClaims:
    """User claims extracted from OIDC token."""
    sub: str  # Subject (user ID from Keycloak)
    email: str
    name: str
    roles: list[str]
    preferred_username: Optional[str] = None


def extract_user_claims(payload: Dict[str, Any], role_claim: str = "realm_access.roles") -> OIDCUserClaims:
    """
    Extract user claims from OIDC token payload.
    
    Args:
        payload: Decoded JWT payload
        role_claim: Path to roles claim (e.g., "realm_access.roles")
    
    Returns:
        OIDCUserClaims instance
    
    Raises:
        HTTPException: If required claims are missing
    """
    try:
        # Basic claims
        sub = payload["sub"]
        email = payload.get("email", "")
        name = payload.get("name", email)
        preferred_username = payload.get("preferred_username")
        
        # Extract roles from nested path (e.g., realm_access.roles)
        roles = []
        if role_claim:
            parts = role_claim.split(".")
            value = payload
            for part in parts:
                value = value.get(part, {})
            
            if isinstance(value, list):
                roles = value
        
        return OIDCUserClaims(
            sub=sub,
            email=email,
            name=name,
            roles=roles,
            preferred_username=preferred_username
        )
        
    except KeyError as e:
        logger.error(f"Missing required claim in OIDC token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: missing required claim {e}"
        )
