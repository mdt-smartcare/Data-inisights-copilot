"""
Unit tests for backend/core/security.py

Tests JWT token creation, decoding, and OIDC utilities.
"""
import pytest
from datetime import timedelta
from unittest.mock import patch
import os

# Set test environment before imports
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"


class TestJWTTokenCreation:
    """Tests for JWT token creation."""
    
    def test_create_access_token_basic(self):
        """Test basic token creation."""
        from backend.core.security import create_access_token
        
        data = {"sub": "testuser", "role": "admin"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT tokens have 3 parts separated by dots
        assert len(token.split('.')) == 3
    
    def test_create_access_token_with_custom_expiry(self):
        """Test token creation with custom expiration."""
        from backend.core.security import create_access_token
        
        data = {"sub": "testuser"}
        expires = timedelta(hours=2)
        token = create_access_token(data, expires_delta=expires)
        
        assert isinstance(token, str)
        assert len(token.split('.')) == 3
    
    def test_create_access_token_preserves_data(self):
        """Test that token creation preserves payload data."""
        from backend.core.security import create_access_token, decode_token
        
        data = {"sub": "testuser", "role": "editor", "custom_field": "value"}
        token = create_access_token(data)
        
        decoded = decode_token(token)
        assert decoded["sub"] == "testuser"
        assert decoded["role"] == "editor"
        assert decoded["custom_field"] == "value"
    
    def test_create_access_token_adds_metadata(self):
        """Test that token includes exp, iat, and type fields."""
        from backend.core.security import create_access_token, decode_token
        
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        decoded = decode_token(token)
        assert "exp" in decoded
        assert "iat" in decoded
        assert decoded["type"] == "access"


class TestJWTTokenDecoding:
    """Tests for JWT token decoding."""
    
    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        from backend.core.security import create_access_token, decode_token
        
        data = {"sub": "testuser", "role": "user"}
        token = create_access_token(data)
        
        decoded = decode_token(token)
        
        assert decoded["sub"] == "testuser"
        assert decoded["role"] == "user"
    
    def test_decode_invalid_token_raises(self):
        """Test that invalid token raises HTTPException."""
        from backend.core.security import decode_token
        from fastapi import HTTPException
        
        invalid_token = "invalid.token.string"
        
        with pytest.raises(HTTPException) as exc_info:
            decode_token(invalid_token)
        
        assert exc_info.value.status_code == 401
    
    def test_decode_tampered_token_raises(self):
        """Test that tampered token raises HTTPException."""
        from backend.core.security import create_access_token, decode_token
        from fastapi import HTTPException
        
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        # Tamper with the token
        parts = token.split('.')
        parts[1] = parts[1][:-5] + "XXXXX"  # Modify payload
        tampered_token = '.'.join(parts)
        
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tampered_token)
        
        assert exc_info.value.status_code == 401
    
    def test_decode_expired_token_raises(self):
        """Test that expired token raises HTTPException."""
        from backend.core.security import create_access_token, decode_token
        from fastapi import HTTPException
        from datetime import timedelta
        import time
        
        # Create token that expires in 1 second
        data = {"sub": "testuser"}
        token = create_access_token(data, expires_delta=timedelta(seconds=1))
        
        # Wait for expiration
        time.sleep(2)
        
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        
        assert exc_info.value.status_code == 401
    
    def test_decode_wrong_type_token_raises(self):
        """Test that token with wrong type raises HTTPException."""
        from backend.core.security import decode_token
        from backend.config import get_settings
        from fastapi import HTTPException
        from jose import jwt
        from datetime import datetime, timedelta
        
        settings = get_settings()
        
        # Create token with wrong type
        payload = {
            "sub": "testuser",
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "iat": datetime.utcnow(),
            "type": "refresh"  # Wrong type
        }
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
        
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        
        assert exc_info.value.status_code == 401


class TestGetTokenUsername:
    """Tests for get_token_username function."""
    
    def test_get_username_valid_token(self):
        """Test extracting username from valid token."""
        from backend.core.security import create_access_token, get_token_username
        
        data = {"sub": "testuser"}
        token = create_access_token(data)
        
        username = get_token_username(token)
        
        assert username == "testuser"
    
    def test_get_username_no_sub_raises(self):
        """Test that token without 'sub' claim raises HTTPException."""
        from backend.core.security import get_token_username
        from backend.config import get_settings
        from fastapi import HTTPException
        from jose import jwt
        from datetime import datetime, timedelta
        
        settings = get_settings()
        
        # Create token without 'sub'
        payload = {
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(minutes=30),
            "iat": datetime.utcnow(),
            "type": "access"
        }
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
        
        with pytest.raises(HTTPException) as exc_info:
            get_token_username(token)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token payload" in str(exc_info.value.detail)
    
    def test_get_username_invalid_token_raises(self):
        """Test that invalid token raises HTTPException."""
        from backend.core.security import get_token_username
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            get_token_username("invalid.token.here")
        
        assert exc_info.value.status_code == 401


class TestHTTPBearerScheme:
    """Tests for HTTP Bearer scheme configuration."""
    
    def test_http_bearer_exists(self):
        """Test HTTP Bearer scheme is configured."""
        from backend.core.security import http_bearer
        
        assert http_bearer is not None
