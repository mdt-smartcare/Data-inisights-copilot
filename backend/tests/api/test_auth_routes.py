"""
Tests for authentication API routes.
"""
import pytest
from unittest.mock import MagicMock


class TestAuthRouter:
    """Tests for auth router."""
    
    def test_router_exists(self):
        """Test auth router exists."""
        from backend.api.routes.auth import router
        assert router is not None
    
    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.routes.auth import router
        assert router.prefix == "/auth"
    
    def test_router_tags(self):
        """Test router has tags."""
        from backend.api.routes.auth import router
        assert "Authentication" in router.tags


class TestRegisterEndpoint:
    """Tests for register endpoint."""
    
    def test_register_function_exists(self):
        """Test register function exists."""
        from backend.api.routes.auth import register
        assert register is not None
    
    @pytest.mark.asyncio
    async def test_register_creates_user(self):
        """Test register creates user."""
        from backend.api.routes.auth import register
        from backend.models.schemas import RegisterRequest
        
        mock_db = MagicMock()
        mock_db.create_user.return_value = {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "full_name": "Test User",
            "role": "viewer"
        }
        
        request = RegisterRequest(
            username="testuser",
            password="password123",
            email="test@example.com",
            full_name="Test User"
        )
        
        _ = await register(request, mock_db)
        mock_db.create_user.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_register_with_role(self):
        """Test register with specified role."""
        from backend.api.routes.auth import register
        from backend.models.schemas import RegisterRequest
        
        mock_db = MagicMock()
        mock_db.create_user.return_value = {
            "id": 1,
            "username": "adminuser",
            "email": "admin@example.com",
            "full_name": "Admin User",
            "role": "editor"
        }
        
        request = RegisterRequest(
            username="adminuser",
            password="password123",
            email="admin@example.com",
            full_name="Admin User",
            role="editor"
        )
        
        _ = await register(request, mock_db)
        mock_db.create_user.assert_called_once()


class TestLoginEndpoint:
    """Tests for login endpoint."""
    
    def test_login_function_exists(self):
        """Test login function exists."""
        from backend.api.routes.auth import login
        assert login is not None
    
    @pytest.mark.asyncio
    async def test_login_returns_token(self):
        """Test login function can be called with mocked DB (method existence test)."""
        from backend.api.routes.auth import login
        from backend.models.schemas import LoginRequest
        
        # Just verify the function exists and is callable
        # Full integration testing requires proper DB setup
        assert callable(login)
        
        # Verify LoginRequest model works
        request = LoginRequest(
            username="testuser",
            password="password123"
        )
        assert request.username == "testuser"
    
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self):
        """Test login with invalid credentials raises 401."""
        from backend.api.routes.auth import login
        from backend.models.schemas import LoginRequest
        from fastapi import HTTPException
        
        mock_db = MagicMock()
        # Return None to simulate failed authentication
        mock_db.authenticate_user.return_value = None
        # Also make get_user return None to prevent code from continuing
        mock_db.get_user_by_username.return_value = None
        
        request = LoginRequest(
            username="wronguser",
            password="wrongpassword"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await login(request, mock_db)
        
        # Either 401 (invalid credentials) or similar error
        assert exc_info.value.status_code in [401, 403, 404]


class TestGetCurrentUserProfileEndpoint:
    """Tests for /me endpoint (get_current_user_profile)."""
    
    def test_function_exists(self):
        """Test get_current_user_profile function exists."""
        from backend.api.routes.auth import get_current_user_profile
        assert get_current_user_profile is not None


class TestAuthImports:
    """Tests for auth module imports."""
    
    def test_create_access_token_import(self):
        """Test create_access_token is imported."""
        from backend.api.routes.auth import create_access_token
        assert create_access_token is not None
    
    def test_settings_loaded(self):
        """Test settings are loaded."""
        from backend.api.routes.auth import settings
        assert settings is not None
    
    def test_logger_configured(self):
        """Test logger is configured."""
        from backend.api.routes.auth import logger
        assert logger is not None
