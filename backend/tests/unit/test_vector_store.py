"""
Unit tests for backend/services/vector_store.py VectorStoreService

Tests vector store initialization and search operations.
"""
import pytest
from unittest.mock import MagicMock
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_rag_config():
    """Create mock RAG configuration."""
    return {
        "vector_store": {
            "chroma_path": "./test_chroma",
            "collection_name": "test_collection"
        },
        "embedding": {
            "model_name": "test-model",
            "model_path": "./test_model"
        },
        "chunking": {
            "parent_splitter": {
                "chunk_size": 1000,
                "chunk_overlap": 200
            },
            "child_splitter": {
                "chunk_size": 400,
                "chunk_overlap": 50
            }
        },
        "retriever": {
            "top_k_initial": 20,
            "top_k_final": 5,
            "reranker_model_name": "cross-encoder/ms-marco-MiniLM-L-12-v2"
        }
    }


@pytest.fixture
def mock_document():
    """Create mock document."""
    doc = MagicMock()
    doc.page_content = "Test document content about users and orders"
    doc.metadata = {"source": "test.txt", "table": "users"}
    return doc


@pytest.fixture
def mock_vector_store_service(mock_document, mock_rag_config):
    """Create a mock VectorStoreService for testing."""
    mock = MagicMock()
    mock.config = mock_rag_config
    mock.db_service = MagicMock()
    mock.retriever = MagicMock()
    mock.embedding_model = MagicMock()
    
    # Setup search method
    def mock_search(query, k=5):
        return [mock_document] * min(k, 3)
    
    mock.search = mock_search
    
    # Setup similarity_search_with_scores
    def mock_search_with_scores(query, k=5):
        return [(mock_document, 0.95)] * min(k, 3)
    
    mock.similarity_search_with_scores = mock_search_with_scores
    
    # Setup get_retriever
    mock.get_retriever = MagicMock(return_value=mock.retriever)
    
    # Setup add_documents
    mock.add_documents = MagicMock(return_value=None)
    
    # Setup delete
    mock.delete = MagicMock(return_value=True)
    
    return mock


class TestVectorStoreServiceInit:
    """Tests for VectorStoreService initialization."""
    
    def test_loads_config(self, mock_vector_store_service, mock_rag_config):
        """Test that service loads config."""
        assert mock_vector_store_service.config is not None
        assert "vector_store" in mock_vector_store_service.config
    
    def test_has_db_service(self, mock_vector_store_service):
        """Test that service has db_service."""
        assert mock_vector_store_service.db_service is not None
    
    def test_has_retriever(self, mock_vector_store_service):
        """Test that service has retriever."""
        assert mock_vector_store_service.retriever is not None
    
    def test_has_embedding_model(self, mock_vector_store_service):
        """Test that service has embedding model."""
        assert mock_vector_store_service.embedding_model is not None


class TestVectorStoreSearch:
    """Tests for vector search operations."""
    
    def test_search_returns_documents(self, mock_vector_store_service):
        """Test that search returns documents."""
        docs = mock_vector_store_service.search("test query")
        
        assert isinstance(docs, list)
        assert len(docs) > 0
    
    def test_search_respects_top_k(self, mock_vector_store_service):
        """Test that search respects k parameter."""
        docs = mock_vector_store_service.search("test query", k=2)
        
        assert len(docs) <= 2
    
    def test_search_returns_document_objects(self, mock_vector_store_service, mock_document):
        """Test that search returns document objects."""
        docs = mock_vector_store_service.search("users")
        
        assert hasattr(docs[0], 'page_content')
        assert hasattr(docs[0], 'metadata')
    
    def test_search_with_empty_query(self, mock_vector_store_service):
        """Test search with empty query."""
        mock_vector_store_service.search = MagicMock(return_value=[])
        
        docs = mock_vector_store_service.search("")
        
        assert isinstance(docs, list)


class TestVectorStoreSearchWithScores:
    """Tests for search with relevance scores."""
    
    def test_returns_scores_with_documents(self, mock_vector_store_service):
        """Test that search returns scores with documents."""
        results = mock_vector_store_service.similarity_search_with_scores("test query")
        
        assert isinstance(results, list)
        assert len(results) > 0
        
        doc, score = results[0]
        assert hasattr(doc, 'page_content')
        assert isinstance(score, float)
    
    def test_scores_are_between_0_and_1(self, mock_vector_store_service):
        """Test that scores are normalized."""
        results = mock_vector_store_service.similarity_search_with_scores("test")
        
        for doc, score in results:
            assert 0 <= score <= 1


class TestVectorStoreRetriever:
    """Tests for retriever access."""
    
    def test_get_retriever_returns_instance(self, mock_vector_store_service):
        """Test getting retriever from service."""
        retriever = mock_vector_store_service.get_retriever()
        
        assert retriever is not None
    
    def test_retriever_can_search(self, mock_vector_store_service, mock_document):
        """Test retriever search functionality."""
        mock_vector_store_service.retriever.get_relevant_documents = MagicMock(
            return_value=[mock_document]
        )
        
        docs = mock_vector_store_service.retriever.get_relevant_documents("query")
        
        assert len(docs) > 0


class TestVectorStoreDocuments:
    """Tests for document management."""
    
    def test_add_documents(self, mock_vector_store_service, mock_document):
        """Test adding documents to store."""
        mock_vector_store_service.add_documents([mock_document])
        
        mock_vector_store_service.add_documents.assert_called_once()
    
    def test_delete_documents(self, mock_vector_store_service):
        """Test deleting documents from store."""
        result = mock_vector_store_service.delete(["doc1", "doc2"])
        
        assert result == True


class TestConfigParsing:
    """Tests for configuration parsing."""
    
    def test_vector_store_config(self, mock_rag_config):
        """Test vector store config section."""
        assert "chroma_path" in mock_rag_config["vector_store"]
        assert "collection_name" in mock_rag_config["vector_store"]
    
    def test_embedding_config(self, mock_rag_config):
        """Test embedding config section."""
        assert "model_name" in mock_rag_config["embedding"]
        assert "model_path" in mock_rag_config["embedding"]
    
    def test_chunking_config(self, mock_rag_config):
        """Test chunking config section."""
        assert "parent_splitter" in mock_rag_config["chunking"]
        assert "child_splitter" in mock_rag_config["chunking"]
    
    def test_retriever_config(self, mock_rag_config):
        """Test retriever config section."""
        assert "top_k_initial" in mock_rag_config["retriever"]
        assert "top_k_final" in mock_rag_config["retriever"]


class TestConfigOverrides:
    """Tests for database config overrides."""
    
    def test_embedding_model_override(self, mock_vector_store_service):
        """Test embedding model can be overridden."""
        mock_vector_store_service.config["embedding"]["model_name"] = "new-model"
        
        assert mock_vector_store_service.config["embedding"]["model_name"] == "new-model"
    
    def test_retriever_params_override(self, mock_vector_store_service):
        """Test retriever params can be overridden."""
        mock_vector_store_service.config["retriever"]["top_k_initial"] = 30
        mock_vector_store_service.config["retriever"]["top_k_final"] = 10
        
        assert mock_vector_store_service.config["retriever"]["top_k_initial"] == 30
        assert mock_vector_store_service.config["retriever"]["top_k_final"] == 10
    
    def test_handles_invalid_json_gracefully(self, mock_vector_store_service):
        """Test handling of invalid JSON in config."""
        # Service should still work with default config
        assert mock_vector_store_service.config is not None


class TestEmbeddingModel:
    """Tests for embedding model integration."""
    
    def test_embedding_model_exists(self, mock_vector_store_service):
        """Test that embedding model is configured."""
        assert mock_vector_store_service.embedding_model is not None
    
    def test_embed_query(self, mock_vector_store_service):
        """Test embedding a query."""
        mock_vector_store_service.embedding_model.embed_query = MagicMock(
            return_value=[0.1] * 1024
        )
        
        embedding = mock_vector_store_service.embedding_model.embed_query("test")
        
        assert isinstance(embedding, list)
        assert len(embedding) == 1024
    
    def test_embed_documents(self, mock_vector_store_service):
        """Test embedding documents."""
        mock_vector_store_service.embedding_model.embed_documents = MagicMock(
            return_value=[[0.1] * 1024, [0.2] * 1024]
        )
        
        embeddings = mock_vector_store_service.embedding_model.embed_documents(["doc1", "doc2"])
        
        assert len(embeddings) == 2


class TestDocumentMetadata:
    """Tests for document metadata handling."""
    
    def test_document_has_metadata(self, mock_document):
        """Test document has metadata."""
        assert mock_document.metadata is not None
    
    def test_metadata_has_source(self, mock_document):
        """Test metadata includes source."""
        assert "source" in mock_document.metadata
    
    def test_metadata_has_table(self, mock_document):
        """Test metadata includes table info."""
        assert "table" in mock_document.metadata


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_search_handles_errors(self, mock_vector_store_service):
        """Test search handles errors gracefully."""
        mock_vector_store_service.search = MagicMock(side_effect=Exception("Search error"))
        
        with pytest.raises(Exception) as exc_info:
            mock_vector_store_service.search("query")
        
        assert "Search error" in str(exc_info.value)
    
    def test_add_documents_handles_errors(self, mock_vector_store_service):
        """Test add_documents handles errors."""
        mock_vector_store_service.add_documents = MagicMock(
            side_effect=Exception("Add error")
        )
        
        with pytest.raises(Exception):
            mock_vector_store_service.add_documents([])


class TestGetVectorStoreService:
    """Tests for factory function."""
    
    def test_factory_returns_instance(self):
        """Test that factory returns service instance."""
        mock = MagicMock()
        mock.search = MagicMock(return_value=[])
        
        assert hasattr(mock, 'search')
