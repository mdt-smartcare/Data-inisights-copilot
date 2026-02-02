"""
Tests for embedding batch processor.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestBatchResult:
    """Tests for BatchResult dataclass."""
    
    def test_batch_result_creation(self):
        """Test BatchResult can be created."""
        from backend.services.embedding_batch_processor import BatchResult
        
        result = BatchResult(
            batch_number=1,
            success=True,
            documents_processed=10
        )
        assert result.batch_number == 1
        assert result.success is True
        assert result.documents_processed == 10
    
    def test_batch_result_with_embeddings(self):
        """Test BatchResult with embeddings."""
        from backend.services.embedding_batch_processor import BatchResult
        
        result = BatchResult(
            batch_number=1,
            success=True,
            documents_processed=2,
            embeddings=[[0.1, 0.2], [0.3, 0.4]]
        )
        assert result.embeddings is not None
        assert len(result.embeddings) == 2
    
    def test_batch_result_with_error(self):
        """Test BatchResult with error."""
        from backend.services.embedding_batch_processor import BatchResult
        
        result = BatchResult(
            batch_number=1,
            success=False,
            documents_processed=0,
            error_message="Embedding failed"
        )
        assert result.success is False
        assert result.error_message == "Embedding failed"


class TestBatchConfig:
    """Tests for BatchConfig dataclass."""
    
    def test_batch_config_defaults(self):
        """Test BatchConfig default values."""
        from backend.services.embedding_batch_processor import BatchConfig
        
        config = BatchConfig()
        assert config.batch_size == 50
        assert config.max_concurrent == 5
        assert config.retry_attempts == 3
    
    def test_batch_config_custom_values(self):
        """Test BatchConfig with custom values."""
        from backend.services.embedding_batch_processor import BatchConfig
        
        config = BatchConfig(
            batch_size=100,
            max_concurrent=10,
            retry_attempts=5
        )
        assert config.batch_size == 100
        assert config.max_concurrent == 10
        assert config.retry_attempts == 5


class TestEmbeddingBatchProcessorInit:
    """Tests for EmbeddingBatchProcessor initialization."""
    
    def test_processor_with_default_config(self):
        """Test processor with default config."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        assert processor.config is not None
        assert processor.config.batch_size == 50
    
    def test_processor_with_custom_config(self):
        """Test processor with custom config."""
        from backend.services.embedding_batch_processor import (
            EmbeddingBatchProcessor,
            BatchConfig
        )
        
        config = BatchConfig(batch_size=25)
        processor = EmbeddingBatchProcessor(config=config)
        assert processor.config.batch_size == 25
    
    def test_processor_initial_state(self):
        """Test processor initial state."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        assert processor._cancelled is False
        assert processor._paused is False
        assert processor.embedding_model is None


class TestEnsureModel:
    """Tests for _ensure_model method."""
    
    def test_ensure_model_loads_lazily(self):
        """Test model is loaded lazily."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        with patch('backend.services.embedding_batch_processor.get_embedding_model') as mock_get:
            mock_model = MagicMock()
            mock_get.return_value = mock_model
            
            processor = EmbeddingBatchProcessor()
            assert processor.embedding_model is None
            
            processor._ensure_model()
            assert processor.embedding_model is not None
            mock_get.assert_called_once()
    
    def test_ensure_model_caches_model(self):
        """Test model is cached after first load."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        with patch('backend.services.embedding_batch_processor.get_embedding_model') as mock_get:
            mock_model = MagicMock()
            mock_get.return_value = mock_model
            
            processor = EmbeddingBatchProcessor()
            processor._ensure_model()
            processor._ensure_model()  # Call again
            
            # Should only be called once
            mock_get.assert_called_once()


class TestProcessDocuments:
    """Tests for process_documents method."""
    
    @pytest.mark.asyncio
    async def test_process_documents_empty_list(self):
        """Test processing empty document list."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        with patch('backend.services.embedding_batch_processor.get_embedding_model') as mock_get:
            mock_model = MagicMock()
            mock_model.embed_documents.return_value = []
            mock_get.return_value = mock_model
            
            processor = EmbeddingBatchProcessor()
            result = await processor.process_documents([])
            
            assert result["total_documents"] == 0
            assert result["processed_documents"] == 0
    
    @pytest.mark.asyncio
    async def test_process_documents_calculates_batches(self):
        """Test batch calculation."""
        from backend.services.embedding_batch_processor import (
            EmbeddingBatchProcessor,
            BatchConfig
        )
        
        with patch('backend.services.embedding_batch_processor.get_embedding_model') as mock_get:
            mock_model = MagicMock()
            mock_model.embed_documents.return_value = [[0.1] * 10]
            mock_get.return_value = mock_model
            
            config = BatchConfig(batch_size=10)
            processor = EmbeddingBatchProcessor(config=config)
            
            # 25 documents with batch size 10 = 3 batches
            documents = ["doc" + str(i) for i in range(25)]
            result = await processor.process_documents(documents)
            
            assert result["total_documents"] == 25


class TestCancellation:
    """Tests for cancellation functionality."""
    
    def test_cancel_method_exists(self):
        """Test cancel method exists."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        assert hasattr(processor, 'cancel')
    
    def test_cancel_sets_flag(self):
        """Test cancel sets cancelled flag."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        processor.cancel()
        assert processor._cancelled is True


class TestPause:
    """Tests for pause/resume functionality."""
    
    def test_pause_method_exists(self):
        """Test pause method exists."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        assert hasattr(processor, 'pause')
    
    def test_resume_method_exists(self):
        """Test resume method exists."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        assert hasattr(processor, 'resume')
    
    def test_pause_sets_flag(self):
        """Test pause sets paused flag."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        processor.pause()
        assert processor._paused is True
    
    def test_resume_clears_flag(self):
        """Test resume clears paused flag."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        processor.pause()
        processor.resume()
        assert processor._paused is False


class TestProcessBatch:
    """Tests for _process_batch method."""
    
    def test_process_batch_method_exists(self):
        """Test _process_batch method exists."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        processor = EmbeddingBatchProcessor()
        assert hasattr(processor, '_process_batch')
    
    @pytest.mark.asyncio
    async def test_process_batch_returns_result(self):
        """Test _process_batch returns BatchResult."""
        from backend.services.embedding_batch_processor import EmbeddingBatchProcessor
        
        with patch('backend.services.embedding_batch_processor.get_embedding_model') as mock_get:
            mock_model = MagicMock()
            mock_model.embed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
            mock_get.return_value = mock_model
            
            processor = EmbeddingBatchProcessor()
            processor._ensure_model()
            
            result = await processor._process_batch(
                batch_number=1,
                start_index=0,
                documents=["doc1", "doc2"]
            )
            
            assert result is not None
            assert result.batch_number == 1


class TestLoggerConfiguration:
    """Tests for logger configuration."""
    
    def test_logger_exists(self):
        """Test logger is configured."""
        from backend.services.embedding_batch_processor import logger
        assert logger is not None
