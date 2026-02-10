"""
Tests for observability API routes.

Tests cover:
- GET /observability/config - Get observability settings
- PUT /observability/config - Update observability settings  
- GET /observability/usage - Get usage statistics
- POST /observability/test-log - Emit test log message
"""
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestObservabilityRouter:
    """Tests for observability router configuration."""
    
    def test_router_exists(self):
        """Test observability router exists."""
        from backend.api.routes.observability import router
        assert router is not None
    
    def test_router_prefix(self):
        """Test router has correct prefix."""
        from backend.api.routes.observability import router
        assert router.prefix == "/observability"
    
    def test_router_tags(self):
        """Test router has tags."""
        from backend.api.routes.observability import router
        assert "observability" in router.tags


class TestObservabilityConfigUpdate:
    """Tests for ObservabilityConfigUpdate model."""
    
    def test_model_exists(self):
        """Test model can be imported."""
        from backend.api.routes.observability import ObservabilityConfigUpdate
        assert ObservabilityConfigUpdate is not None
    
    def test_model_fields(self):
        """Test model has expected optional fields."""
        from backend.api.routes.observability import ObservabilityConfigUpdate
        
        # All fields should be optional
        config = ObservabilityConfigUpdate()
        assert config.log_level is None
        assert config.langfuse_enabled is None
        assert config.tracing_provider is None
        assert config.trace_sample_rate is None
        assert config.log_destinations is None
    
    def test_model_with_values(self):
        """Test model accepts values."""
        from backend.api.routes.observability import ObservabilityConfigUpdate
        
        config = ObservabilityConfigUpdate(
            log_level="DEBUG",
            langfuse_enabled=True,
            tracing_provider="langfuse",
            trace_sample_rate=0.5,
            log_destinations=["console", "file"]
        )
        
        assert config.log_level == "DEBUG"
        assert config.langfuse_enabled is True
        assert config.tracing_provider == "langfuse"
        assert config.trace_sample_rate == 0.5
        assert config.log_destinations == ["console", "file"]


class TestGetObservabilityConfigEndpoint:
    """Tests for GET /observability/config endpoint."""
    
    def test_function_exists(self):
        """Test get_observability_config function exists."""
        from backend.api.routes.observability import get_observability_config
        assert get_observability_config is not None
    
    @pytest.mark.asyncio
    async def test_get_config_returns_dict(self):
        """Test get_config returns configuration dictionary."""
        from backend.api.routes.observability import get_observability_config
        
        # Mock service
        mock_service = MagicMock()
        mock_service.get_config = AsyncMock(return_value={
            "log_level": "INFO",
            "langfuse_enabled": False,
            "tracing_provider": "none",
            "trace_sample_rate": 1.0,
            "log_destinations": ["console"]
        })
        
        # Mock user (super admin required)
        mock_user = MagicMock()
        mock_user.role = "super_admin"
        
        result = await get_observability_config(
            service=mock_service,
            current_user=mock_user
        )
        
        assert "log_level" in result
        assert "tracing_provider" in result
        mock_service.get_config.assert_called_once()


class TestUpdateObservabilityConfigEndpoint:
    """Tests for PUT /observability/config endpoint."""
    
    def test_function_exists(self):
        """Test update_observability_config function exists."""
        from backend.api.routes.observability import update_observability_config
        assert update_observability_config is not None
    
    @pytest.mark.asyncio
    async def test_update_config_success(self):
        """Test successful config update."""
        from backend.api.routes.observability import update_observability_config
        
        # Mock service
        mock_service = MagicMock()
        mock_service.update_config = AsyncMock(return_value={
            "success": True,
            "log_level": "DEBUG"
        })
        
        # Mock user
        mock_user = MagicMock()
        mock_user.role = "super_admin"
        
        updates = {"log_level": "DEBUG"}
        
        result = await update_observability_config(
            updates=updates,
            service=mock_service,
            current_user=mock_user
        )
        
        assert result["success"] is True
        mock_service.update_config.assert_called_once_with(updates)
    
    @pytest.mark.asyncio
    async def test_update_config_failure_raises_500(self):
        """Test config update failure raises HTTPException."""
        from backend.api.routes.observability import update_observability_config
        from fastapi import HTTPException
        
        # Mock service that raises exception
        mock_service = MagicMock()
        mock_service.update_config = AsyncMock(side_effect=Exception("Database error"))
        
        # Mock user
        mock_user = MagicMock()
        mock_user.role = "super_admin"
        
        with pytest.raises(HTTPException) as exc_info:
            await update_observability_config(
                updates={"log_level": "DEBUG"},
                service=mock_service,
                current_user=mock_user
            )
        
        assert exc_info.value.status_code == 500
        assert "Failed to update config" in str(exc_info.value.detail)


class TestGetUsageStatisticsEndpoint:
    """Tests for GET /observability/usage endpoint."""
    
    def test_function_exists(self):
        """Test get_usage_statistics function exists."""
        from backend.api.routes.observability import get_usage_statistics
        assert get_usage_statistics is not None
    
    @pytest.mark.asyncio
    async def test_get_usage_default_period(self):
        """Test get usage with default 24h period."""
        from backend.api.routes.observability import get_usage_statistics
        
        # Mock service
        mock_service = MagicMock()
        mock_service.get_usage_stats = AsyncMock(return_value={
            "period": "24h",
            "total_llm_calls": 100,
            "total_tokens": 50000,
            "estimated_cost_usd": 2.50,
            "avg_latency_ms": 1200
        })
        
        # Mock user
        mock_user = MagicMock()
        mock_user.role = "super_admin"
        
        result = await get_usage_statistics(
            period="24h",
            service=mock_service,
            current_user=mock_user
        )
        
        assert result["period"] == "24h"
        assert "total_llm_calls" in result
        assert "total_tokens" in result
        assert "estimated_cost_usd" in result
        mock_service.get_usage_stats.assert_called_once_with("24h")
    
    @pytest.mark.asyncio
    async def test_get_usage_different_periods(self):
        """Test get usage with different time periods."""
        from backend.api.routes.observability import get_usage_statistics
        
        periods = ["1h", "24h", "7d", "30d"]
        
        for period in periods:
            mock_service = MagicMock()
            mock_service.get_usage_stats = AsyncMock(return_value={"period": period})
            
            mock_user = MagicMock()
            mock_user.role = "super_admin"
            
            result = await get_usage_statistics(
                period=period,
                service=mock_service,
                current_user=mock_user
            )
            
            assert result["period"] == period


class TestTestLogEmissionEndpoint:
    """Tests for POST /observability/test-log endpoint."""
    
    def test_function_exists(self):
        """Test test_log_emission function exists."""
        from backend.api.routes.observability import test_log_emission
        assert test_log_emission is not None
    
    @pytest.mark.asyncio
    async def test_emit_info_log(self):
        """Test emitting INFO level log."""
        from backend.api.routes.observability import test_log_emission
        
        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.role = "super_admin"
        
        result = await test_log_emission(
            level="INFO",
            message="Test message",
            current_user=mock_user
        )
        
        assert result["status"] == "success"
        assert result["level"] == "INFO"
        assert result["message"] == "Test message"
    
    @pytest.mark.asyncio
    async def test_emit_different_log_levels(self):
        """Test emitting logs at different levels."""
        from backend.api.routes.observability import test_log_emission
        
        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.role = "super_admin"
        
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        for level in levels:
            result = await test_log_emission(
                level=level,
                message=f"Test {level} message",
                current_user=mock_user
            )
            
            assert result["status"] == "success"
            assert result["level"] == level


class TestObservabilityImports:
    """Tests for observability module imports."""
    
    def test_observability_service_import(self):
        """Test ObservabilityService is imported."""
        from backend.api.routes.observability import ObservabilityService
        assert ObservabilityService is not None
    
    def test_get_observability_service_import(self):
        """Test get_observability_service is imported."""
        from backend.api.routes.observability import get_observability_service
        assert get_observability_service is not None
    
    def test_require_super_admin_import(self):
        """Test require_super_admin is imported."""
        from backend.api.routes.observability import require_super_admin
        assert require_super_admin is not None


class TestObservabilityServiceIntegration:
    """Integration tests for observability service."""
    
    def test_service_singleton(self):
        """Test observability service is a singleton."""
        from backend.services.observability_service import get_observability_service
        
        service1 = get_observability_service()
        service2 = get_observability_service()
        
        # Should be the same instance
        assert service1 is service2
    
    def test_service_has_required_methods(self):
        """Test service has all required methods."""
        from backend.services.observability_service import ObservabilityService
        
        # Check required methods exist
        assert hasattr(ObservabilityService, 'get_config')
        assert hasattr(ObservabilityService, 'update_config')
        assert hasattr(ObservabilityService, 'get_usage_stats')


class TestTracingManagerIntegration:
    """Integration tests for tracing manager."""
    
    def test_tracing_manager_singleton(self):
        """Test tracing manager is a singleton."""
        from backend.core.tracing import get_tracing_manager
        
        manager1 = get_tracing_manager()
        manager2 = get_tracing_manager()
        
        assert manager1 is manager2
    
    def test_tracing_manager_has_langchain_callback(self):
        """Test tracing manager has get_langchain_callback method."""
        from backend.core.tracing import TracingManager
        
        assert hasattr(TracingManager, 'get_langchain_callback')
    
    def test_observe_decorator_available(self):
        """Test @observe decorator is available for use."""
        try:
            from langfuse import observe
            assert observe is not None
        except ImportError:
            pytest.skip("langfuse not installed")


class TestLLMRegistryLangfuseIntegration:
    """Tests for LLM Registry Langfuse callback integration."""
    
    def test_get_langchain_llm_has_tracing_param(self):
        """Test get_langchain_llm accepts with_tracing parameter."""
        from backend.services.llm_registry import LLMRegistry
        import inspect
        
        sig = inspect.signature(LLMRegistry.get_langchain_llm)
        params = list(sig.parameters.keys())
        
        assert 'with_tracing' in params
    
    def test_get_langfuse_callback_method_exists(self):
        """Test get_langfuse_callback method exists."""
        from backend.services.llm_registry import LLMRegistry
        
        assert hasattr(LLMRegistry, 'get_langfuse_callback')
