"""
Security utilities for OIDC/Keycloak JWT token verification.

This module validates tokens issued by Keycloak using RS256 algorithm
and JWKS (JSON Web Key Set) for signature verification.
"""
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import httpx
from jose import jwt, JWTError, jwk
from jose.exceptions import JWKError
from fastapi import HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer

logger = logging.getLogger(__name__)

# HTTP Bearer scheme for extracting tokens
http_bearer = HTTPBearer(auto_error=True)

# Keep oauth2_scheme for backward compatibility with existing code
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


# ============================================
# JWKS Cache
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
        issuer_url: The OIDC issuer URL (e.g., https://keycloak.example.com/realms/myrealm)
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
            
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch JWKS from {issuer_url}: {e}")
        
        # If we have expired cache, use it as fallback
        if _jwks_cache:
            logger.warning("Using expired JWKS cache as fallback")
            return _jwks_cache.keys
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to validate token: OIDC provider unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching JWKS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token validation configuration error"
        )


def clear_jwks_cache():
    """Clear the JWKS cache. Useful for testing or forcing refresh."""
    global _jwks_cache
    _jwks_cache = None


# ============================================
# Token Verification
# ============================================

@dataclass
class OIDCUserClaims:
    """Extracted claims from an OIDC token."""
    sub: str  # Subject (unique user ID from Keycloak)
    email: Optional[str] = None
    email_verified: bool = False
    preferred_username: Optional[str] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    roles: List[str] = None
    
    def __post_init__(self):
        if self.roles is None:
            self.roles = []


async def decode_keycloak_token(
    token: str,
    issuer_url: str,
    client_id: str,
    audience: Optional[str] = None,
    jwks_cache_ttl: int = 3600
) -> Dict[str, Any]:
    """
    Decode and verify a Keycloak JWT token.
    
    Performs the following validations:
    - Signature verification using JWKS
    - Expiration check
    - Issuer verification
    - Audience verification (if specified)
    
    Args:
        token: The JWT token string
        issuer_url: Expected issuer URL (Keycloak realm URL)
        client_id: OIDC client ID
        audience: Expected audience claim (optional, defaults to client_id)
        jwks_cache_ttl: JWKS cache TTL in seconds
    
    Returns:
        Decoded token payload as dictionary
    
    Raises:
        HTTPException: If token is invalid, expired, or verification fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Get unverified header to extract key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")
        
        if not kid:
            logger.warning("Token missing 'kid' header")
            raise credentials_exception
        
        # Fetch JWKS and get the signing key
        jwks = await fetch_jwks(issuer_url, ttl=jwks_cache_ttl)
        
        if kid not in jwks:
            # Key not found - try refreshing cache once
            logger.info(f"Key ID {kid} not in cache, refreshing JWKS")
            clear_jwks_cache()
            jwks = await fetch_jwks(issuer_url, ttl=jwks_cache_ttl)
            
            if kid not in jwks:
                logger.error(f"Key ID {kid} not found in JWKS")
                raise credentials_exception
        
        key_data = jwks[kid]
        
        # Construct the public key
        try:
            public_key = jwk.construct(key_data)
        except JWKError as e:
            logger.error(f"Failed to construct key from JWK: {e}")
            raise credentials_exception
        
        # Determine expected audience
        expected_audience = audience or client_id
        
        # Decode and verify the token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[alg],
            audience=expected_audience,
            issuer=issuer_url,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_iat": True,
            }
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTClaimsError as e:
        logger.warning(f"Token claims validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token claims validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.warning(f"JWT validation error: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected token validation error: {e}")
        raise credentials_exception


def extract_user_claims(payload: Dict[str, Any], role_claim: str = "realm_access.roles") -> OIDCUserClaims:
    """
    Extract user claims from a decoded OIDC token payload.
    
    Args:
        payload: Decoded JWT payload
        role_claim: Dot-notation path to roles claim 
                   (e.g., "realm_access.roles" or "resource_access.myapp.roles")
    
    Returns:
        OIDCUserClaims object with extracted user information
    """
    # Extract basic claims
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token missing 'sub' claim")
    
    # Extract roles from nested claim path
    roles = []
    if role_claim:
        parts = role_claim.split(".")
        current = payload
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, {})
            else:
                current = {}
                break
        if isinstance(current, list):
            roles = current
    
    
    return OIDCUserClaims(
        sub=sub,
        email=payload.get("email"),
        email_verified=payload.get("email_verified", False),
        preferred_username=payload.get("preferred_username"),
        name=payload.get("name"),
        given_name=payload.get("given_name"),
        family_name=payload.get("family_name"),
        roles=roles
    )


# Note: map_keycloak_role_to_app_role has been moved to core/roles.py
# Import from there: from backend.core.roles import map_keycloak_role
# Keeping backward compatibility alias:
def map_keycloak_role_to_app_role(keycloak_roles: List[str]) -> str:
    """Backward compatibility alias. Use map_keycloak_role from core/roles.py instead."""
    from backend.core.roles import map_keycloak_role
    return map_keycloak_role(keycloak_roles)
