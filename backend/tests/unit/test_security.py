"""
Unit tests for backend/core/security.py

Tests OIDC/Keycloak token verification and claim extraction.
"""
import pytest
from unittest.mock import patch, AsyncMock
import os
from datetime import datetime

# Set test environment before imports
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"

from backend.core.security import extract_user_claims, OIDCUserClaims, clear_jwks_cache

class TestOIDCClaimExtraction:
    """Tests for extract_user_claims function."""
    
    def test_extract_basic_claims(self):
        """Test extracting standard OIDC claims."""
        payload = {
            "sub": "user-123",
            "email": "test@example.com",
            "preferred_username": "testuser",
            "name": "Test User",
            "realm_access": {"roles": ["user", "admin"]}
        }
        
        claims = extract_user_claims(payload)
        
        assert claims.sub == "user-123"
        assert claims.email == "test@example.com"
        assert claims.preferred_username == "testuser"
        assert "admin" in claims.roles
        assert "user" in claims.roles

    def test_extract_nested_roles(self):
        """Test extracting roles from nested resource_access claim."""
        payload = {
            "sub": "user-123",
            "resource_access": {
                "myapp": {
                    "roles": ["editor"]
                }
            }
        }
        
        claims = extract_user_claims(payload, role_claim="resource_access.myapp.roles")
        assert claims.roles == ["editor"]

    def test_missing_sub_raises_error(self):
        """Test that missing 'sub' claim raises ValueError."""
        payload = {"email": "test@example.com"}
        with pytest.raises(ValueError, match="missing 'sub' claim"):
            extract_user_claims(payload)

class TestJWKSCaching:
    """Tests for JWKS cache logic."""
    
    def test_clear_cache(self):
        """Test that clear_jwks_cache works."""
        from backend.core.security import _jwks_cache, JWKSCache
        import backend.core.security
        
        backend.core.security._jwks_cache = JWKSCache(keys={}, fetched_at=0, ttl=3600)
        assert backend.core.security._jwks_cache is not None
        
        clear_jwks_cache()
        assert backend.core.security._jwks_cache is None

class TestTokenDecoding:
    """Tests for decode_keycloak_token function (mocked)."""
    
    @pytest.mark.asyncio
    async def test_decode_token_success(self):
        """Test decoding token when signature is valid (mocked)."""
        from backend.core.security import decode_keycloak_token
        
        mock_payload = {"sub": "user-123", "iss": "http://keycloak/realm", "aud": "client-id"}
        
        with patch("backend.core.security.jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"kid": "key-1", "alg": "RS256"}
            
            with patch("backend.core.security.fetch_jwks", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = {"key-1": {"n": "...", "e": "..."}}
                
                with patch("backend.core.security.jwk.construct") as mock_construct:
                    with patch("backend.core.security.jwt.decode") as mock_decode:
                        mock_decode.return_value = mock_payload
                        
                        result = await decode_keycloak_token(
                            token="fake.token.here",
                            issuer_url="http://keycloak/realm",
                            client_id="client-id"
                        )
                        
                        assert result == mock_payload
                        mock_decode.assert_called_once()

    @pytest.mark.asyncio
    async def test_decode_token_expired_raises(self):
        """Test that expired token raises HTTPException."""
        from backend.core.security import decode_keycloak_token
        from fastapi import HTTPException
        from jose.exceptions import ExpiredSignatureError
        
        with patch("backend.core.security.jwt.get_unverified_header") as mock_header:
            mock_header.return_value = {"kid": "key-1"}
            with patch("backend.core.security.fetch_jwks", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = {"key-1": {}}
                with patch("backend.core.security.jwk.construct"):
                    with patch("backend.core.security.jwt.decode") as mock_decode:
                        mock_decode.side_effect = ExpiredSignatureError()
                        
                        with pytest.raises(HTTPException) as exc_info:
                            await decode_keycloak_token(
                                token="expired.token",
                                issuer_url="http://keycloak/realm",
                                client_id="client-id"
                            )
                        assert exc_info.value.status_code == 401
                        assert "expired" in exc_info.value.detail.lower()

class TestHTTPBearerScheme:
    """Tests for HTTP Bearer scheme configuration."""
    
    def test_http_bearer_exists(self):
        """Test HTTP Bearer scheme is configured."""
        from backend.core.security import http_bearer
        assert http_bearer is not None
