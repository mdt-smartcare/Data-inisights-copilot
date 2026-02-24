"""
Tests for authentication API routes.

With OIDC integration, the auth routes only contain the /me endpoint
for retrieving the current user's profile. Registration and login
are handled by the external Identity Provider (Keycloak).
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


class TestGetCurrentUserProfileEndpoint:
    """Tests for /me endpoint (get_current_user_profile)."""
    
    def test_function_exists(self):
        """Test get_current_user_profile function exists."""
        from backend.api.routes.auth import get_current_user_profile
        assert get_current_user_profile is not None
    
    def test_function_is_async(self):
        """Test get_current_user_profile is async."""
        import asyncio
        from backend.api.routes.auth import get_current_user_profile
        assert asyncio.iscoroutinefunction(get_current_user_profile)


class TestAuthImports:
    """Tests for auth module imports."""
    
    def test_logger_configured(self):
        """Test logger is configured."""
        from backend.api.routes.auth import logger
        assert logger is not None
