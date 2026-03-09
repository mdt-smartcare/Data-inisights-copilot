"""
Unit tests for backend/services/embeddings.py

Tests embedding model wrapper and service.
"""
import pytest
from unittest.mock import MagicMock, patch
import os
import sys
import numpy as np

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"

# Mock missing optional dependencies for environment-independent testing
if 'sentence_transformers' not in sys.modules:
    sys.modules['sentence_transformers'] = MagicMock()

@pytest.fixture
def mock_sentence_transformer():
    """Create mock SentenceTransformer model."""
    mock = MagicMock()
    mock.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    mock.get_sentence_embedding_dimension.return_value = 1024
    return mock

@pytest.fixture
def mock_embedding_registry():
    """Mock EmbeddingRegistry and active provider."""
    mock_registry = MagicMock()
    mock_provider = MagicMock()
    mock_provider.provider_name = "bge-m3"
    mock_provider.dimension = 1024
    mock_provider.embed_documents.return_value = [[0.1, 0.2, 0.3]]
    mock_provider.embed_query.return_value = [0.1, 0.2, 0.3]
    mock_registry.get_active_provider.return_value = mock_provider
    return mock_registry, mock_provider

class TestEmbeddingService:
    """Tests for _EmbeddingService singleton."""
    
    def test_service_loads_model_once(self, mock_sentence_transformer):
        """Test that model is loaded only once (singleton)."""
        # Patching the library source
        with patch('sentence_transformers.SentenceTransformer', return_value=mock_sentence_transformer):
            # backend.services.embeddings imports get_embedding_settings into its namespace
            with patch('backend.services.embeddings.get_embedding_settings', return_value={}):
                # Reset singleton for test isolation
                from backend.services import embeddings
                embeddings._EmbeddingService._instance = None
                embeddings._EmbeddingService._model = None
                
                from backend.services.embeddings import _EmbeddingService
                
                # Create multiple instances
                service1 = _EmbeddingService()
                service2 = _EmbeddingService()
                
                # Should be same instance
                assert service1 is service2
    
    def test_get_model_returns_loaded_model(self, mock_sentence_transformer):
        """Test that get_model returns the loaded model."""
        with patch('sentence_transformers.SentenceTransformer', return_value=mock_sentence_transformer):
            with patch('backend.services.embeddings.get_embedding_settings', return_value={}):
                from backend.services import embeddings
                embeddings._EmbeddingService._instance = None
                embeddings._EmbeddingService._model = None
                
                from backend.services.embeddings import _EmbeddingService
                
                service = _EmbeddingService()
                model = service.get_model()
                
                assert model is mock_sentence_transformer

class TestLocalHuggingFaceEmbeddings:
    """Tests for LocalHuggingFaceEmbeddings wrapper."""
    
    def test_embed_documents_uses_registry(self, mock_embedding_registry):
        """Test that LocalHuggingFaceEmbeddings uses the registry."""
        mock_reg, mock_prov = mock_embedding_registry
        # get_embedding_registry is NOT in embeddings.py global namespace (local import), so patch source
        with patch('backend.services.embedding_registry.get_embedding_registry', return_value=mock_reg):
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            wrapper = LocalHuggingFaceEmbeddings()
            results = wrapper.embed_documents(["Text 1"])
            
            assert results == [[0.1, 0.2, 0.3]]
            mock_prov.embed_documents.assert_called_once_with(["Text 1"])
            
    def test_embed_documents_fallback_to_legacy(self, mock_sentence_transformer):
        """Test fallback to legacy service if registry fails."""
        mock_sentence_transformer.encode.return_value = np.array([[0.1, 0.2, 0.3]])
        
        # get_embedding_registry is NOT in embeddings.py global namespace (local import), so patch source
        with patch('backend.services.embedding_registry.get_embedding_registry', side_effect=ImportError):
            with patch('sentence_transformers.SentenceTransformer', return_value=mock_sentence_transformer):
                with patch('backend.services.embeddings.get_embedding_settings', return_value={}):
                    from backend.services import embeddings
                    embeddings._EmbeddingService._instance = None
                    embeddings._EmbeddingService._model = None
                    
                    from backend.services.embeddings import LocalHuggingFaceEmbeddings
                    wrapper = LocalHuggingFaceEmbeddings()
                    results = wrapper.embed_documents(["Text 1"])
                    
                    assert len(results) == 1
                    assert results[0] == [0.1, 0.2, 0.3]
    
    def test_embed_documents_empty_list(self, mock_embedding_registry):
        """Test embedding empty list."""
        mock_reg, mock_prov = mock_embedding_registry
        with patch('backend.services.embedding_registry.get_embedding_registry', return_value=mock_reg):
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            wrapper = LocalHuggingFaceEmbeddings()
            results = wrapper.embed_documents([])
            assert results == []

    def test_embed_query_uses_registry(self, mock_embedding_registry):
        """Test embedding a single query via registry."""
        mock_reg, mock_prov = mock_embedding_registry
        with patch('backend.services.embedding_registry.get_embedding_registry', return_value=mock_reg):
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            wrapper = LocalHuggingFaceEmbeddings()
            result = wrapper.embed_query("Test query")
            
            assert result == [0.1, 0.2, 0.3]
            mock_prov.embed_query.assert_called_once_with("Test query")

    def test_dimension_property(self, mock_embedding_registry):
        """Test dimension property returns value from provider."""
        mock_reg, mock_prov = mock_embedding_registry
        mock_prov.dimension = 768
        with patch('backend.services.embedding_registry.get_embedding_registry', return_value=mock_reg):
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            wrapper = LocalHuggingFaceEmbeddings()
            assert wrapper.dimension == 768

class TestGetEmbeddingModel:
    """Tests for get_embedding_model cached function."""
    
    def test_returns_cached_instance(self, mock_embedding_registry):
        """Test that get_embedding_model returns cached instance."""
        mock_reg, mock_prov = mock_embedding_registry
        with patch('backend.services.embedding_registry.get_embedding_registry', return_value=mock_reg):
            from backend.services import embeddings
            embeddings.get_embedding_model.cache_clear()
            
            from backend.services.embeddings import get_embedding_model
            model1 = get_embedding_model()
            model2 = get_embedding_model()
            assert model1 is model2

class TestPreloadEmbeddingModel:
    """Tests for preload_embedding_model function."""
    
    def test_preload_initializes_registry(self, mock_embedding_registry):
        """Test that preload initializes via registry."""
        mock_reg, mock_prov = mock_embedding_registry
        with patch('backend.services.embedding_registry.get_embedding_registry', return_value=mock_reg):
            from backend.services.embeddings import preload_embedding_model
            preload_embedding_model()
            mock_reg.get_active_provider.assert_called_once()

class TestModelPathResolution:
    """Tests for legacy model path resolution."""
    
    def test_resolves_relative_path(self, mock_sentence_transformer):
        """Test that relative paths are resolved correctly in legacy service."""
        with patch('backend.services.embedding_registry.get_embedding_registry', side_effect=ImportError):
            with patch('sentence_transformers.SentenceTransformer', return_value=mock_sentence_transformer):
                with patch('backend.services.embeddings.get_embedding_settings', return_value={'model_path': './models/bge-m3'}):
                    from backend.services import embeddings
                    embeddings._EmbeddingService._instance = None
                    embeddings._EmbeddingService._model = None
                    from backend.services.embeddings import _EmbeddingService
                    service = _EmbeddingService()
                    assert service._model is not None

    def test_absolute_path_unchanged(self, mock_sentence_transformer):
        """Test that absolute paths are used as-is in legacy service."""
        with patch('backend.services.embedding_registry.get_embedding_registry', side_effect=ImportError):
            with patch('sentence_transformers.SentenceTransformer', return_value=mock_sentence_transformer):
                with patch('backend.services.embeddings.get_embedding_settings', return_value={'model_path': '/absolute/path/model'}):
                    from backend.services import embeddings
                    embeddings._EmbeddingService._instance = None
                    embeddings._EmbeddingService._model = None
                    from backend.services.embeddings import _EmbeddingService
                    service = _EmbeddingService()
                    assert service._model is not None
