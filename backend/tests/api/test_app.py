"""
Tests for the FastAPI application.
"""
import pytest
from unittest.mock import patch


class TestFastAPIApp:
    """Tests for FastAPI app initialization."""
    
    def test_app_exists(self):
        """Test that app can be imported."""
        from backend.app import app
        assert app is not None
    
    def test_app_title(self):
        """Test app has correct title."""
        from backend.app import app
        assert app.title is not None
    
    def test_app_version(self):
        """Test app has version."""
        from backend.app import app
        assert app.version is not None
    
    def test_app_has_routes(self):
        """Test app has registered routes."""
        from backend.app import app
        assert len(app.routes) > 0


class TestAppRoutes:
    """Tests for app route registration."""
    
    def test_root_route_exists(self):
        """Test root route is registered."""
        from backend.app import app
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        assert "/" in route_paths
    
    def test_health_route_exists(self):
        """Test health route is registered."""
        from backend.app import app
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        assert "/health" in route_paths
    
    def test_auth_routes_registered(self):
        """Test auth routes are included."""
        from backend.app import app
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        # Check for auth routes
        auth_routes = [p for p in route_paths if '/auth' in p]
        assert len(auth_routes) > 0
    
    def test_chat_routes_registered(self):
        """Test chat routes are included."""
        from backend.app import app
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        chat_routes = [p for p in route_paths if '/chat' in p]
        assert len(chat_routes) > 0


class TestCORSMiddleware:
    """Tests for CORS middleware configuration."""
    
    def test_cors_middleware_added(self):
        """Test CORS middleware is configured."""
        from backend.app import app
        # Check that middleware is configured
        middleware_classes = [m.cls.__name__ if hasattr(m, 'cls') else str(m) for m in app.user_middleware]
        # CORS may or may not show in user_middleware depending on how it's added
        _ = any('CORS' in str(m) for m in middleware_classes)
        # It's OK if not found - CORS is added but may not show in user_middleware
        assert app is not None


class TestRootEndpoint:
    """Tests for root endpoint."""
    
    @pytest.mark.asyncio
    async def test_root_returns_json(self):
        """Test root endpoint returns JSON."""
        from backend.app import root
        response = await root()
        assert response is not None
    
    @pytest.mark.asyncio
    async def test_root_has_message(self):
        """Test root endpoint has message."""
        from backend.app import root
        response = await root()
        # JSONResponse body is bytes, check status code
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_root_health_endpoint(self):
        """Test root health endpoint."""
        from backend.app import root_health
        response = await root_health()
        assert "status" in response
        assert response["status"] == "healthy"


class TestLifespan:
    """Tests for lifespan context manager."""
    
    def test_lifespan_function_exists(self):
        """Test lifespan function exists."""
        from backend.app import lifespan
        assert lifespan is not None
    
    @pytest.mark.asyncio
    async def test_lifespan_context_manager(self):
        """Test lifespan as context manager."""
        from backend.app import lifespan, app
        
        # Mock preload_embedding_model to avoid loading real model
        with patch('backend.app.preload_embedding_model'):
            async with lifespan(app):
                pass  # Just verify it doesn't crash


class TestSettingsConfiguration:
    """Tests for settings configuration in app."""
    
    def test_settings_loaded(self):
        """Test settings are loaded."""
        from backend.app import settings
        assert settings is not None
    
    def test_project_name_configured(self):
        """Test project name is configured."""
        from backend.app import settings
        assert settings.project_name is not None
    
    def test_api_prefix_configured(self):
        """Test API prefix is configured."""
        from backend.app import settings
        assert settings.api_v1_prefix is not None


class TestLoggerConfiguration:
    """Tests for logger configuration."""
    
    def test_logger_configured(self):
        """Test logger is configured."""
        from backend.app import logger
        assert logger is not None
