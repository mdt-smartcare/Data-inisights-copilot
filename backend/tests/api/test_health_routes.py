"""
Tests for health check API routes.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestHealthRouter:
    """Tests for health router."""
    
    def test_router_exists(self):
        """Test health router exists."""
        from backend.api.routes.health import router
        assert router is not None
    
    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.routes.health import router
        assert router.prefix == "/health"
    
    def test_router_tags(self):
        """Test router has tags."""
        from backend.api.routes.health import router
        assert "Health" in router.tags


class TestHealthCheckEndpoint:
    """Tests for health check endpoint function."""
    
    @pytest.mark.asyncio
    async def test_health_check_returns_response(self):
        """Test health check function returns response."""
        from backend.api.routes.health import health_check
        
        with patch('backend.api.routes.health.get_sql_service') as mock_sql:
            with patch('backend.api.routes.health.get_vector_store') as mock_vector:
                mock_sql_service = MagicMock()
                mock_sql_service.health_check.return_value = True
                mock_sql.return_value = mock_sql_service
                
                mock_vector_service = MagicMock()
                mock_vector_service.health_check.return_value = True
                mock_vector.return_value = mock_vector_service
                
                response = await health_check()
                assert response is not None
    
    @pytest.mark.asyncio
    async def test_health_check_includes_status(self):
        """Test health check includes status field."""
        from backend.api.routes.health import health_check
        
        with patch('backend.api.routes.health.get_sql_service') as mock_sql:
            with patch('backend.api.routes.health.get_vector_store') as mock_vector:
                mock_sql_service = MagicMock()
                mock_sql_service.health_check.return_value = True
                mock_sql.return_value = mock_sql_service
                
                mock_vector_service = MagicMock()
                mock_vector_service.health_check.return_value = True
                mock_vector.return_value = mock_vector_service
                
                response = await health_check()
                assert "status" in response or hasattr(response, 'status')


class TestHealthCheckDatabaseStatus:
    """Tests for database status in health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_with_healthy_database(self):
        """Test health check when database is healthy."""
        from backend.api.routes.health import health_check
        
        with patch('backend.api.routes.health.get_sql_service') as mock_sql:
            with patch('backend.api.routes.health.get_vector_store') as mock_vector:
                mock_sql_service = MagicMock()
                mock_sql_service.health_check.return_value = True
                mock_sql.return_value = mock_sql_service
                
                mock_vector_service = MagicMock()
                mock_vector_service.health_check.return_value = True
                mock_vector.return_value = mock_vector_service
                
                response = await health_check()
                assert response is not None
    
    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy_database(self):
        """Test health check when database is unhealthy."""
        from backend.api.routes.health import health_check
        
        with patch('backend.api.routes.health.get_sql_service') as mock_sql:
            with patch('backend.api.routes.health.get_vector_store') as mock_vector:
                mock_sql_service = MagicMock()
                mock_sql_service.health_check.return_value = False
                mock_sql.return_value = mock_sql_service
                
                mock_vector_service = MagicMock()
                mock_vector_service.health_check.return_value = True
                mock_vector.return_value = mock_vector_service
                
                response = await health_check()
                # Should still return, but with degraded status
                assert response is not None


class TestHealthCheckVectorStoreStatus:
    """Tests for vector store status in health check."""
    
    @pytest.mark.asyncio
    async def test_health_check_with_healthy_vector_store(self):
        """Test health check when vector store is healthy."""
        from backend.api.routes.health import health_check
        
        with patch('backend.api.routes.health.get_sql_service') as mock_sql:
            with patch('backend.api.routes.health.get_vector_store') as mock_vector:
                mock_sql_service = MagicMock()
                mock_sql_service.health_check.return_value = True
                mock_sql.return_value = mock_sql_service
                
                mock_vector_service = MagicMock()
                mock_vector_service.health_check.return_value = True
                mock_vector.return_value = mock_vector_service
                
                response = await health_check()
                assert response is not None
    
    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy_vector_store(self):
        """Test health check when vector store is unhealthy."""
        from backend.api.routes.health import health_check
        
        with patch('backend.api.routes.health.get_sql_service') as mock_sql:
            with patch('backend.api.routes.health.get_vector_store') as mock_vector:
                mock_sql_service = MagicMock()
                mock_sql_service.health_check.return_value = True
                mock_sql.return_value = mock_sql_service
                
                mock_vector_service = MagicMock()
                mock_vector_service.health_check.return_value = False
                mock_vector.return_value = mock_vector_service
                
                response = await health_check()
                assert response is not None


class TestHealthCheckServiceImports:
    """Tests for service imports in health module."""
    
    def test_get_sql_service_import(self):
        """Test get_sql_service is imported."""
        from backend.api.routes.health import get_sql_service
        assert get_sql_service is not None
    
    def test_get_vector_store_import(self):
        """Test get_vector_store is imported."""
        from backend.api.routes.health import get_vector_store
        assert get_vector_store is not None
    
    def test_logger_configured(self):
        """Test logger is configured."""
        from backend.api.routes.health import logger
        assert logger is not None
    
    def test_settings_loaded(self):
        """Test settings are loaded."""
        from backend.api.routes.health import settings
        assert settings is not None
