"""
Tests for the tracing module (Langfuse integration).

These tests verify:
1. TracingManager singleton initialization
2. LangChain callback handler creation with proper parameters
3. Trace metadata updates (user_id, session_id)
4. Decorator functionality
"""
import pytest
from unittest.mock import MagicMock, patch
import backend.core.tracing as tracing


class TestTracingManager:
    """Tests for TracingManager class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for tracing tests."""
        with patch('backend.core.tracing.get_settings') as mock:
            settings = MagicMock()
            settings.enable_langfuse = True
            settings.langfuse_public_key = "pk-test-key"
            settings.langfuse_secret_key = "sk-test-key"
            settings.langfuse_host = "http://localhost:3000"
            mock.return_value = settings
            yield settings
    
    @pytest.fixture
    def mock_langfuse(self):
        """Mock Langfuse client."""
        with patch('backend.core.tracing.Langfuse') as mock_class:
            mock_instance = MagicMock()
            mock_instance.auth_check.return_value = True
            mock_class.return_value = mock_instance
            yield mock_instance
    
    @pytest.fixture
    def fresh_tracing_manager(self, mock_settings, mock_langfuse):
        """Get a fresh TracingManager instance (reset singleton)."""
        from backend.core.tracing import TracingManager
        # Reset singleton
        TracingManager._instance = None
        manager = TracingManager()
        return manager
    
    def test_singleton_pattern(self, fresh_tracing_manager):
        """Verify TracingManager is a singleton."""
        from backend.core.tracing import TracingManager
        manager1 = fresh_tracing_manager
        manager2 = TracingManager()
        assert manager1 is manager2
    
    def test_langfuse_initialization_success(self, fresh_tracing_manager, mock_langfuse):
        """Test successful Langfuse initialization."""
        manager = fresh_tracing_manager
        assert manager.langfuse_enabled is True
        assert manager.langfuse is not None
        mock_langfuse.auth_check.assert_called_once()
    
    def test_langfuse_initialization_auth_failure(self, mock_settings):
        """Test Langfuse disabled on auth failure."""
        with patch('backend.core.tracing.Langfuse') as mock_class:
            mock_instance = MagicMock()
            mock_instance.auth_check.return_value = False
            mock_class.return_value = mock_instance
            
            from backend.core.tracing import TracingManager
            TracingManager._instance = None
            manager = TracingManager()
            
            assert manager.langfuse_enabled is False
    
    def test_langfuse_disabled_by_setting(self):
        """Test Langfuse not initialized when disabled in settings."""
        with patch.object(tracing, 'settings') as mock_settings:
            mock_settings.enable_langfuse = False
            mock_settings.langfuse_public_key = ""
            mock_settings.langfuse_secret_key = ""
            mock_settings.langfuse_host = ""
            
            from backend.core.tracing import TracingManager
            TracingManager._instance = None
            manager = TracingManager()
            
            assert manager.langfuse_enabled is False
            assert manager.langfuse is None


class TestLangChainCallback:
    """Tests for LangChain callback handler creation."""
    
    @pytest.fixture
    def tracing_manager(self):
        """Get a mocked TracingManager."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = True
            settings.langfuse_public_key = "pk-test"
            settings.langfuse_secret_key = "sk-test"
            settings.langfuse_host = "http://localhost:3000"
            mock_settings.return_value = settings
            
            with patch('backend.core.tracing.Langfuse') as mock_langfuse:
                mock_instance = MagicMock()
                mock_instance.auth_check.return_value = True
                mock_langfuse.return_value = mock_instance
                
                from backend.core.tracing import TracingManager
                TracingManager._instance = None
                manager = TracingManager()
                yield manager
    
    def test_callback_handler_creation(self, tracing_manager):
        """Test LangChain callback handler is created with correct params."""
        with patch('backend.core.tracing.LangfuseCallbackHandler') as mock_handler:
            mock_handler.return_value = MagicMock()
            
            handler = tracing_manager.get_langchain_callback(
                trace_id="test-trace-123",
                session_id="session-456",
                user_id="user-789",
                trace_name="test_operation"
            )
            
            # Verify handler was created
            assert handler is not None
            mock_handler.assert_called_once()
            
            # Check that trace_context was passed
            call_kwargs = mock_handler.call_args.kwargs
            assert "trace_context" in call_kwargs
            assert call_kwargs["trace_context"]["trace_id"] == "test-trace-123"
            assert call_kwargs["update_trace"] is True
    
    def test_callback_handler_stores_metadata(self, tracing_manager):
        """Test that user_id and session_id are stored for reference."""
        with patch('backend.core.tracing.LangfuseCallbackHandler') as mock_handler:
            mock_instance = MagicMock()
            mock_handler.return_value = mock_instance
            
            handler = tracing_manager.get_langchain_callback(
                trace_id="trace-1",
                session_id="session-abc",
                user_id="user-xyz",
                trace_name="my_trace"
            )
            
            # Verify metadata stored on handler for debugging
            assert handler._session_id == "session-abc"
            assert handler._user_id == "user-xyz"
            assert handler._trace_name == "my_trace"
    
    def test_callback_returns_none_when_disabled(self):
        """Test that None is returned when Langfuse is disabled."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = False
            mock_settings.return_value = settings
            
            from backend.core.tracing import TracingManager
            TracingManager._instance = None
            manager = TracingManager()
            
            handler = manager.get_langchain_callback(
                trace_id="test",
                session_id="session",
                user_id="user"
            )
            
            assert handler is None


class TestTraceMetadataUpdate:
    """Tests for trace metadata update functionality."""
    
    @pytest.fixture
    def tracing_manager_with_langfuse(self):
        """Get TracingManager with mocked Langfuse client."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = True
            settings.langfuse_public_key = "pk-test"
            settings.langfuse_secret_key = "sk-test"
            settings.langfuse_host = "http://localhost:3000"
            mock_settings.return_value = settings
            
            with patch('backend.core.tracing.Langfuse') as mock_langfuse_class:
                mock_langfuse = MagicMock()
                mock_langfuse.auth_check.return_value = True
                mock_langfuse_class.return_value = mock_langfuse
                
                from backend.core.tracing import TracingManager
                TracingManager._instance = None
                manager = TracingManager()
                yield manager, mock_langfuse
    
    def test_update_current_trace_metadata(self, tracing_manager_with_langfuse):
        """Test updating current trace with user_id, session_id, etc."""
        manager, mock_langfuse = tracing_manager_with_langfuse
        
        manager.update_current_trace_metadata(
            name="rag_query",
            session_id="session-123",
            user_id="user-456",
            metadata={"query_length": 50},
            tags=["test", "rag"]
        )
        
        mock_langfuse.update_current_trace.assert_called_once_with(
            name="rag_query",
            session_id="session-123",
            user_id="user-456",
            metadata={"query_length": 50},
            tags=["test", "rag"]
        )
    
    def test_update_trace_handles_exception(self, tracing_manager_with_langfuse):
        """Test that exceptions during trace update are handled gracefully."""
        manager, mock_langfuse = tracing_manager_with_langfuse
        mock_langfuse.update_current_trace.side_effect = Exception("API error")
        
        # Should not raise
        manager.update_current_trace_metadata(
            name="test",
            user_id="user"
        )


class TestCreateTrace:
    """Tests for manual trace creation."""
    
    @pytest.fixture
    def tracing_manager_with_langfuse(self):
        """Get TracingManager with mocked Langfuse client."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = True
            settings.langfuse_public_key = "pk-test"
            settings.langfuse_secret_key = "sk-test"
            settings.langfuse_host = "http://localhost:3000"
            mock_settings.return_value = settings
            
            with patch('backend.core.tracing.Langfuse') as mock_langfuse_class:
                mock_langfuse = MagicMock()
                mock_langfuse.auth_check.return_value = True
                mock_langfuse_class.return_value = mock_langfuse
                
                from backend.core.tracing import TracingManager
                TracingManager._instance = None
                manager = TracingManager()
                yield manager, mock_langfuse
    
    def test_create_trace_with_all_params(self, tracing_manager_with_langfuse):
        """Test creating a trace with all parameters."""
        manager, mock_langfuse = tracing_manager_with_langfuse
        mock_trace = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        
        trace = manager.create_trace(
            name="custom_operation",
            input={"query": "test query"},
            user_id="user-123",
            session_id="session-456",
            metadata={"source": "api"},
            tags=["custom"]
        )
        
        assert trace is mock_trace
        mock_langfuse.trace.assert_called_once_with(
            name="custom_operation",
            input={"query": "test query"},
            user_id="user-123",
            session_id="session-456",
            metadata={"source": "api"},
            tags=["custom"]
        )
    
    def test_create_trace_returns_none_when_disabled(self):
        """Test that create_trace returns None when Langfuse is disabled."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = False
            mock_settings.return_value = settings
            
            from backend.core.tracing import TracingManager
            TracingManager._instance = None
            manager = TracingManager()
            
            trace = manager.create_trace(name="test")
            assert trace is None


class TestTraceOperationContextManager:
    """Tests for the trace_operation context manager."""
    
    @pytest.fixture
    def tracing_manager_with_langfuse(self):
        """Get TracingManager with mocked Langfuse client."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = True
            settings.langfuse_public_key = "pk-test"
            settings.langfuse_secret_key = "sk-test"
            settings.langfuse_host = "http://localhost:3000"
            mock_settings.return_value = settings
            
            with patch('backend.core.tracing.Langfuse') as mock_langfuse_class:
                mock_langfuse = MagicMock()
                mock_langfuse.auth_check.return_value = True
                mock_langfuse_class.return_value = mock_langfuse
                
                from backend.core.tracing import TracingManager
                TracingManager._instance = None
                manager = TracingManager()
                yield manager, mock_langfuse
    
    def test_trace_operation_creates_and_flushes(self, tracing_manager_with_langfuse):
        """Test that trace_operation creates trace and flushes on exit."""
        manager, mock_langfuse = tracing_manager_with_langfuse
        mock_trace = MagicMock()
        mock_trace.id = "trace-id-123"
        mock_langfuse.trace.return_value = mock_trace
        
        with manager.trace_operation(
            name="test_op",
            input="test input",
            user_id="user-1",
            session_id="session-1"
        ) as trace:
            assert trace is mock_trace
        
        # Verify trace was created
        mock_langfuse.trace.assert_called_once()
        
        # Verify flush was called
        mock_langfuse.flush.assert_called_once()
    
    def test_trace_operation_handles_exception(self, tracing_manager_with_langfuse):
        """Test that trace_operation updates trace on exception."""
        manager, mock_langfuse = tracing_manager_with_langfuse
        mock_trace = MagicMock()
        mock_langfuse.trace.return_value = mock_trace
        
        with pytest.raises(ValueError, match="test error"):
            with manager.trace_operation(name="failing_op"):
                raise ValueError("test error")
        
        # Verify trace was updated with error
        mock_trace.update.assert_called_once()
        call_kwargs = mock_trace.update.call_args.kwargs
        assert call_kwargs["level"] == "ERROR"
        assert "test error" in call_kwargs["status_message"]


class TestFlush:
    """Tests for the flush method."""
    
    def test_flush_calls_langfuse_flush(self):
        """Test that flush calls Langfuse flush."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = True
            settings.langfuse_public_key = "pk-test"
            settings.langfuse_secret_key = "sk-test"
            settings.langfuse_host = "http://localhost:3000"
            mock_settings.return_value = settings
            
            with patch('backend.core.tracing.Langfuse') as mock_langfuse_class:
                mock_langfuse = MagicMock()
                mock_langfuse.auth_check.return_value = True
                mock_langfuse_class.return_value = mock_langfuse
                
                from backend.core.tracing import TracingManager
                TracingManager._instance = None
                manager = TracingManager()
                
                manager.flush()
                mock_langfuse.flush.assert_called_once()


class TestGetTracingManager:
    """Tests for the get_tracing_manager function."""
    
    def test_get_tracing_manager_returns_singleton(self):
        """Test that get_tracing_manager returns the singleton instance."""
        with patch('backend.core.tracing.get_settings') as mock_settings:
            settings = MagicMock()
            settings.enable_langfuse = False
            mock_settings.return_value = settings
            
            from backend.core.tracing import TracingManager, get_tracing_manager
            TracingManager._instance = None
            
            manager1 = get_tracing_manager()
            manager2 = get_tracing_manager()
            
            assert manager1 is manager2
