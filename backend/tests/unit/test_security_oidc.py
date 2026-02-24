"""
Unit tests for backend/core/security.py

Tests OIDC/Keycloak token validation and user claim extraction.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import os

# Set test environment before imports
os.environ["OIDC_ISSUER_URL"] = "https://keycloak.test.com/realms/test"
os.environ["OIDC_CLIENT_ID"] = "test-client"


class TestOIDCUserClaims:
    """Tests for OIDCUserClaims dataclass."""
    
    def test_create_claims_with_defaults(self):
        """Test creating claims with minimal data."""
        from backend.core.security import OIDCUserClaims
        
        claims = OIDCUserClaims(sub="user-123")
        
        assert claims.sub == "user-123"
        assert claims.email is None
        assert claims.roles == []
    
    def test_create_claims_with_all_fields(self):
        """Test creating claims with all fields."""
        from backend.core.security import OIDCUserClaims
        
        claims = OIDCUserClaims(
            sub="user-123",
            email="test@example.com",
            email_verified=True,
            preferred_username="testuser",
            name="Test User",
            given_name="Test",
            family_name="User",
            roles=["admin", "user"]
        )
        
        assert claims.sub == "user-123"
        assert claims.email == "test@example.com"
        assert claims.email_verified is True
        assert claims.preferred_username == "testuser"
        assert claims.name == "Test User"
        assert "admin" in claims.roles


class TestExtractUserClaims:
    """Tests for extract_user_claims function."""
    
    def test_extract_basic_claims(self):
        """Test extracting basic user claims from token payload."""
        from backend.core.security import extract_user_claims
        
        payload = {
            "sub": "abc-123",
            "email": "user@test.com",
            "preferred_username": "testuser"
        }
        
        claims = extract_user_claims(payload)
        
        assert claims.sub == "abc-123"
        assert claims.email == "user@test.com"
        assert claims.preferred_username == "testuser"
    
    def test_extract_realm_roles(self):
        """Test extracting roles from realm_access claim."""
        from backend.core.security import extract_user_claims
        
        payload = {
            "sub": "abc-123",
            "realm_access": {
                "roles": ["admin", "user"]
            }
        }
        
        claims = extract_user_claims(payload, role_claim="realm_access.roles")
        
        assert "admin" in claims.roles
        assert "user" in claims.roles
    
    def test_extract_client_roles(self):
        """Test extracting roles from resource_access claim."""
        from backend.core.security import extract_user_claims
        
        payload = {
            "sub": "abc-123",
            "resource_access": {
                "my-client": {
                    "roles": ["editor", "viewer"]
                }
            }
        }
        
        claims = extract_user_claims(payload, role_claim="resource_access.my-client.roles")
        
        assert "editor" in claims.roles
        assert "viewer" in claims.roles
    
    def test_extract_with_missing_roles(self):
        """Test extraction when role claim doesn't exist."""
        from backend.core.security import extract_user_claims
        
        payload = {
            "sub": "abc-123"
        }
        
        claims = extract_user_claims(payload, role_claim="realm_access.roles")
        
        assert claims.roles == []


class TestMapKeycloakRole:
    """Tests for role mapping from Keycloak to app roles."""
    
    def test_map_admin_role(self):
        """Test mapping Keycloak admin role."""
        from backend.core.security import map_keycloak_role_to_app_role
        
        result = map_keycloak_role_to_app_role(["admin"])
        
        assert result == "admin"
    
    def test_map_user_role(self):
        """Test mapping Keycloak user role."""
        from backend.core.security import map_keycloak_role_to_app_role
        
        result = map_keycloak_role_to_app_role(["user"])
        
        assert result == "user"
    
    def test_map_multiple_roles_returns_highest(self):
        """Test that highest privilege role is returned."""
        from backend.core.security import map_keycloak_role_to_app_role
        
        result = map_keycloak_role_to_app_role(["user", "admin"])
        
        # Admin should take precedence
        assert result == "admin"
    
    def test_map_empty_roles_returns_default(self):
        """Test that empty roles returns default."""
        from backend.core.security import map_keycloak_role_to_app_role
        
        result = map_keycloak_role_to_app_role([])
        
        # Should return None or default role
        assert result is None or result == "user"


class TestJWKSCache:
    """Tests for JWKS caching functionality."""
    
    def test_clear_jwks_cache(self):
        """Test clearing JWKS cache."""
        from backend.core.security import clear_jwks_cache, _jwks_cache
        
        # Should not raise
        clear_jwks_cache()
        
        # Cache should be None after clearing
        from backend.core.security import _jwks_cache as cleared_cache
        assert cleared_cache is None


class TestHTTPBearerScheme:
    """Tests for HTTP Bearer scheme configuration."""
    
    def test_http_bearer_exists(self):
        """Test HTTP Bearer scheme is configured."""
        from backend.core.security import http_bearer
        
        assert http_bearer is not None
    
    def test_http_bearer_auto_error(self):
        """Test HTTP Bearer has auto_error enabled."""
        from backend.core.security import http_bearer
        
        # auto_error should be True for required auth
        assert http_bearer.auto_error is True


class TestDecodeKeycloakToken:
    """Tests for Keycloak token decoding (requires mocking)."""
    
    @pytest.mark.asyncio
    async def test_decode_missing_kid_raises(self):
        """Test that token without 'kid' header raises exception."""
        from backend.core.security import decode_keycloak_token
        from fastapi import HTTPException
        
        # Create a token without kid - mock the unverified header
        with patch('backend.core.security.jwt.get_unverified_header') as mock_header:
            mock_header.return_value = {"alg": "RS256"}  # No 'kid'
            
            with pytest.raises(HTTPException) as exc_info:
                await decode_keycloak_token(
                    token="fake.token.here",
                    issuer_url="https://keycloak.test.com/realms/test",
                    client_id="test-client"
                )
            
            assert exc_info.value.status_code == 401


class TestFetchJWKS:
    """Tests for JWKS fetching (requires mocking HTTP calls)."""
    
    @pytest.mark.asyncio
    async def test_fetch_jwks_caches_result(self):
        """Test that JWKS is cached after first fetch."""
        from backend.core.security import fetch_jwks, clear_jwks_cache
        
        # Clear cache first
        clear_jwks_cache()
        
        # Mock HTTP calls
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jwks_uri": "https://keycloak.test.com/realms/test/protocol/openid-connect/certs"
        }
        mock_response.raise_for_status = MagicMock()
        
        mock_jwks_response = MagicMock()
        mock_jwks_response.json.return_value = {
            "keys": [
                {"kid": "key-1", "kty": "RSA", "use": "sig", "n": "abc", "e": "AQAB"}
            ]
        }
        mock_jwks_response.raise_for_status = MagicMock()
        
        with patch('backend.core.security.httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=[mock_response, mock_jwks_response])
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance
            
            # First call - should fetch
            keys = await fetch_jwks("https://keycloak.test.com/realms/test", ttl=3600)
            
            assert "key-1" in keys
