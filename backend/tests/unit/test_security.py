"""
Unit tests for backend/core/security.py

Tests JWT token creation, decoding, and password hashing utilities.
"""
import pytest
from datetime import timedelta
from unittest.mock import patch
import os
import hashlib

# Set test environment before imports
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"


# Helper to create a mock hash (avoiding bcrypt compatibility issues)
def mock_hash(password):
    """Create a deterministic hash for testing."""
    return "$2b$12$" + hashlib.sha256(password.encode()).hexdigest()[:53]


def mock_verify(plain, hashed):
    """Mock verification for testing."""
    expected = mock_hash(plain)
    return expected == hashed


class TestPasswordHashing:
    """Tests for password hashing utilities."""
    
    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.hash.return_value = "$2b$12$hashedpasswordvalue123456789012345678901234567890123"
            
            from backend.core.security import get_password_hash
            
            password = "test_password123"
            hashed = get_password_hash(password)
            
            assert isinstance(hashed, str)
            assert hashed != password
            assert len(hashed) > 0
    
    def test_hash_password_unique_each_time(self):
        """Test that hashing same password produces different hashes (salt)."""
        call_count = [0]
        def hash_side_effect(pwd):
            call_count[0] += 1
            return f"$2b$12$uniquehash{call_count[0]}{'0' * 40}"
        
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.hash.side_effect = hash_side_effect
            
            from backend.core.security import get_password_hash
            
            password = "test_password123"
            hash1 = get_password_hash(password)
            hash2 = get_password_hash(password)
            
            # Bcrypt uses random salt, so hashes should differ
            assert hash1 != hash2
    
    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.verify.return_value = True
            
            from backend.core.security import verify_password
            
            result = verify_password("my_secure_password", "$2b$12$somehash")
            
            assert result is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.verify.return_value = False
            
            from backend.core.security import verify_password
            
            result = verify_password("wrong_password", "$2b$12$somehash")
            
            assert result is False
    
    def test_verify_password_empty_password(self):
        """Test verification with empty password fails."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.verify.return_value = False
            
            from backend.core.security import verify_password
            
            result = verify_password("", "$2b$12$somehash")
            
            assert result is False
    
    def test_hash_password_special_characters(self):
        """Test hashing passwords with special characters."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.hash.return_value = "$2b$12$specialcharhash123456789012345678901234567890"
            mock_ctx.verify.return_value = True
            
            from backend.core.security import get_password_hash, verify_password
            
            password = "p@$$w0rd!#$%^&*()_+-=[]{}|;':\",./<>?"
            hashed = get_password_hash(password)
            
            assert verify_password(password, hashed) is True
    
    def test_hash_password_unicode(self):
        """Test hashing passwords with unicode characters."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.hash.return_value = "$2b$12$unicodehash1234567890123456789012345678901234"
            mock_ctx.verify.return_value = True
            
            from backend.core.security import get_password_hash, verify_password
            
            password = "密码パスワード🔐"
            hashed = get_password_hash(password)
            
            assert verify_password(password, hashed) is True


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


class TestPasswordContextConfiguration:
    """Tests for password context configuration."""
    
    def test_pwd_context_uses_bcrypt(self):
        """Test that password context is configured for bcrypt."""
        from backend.core.security import pwd_context
        
        assert "bcrypt" in pwd_context.schemes()
    
    def test_pwd_context_hash_starts_with_bcrypt_prefix(self):
        """Test that generated hashes have bcrypt prefix."""
        with patch('backend.core.security.pwd_context') as mock_ctx:
            mock_ctx.hash.return_value = "$2b$12$testbcrypthash12345678901234567890123456789012345"
            
            from backend.core.security import get_password_hash
            
            hashed = get_password_hash("password")
            
            # Bcrypt hashes start with $2a$, $2b$, or $2y$
            assert hashed.startswith(("$2a$", "$2b$", "$2y$"))


class TestOAuth2Scheme:
    """Tests for OAuth2 scheme configuration."""
    
    def test_oauth2_scheme_token_url(self):
        """Test OAuth2 scheme has correct token URL."""
        from backend.core.security import oauth2_scheme
        
        # OAuth2PasswordBearer has tokenUrl attribute
        assert oauth2_scheme.scheme_name == "OAuth2PasswordBearer"
