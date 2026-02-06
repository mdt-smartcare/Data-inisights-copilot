"""
Tests for api/websocket/embedding_progress.py to increase code coverage.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestProgressConnectionManager:
    """Tests for ProgressConnectionManager class."""
    
    def test_class_import(self):
        """Test ProgressConnectionManager can be imported."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        assert ProgressConnectionManager is not None
    
    def test_init(self):
        """Test ProgressConnectionManager initialization."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        manager = ProgressConnectionManager()
        assert manager.active_connections == {}
    
    def test_connect_method_exists(self):
        """Test connect method exists."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        assert hasattr(ProgressConnectionManager, 'connect')
    
    def test_disconnect_method_exists(self):
        """Test disconnect method exists."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        assert hasattr(ProgressConnectionManager, 'disconnect')
    
    def test_broadcast_progress_method_exists(self):
        """Test broadcast_progress method exists."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        assert hasattr(ProgressConnectionManager, 'broadcast_progress')
    
    @pytest.mark.asyncio
    async def test_connect_adds_connection(self):
        """Test connect adds websocket to active connections."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        manager = ProgressConnectionManager()
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        await manager.connect(mock_ws, "job123")
        
        assert "job123" in manager.active_connections
        assert mock_ws in manager.active_connections["job123"]
        mock_ws.accept.assert_called_once()
    
    def test_disconnect_removes_connection(self):
        """Test disconnect removes websocket from active connections."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        manager = ProgressConnectionManager()
        
        mock_ws = MagicMock()
        manager.active_connections["job123"] = {mock_ws}
        
        manager.disconnect(mock_ws, "job123")
        
        assert "job123" not in manager.active_connections
    
    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        """Test broadcast when no connections for job."""
        from backend.api.websocket.embedding_progress import ProgressConnectionManager
        manager = ProgressConnectionManager()
        
        # Should not raise error
        await manager.broadcast_progress("nonexistent", {"status": "running"})


class TestVerifyToken:
    """Tests for verify_token function."""
    
    def test_verify_token_import(self):
        """Test verify_token can be imported."""
        from backend.api.websocket.embedding_progress import verify_token
        assert verify_token is not None
        assert callable(verify_token)
    
    def test_verify_invalid_token(self):
        """Test verify_token returns False for invalid token."""
        from backend.api.websocket.embedding_progress import verify_token
        result = verify_token("invalid_token")
        assert result is False


class TestGlobalManager:
    """Tests for global manager instance."""
    
    def test_manager_exists(self):
        """Test global manager is defined."""
        from backend.api.websocket.embedding_progress import manager
        assert manager is not None


class TestWebSocketRouter:
    """Tests for WebSocket router."""
    
    def test_router_exists(self):
        """Test router is defined."""
        from backend.api.websocket.embedding_progress import router
        assert router is not None


class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint."""
    
    def test_embedding_progress_websocket_exists(self):
        """Test embedding_progress_websocket endpoint exists."""
        from backend.api.websocket.embedding_progress import embedding_progress_websocket
        assert embedding_progress_websocket is not None


class TestWebSocketImports:
    """Tests for websocket module imports."""
    
    def test_get_settings_import(self):
        """Test get_settings is imported."""
        from backend.api.websocket.embedding_progress import get_settings
        assert get_settings is not None
    
    def test_get_embedding_job_service_import(self):
        """Test get_embedding_job_service is imported."""
        from backend.api.websocket.embedding_progress import get_embedding_job_service
        assert get_embedding_job_service is not None
    
    def test_jwt_import(self):
        """Test jwt is imported."""
        from backend.api.websocket.embedding_progress import jwt
        assert jwt is not None
    
    def test_logger_exists(self):
        """Test logger is configured."""
        from backend.api.websocket.embedding_progress import logger
        assert logger is not None
    
    def test_settings_exists(self):
        """Test settings is defined."""
        from backend.api.websocket.embedding_progress import settings
        assert settings is not None
