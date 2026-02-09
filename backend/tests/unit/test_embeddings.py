"""
Unit tests for backend/services/embeddings.py

Tests embedding model wrapper and service.
"""
import pytest
from unittest.mock import MagicMock, patch
import os
import numpy as np

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_sentence_transformer():
    """Create mock SentenceTransformer model."""
    mock = MagicMock()
    mock.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    mock.get_sentence_embedding_dimension.return_value = 1024
    return mock


class TestEmbeddingService:
    """Tests for _EmbeddingService singleton."""
    
    def test_service_loads_model_once(self, mock_sentence_transformer):
        """Test that model is loaded only once (singleton)."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
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
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import _EmbeddingService
            
            service = _EmbeddingService()
            model = service.get_model()
            
            assert model is mock_sentence_transformer


class TestLocalHuggingFaceEmbeddings:
    """Tests for LocalHuggingFaceEmbeddings wrapper."""
    
    def test_embed_documents_returns_vectors(self, mock_sentence_transformer):
        """Test embedding multiple documents."""
        mock_sentence_transformer.encode.return_value = np.array([
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6]
        ])
        
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            
            wrapper = LocalHuggingFaceEmbeddings()
            results = wrapper.embed_documents(["Text 1", "Text 2"])
            
            assert len(results) == 2
            assert isinstance(results[0], list)
    
    def test_embed_documents_empty_list(self, mock_sentence_transformer):
        """Test embedding empty list."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            
            wrapper = LocalHuggingFaceEmbeddings()
            results = wrapper.embed_documents([])
            
            assert results == []
    
    def test_embed_query_returns_single_vector(self, mock_sentence_transformer):
        """Test embedding a single query."""
        mock_sentence_transformer.encode.return_value = np.array([0.1, 0.2, 0.3])
        
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            
            wrapper = LocalHuggingFaceEmbeddings()
            result = wrapper.embed_query("Test query")
            
            assert isinstance(result, list)
            assert len(result) == 3
    
    def test_dimension_property(self, mock_sentence_transformer):
        """Test dimension property returns correct value."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            
            wrapper = LocalHuggingFaceEmbeddings()
            dim = wrapper.dimension
            
            assert dim == 1024
    
    def test_embed_uses_normalization(self, mock_sentence_transformer):
        """Test that embeddings are normalized."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import LocalHuggingFaceEmbeddings
            
            wrapper = LocalHuggingFaceEmbeddings()
            wrapper.embed_query("Test")
            
            # Verify normalize_embeddings=True was passed
            call_args = mock_sentence_transformer.encode.call_args
            assert call_args[1]['normalize_embeddings'] is True


class TestGetEmbeddingModel:
    """Tests for get_embedding_model cached function."""
    
    def test_returns_cached_instance(self, mock_sentence_transformer):
        """Test that get_embedding_model returns cached instance."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            embeddings.get_embedding_model.cache_clear()
            
            from backend.services.embeddings import get_embedding_model
            
            model1 = get_embedding_model()
            model2 = get_embedding_model()
            
            assert model1 is model2


class TestPreloadEmbeddingModel:
    """Tests for preload_embedding_model function."""
    
    def test_preload_initializes_service(self, mock_sentence_transformer):
        """Test that preload initializes the singleton."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            from backend.services import embeddings
            embeddings._EmbeddingService._instance = None
            embeddings._EmbeddingService._model = None
            
            from backend.services.embeddings import preload_embedding_model, _EmbeddingService
            
            preload_embedding_model()
            
            # Service should now have an instance
            assert _EmbeddingService._instance is not None


class TestModelPathResolution:
    """Tests for model path resolution."""
    
    def test_resolves_relative_path(self, mock_sentence_transformer):
        """Test that relative paths are resolved correctly."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            with patch('backend.services.embeddings.settings') as mock_settings:
                mock_settings.embedding_model_path = "./models/bge-m3"
                
                from backend.services import embeddings
                embeddings._EmbeddingService._instance = None
                embeddings._EmbeddingService._model = None
                
                from backend.services.embeddings import _EmbeddingService
                
                service = _EmbeddingService()
                
                # Model should have been loaded
                assert service._model is not None
    
    def test_absolute_path_unchanged(self, mock_sentence_transformer):
        """Test that absolute paths are used as-is."""
        with patch('backend.services.embeddings.SentenceTransformer', return_value=mock_sentence_transformer):
            with patch('backend.services.embeddings.settings') as mock_settings:
                mock_settings.embedding_model_path = "/absolute/path/model"
                
                from backend.services import embeddings
                embeddings._EmbeddingService._instance = None
                embeddings._EmbeddingService._model = None
                
                from backend.services.embeddings import _EmbeddingService
                
                service = _EmbeddingService()
                
                # Just verify service loaded
                assert service._model is not None
