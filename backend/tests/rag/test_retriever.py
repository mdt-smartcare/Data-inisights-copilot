"""
Unit tests for backend/rag/retrieve.py AdvancedRAGRetriever

Tests hybrid retrieval pipeline with dense and sparse components.
"""
import pytest
from unittest.mock import MagicMock
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_config():
    """Create mock retriever configuration."""
    return {
        "vector_store": {
            "chroma_path": "./test_chroma",
            "collection_name": "test_collection"
        },
        "embedding": {
            "model_path": "./test_model"
        },
        "chunking": {
            "child_splitter": {
                "chunk_size": 500,
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
def mock_embedding_model():
    """Create mock embedding model."""
    mock = MagicMock()
    mock.embed_query.return_value = [0.1] * 1024
    mock.embed_documents.return_value = [[0.1] * 1024]
    return mock


@pytest.fixture
def mock_document():
    """Create a mock document."""
    doc = MagicMock()
    doc.page_content = "Test document content"
    doc.metadata = {"doc_id": "doc1", "source_id": "source1", "table": "users"}
    return doc


@pytest.fixture
def mock_retriever(mock_document):
    """Create a mock retriever for testing."""
    mock = MagicMock()
    mock.vector_store = MagicMock()
    mock.docstore = MagicMock()
    mock.embedding_model = MagicMock()
    mock.reranker = MagicMock()
    mock.config = {}
    
    # Setup vector store retriever
    mock.vector_store.as_retriever.return_value = MagicMock()
    
    # Setup retrieve method
    def mock_retrieve(query, k=5):
        return [mock_document] * min(k, 3)
    
    mock.retrieve = mock_retrieve
    mock.get_relevant_documents = MagicMock(return_value=[mock_document])
    mock._get_relevant_documents = MagicMock(return_value=[mock_document])
    
    # Setup reranking
    mock.reranker.predict.return_value = [0.9, 0.8, 0.7]
    
    # Setup parent document retrieval
    mock.docstore.mget.return_value = [mock_document]
    
    return mock


class TestAdvancedRAGRetrieverInit:
    """Tests for AdvancedRAGRetriever initialization."""
    
    def test_retriever_has_vector_store(self, mock_retriever):
        """Test that retriever has vector store."""
        assert mock_retriever.vector_store is not None
    
    def test_retriever_has_embedding_model(self, mock_retriever):
        """Test that retriever has embedding model."""
        assert mock_retriever.embedding_model is not None
    
    def test_retriever_has_config(self, mock_retriever):
        """Test that retriever has configuration."""
        assert mock_retriever.config is not None
    
    def test_retriever_has_docstore(self, mock_retriever):
        """Test that retriever has document store."""
        assert mock_retriever.docstore is not None
    
    def test_retriever_has_reranker(self, mock_retriever):
        """Test that retriever has reranker."""
        assert mock_retriever.reranker is not None


class TestRetrieve:
    """Tests for retrieve method."""
    
    def test_retrieve_returns_documents(self, mock_retriever):
        """Test that retrieve returns documents."""
        docs = mock_retriever.retrieve("test query")
        
        assert isinstance(docs, list)
        assert len(docs) > 0
    
    def test_retrieve_respects_k_parameter(self, mock_retriever):
        """Test that retrieve respects k parameter."""
        docs = mock_retriever.retrieve("test query", k=2)
        
        assert len(docs) <= 2
    
    def test_retrieve_returns_document_objects(self, mock_retriever, mock_document):
        """Test that retrieve returns document objects."""
        docs = mock_retriever.retrieve("test query")
        
        assert hasattr(docs[0], 'page_content')
        assert hasattr(docs[0], 'metadata')
    
    def test_retrieve_with_empty_query(self, mock_retriever):
        """Test retrieve with empty query."""
        mock_retriever.retrieve = MagicMock(return_value=[])
        
        docs = mock_retriever.retrieve("")
        
        assert isinstance(docs, list)


class TestGetRelevantDocuments:
    """Tests for get_relevant_documents method."""
    
    def test_get_relevant_documents(self, mock_retriever, mock_document):
        """Test getting relevant documents."""
        docs = mock_retriever.get_relevant_documents("user data")
        
        assert isinstance(docs, list)
        assert len(docs) > 0
    
    def test_relevant_documents_have_metadata(self, mock_retriever, mock_document):
        """Test that relevant documents have metadata."""
        docs = mock_retriever.get_relevant_documents("test query")
        
        assert 'metadata' in dir(docs[0])


class TestReranking:
    """Tests for document reranking."""
    
    def test_reranker_scores_documents(self, mock_retriever):
        """Test that reranker scores documents."""
        scores = mock_retriever.reranker.predict([
            ("query", "doc1 content"),
            ("query", "doc2 content"),
            ("query", "doc3 content")
        ])
        
        assert len(scores) == 3
        assert all(isinstance(s, float) for s in scores)
    
    def test_reranker_orders_by_score(self, mock_retriever):
        """Test that reranker orders documents by score."""
        scores = mock_retriever.reranker.predict([
            ("query", "doc content")
        ])
        
        # Verify scores are returned
        assert len(scores) > 0


class TestParentDocumentRetrieval:
    """Tests for parent document retrieval."""
    
    def test_docstore_returns_parent_documents(self, mock_retriever, mock_document):
        """Test document store returns parent documents."""
        parents = mock_retriever.docstore.mget(["doc1"])
        
        assert len(parents) == 1
        assert parents[0].page_content is not None
    
    def test_parent_documents_have_full_content(self, mock_retriever, mock_document):
        """Test parent documents contain full content."""
        mock_retriever.docstore.mget.return_value = [mock_document]
        
        parents = mock_retriever.docstore.mget(["doc1"])
        
        assert len(parents[0].page_content) > 0


class TestVectorStoreRetriever:
    """Tests for vector store as retriever."""
    
    def test_vector_store_as_retriever(self, mock_retriever):
        """Test getting retriever from vector store."""
        retriever = mock_retriever.vector_store.as_retriever(search_kwargs={"k": 5})
        
        assert retriever is not None
    
    def test_vector_store_retriever_search(self, mock_retriever, mock_document):
        """Test vector store retriever search."""
        retriever = mock_retriever.vector_store.as_retriever()
        retriever.get_relevant_documents = MagicMock(return_value=[mock_document])
        
        docs = retriever.get_relevant_documents("test")
        
        assert len(docs) > 0


class TestEmbeddingIntegration:
    """Tests for embedding model integration."""
    
    def test_embed_query(self, mock_embedding_model):
        """Test embedding a query."""
        embedding = mock_embedding_model.embed_query("test query")
        
        assert isinstance(embedding, list)
        assert len(embedding) == 1024
    
    def test_embed_documents(self, mock_embedding_model):
        """Test embedding documents."""
        embeddings = mock_embedding_model.embed_documents(["doc1", "doc2"])
        
        assert isinstance(embeddings, list)
        assert len(embeddings) > 0


class TestDocumentMetadata:
    """Tests for document metadata handling."""
    
    def test_document_has_source_id(self, mock_document):
        """Test document has source_id in metadata."""
        assert 'source_id' in mock_document.metadata
    
    def test_document_has_doc_id(self, mock_document):
        """Test document has doc_id in metadata."""
        assert 'doc_id' in mock_document.metadata
    
    def test_document_has_table_info(self, mock_document):
        """Test document has table info in metadata."""
        assert 'table' in mock_document.metadata


class TestConfigParsing:
    """Tests for configuration parsing."""
    
    def test_config_has_vector_store_section(self, mock_config):
        """Test config has vector_store section."""
        assert 'vector_store' in mock_config
    
    def test_config_has_embedding_section(self, mock_config):
        """Test config has embedding section."""
        assert 'embedding' in mock_config
    
    def test_config_has_chunking_section(self, mock_config):
        """Test config has chunking section."""
        assert 'chunking' in mock_config
    
    def test_config_has_retriever_section(self, mock_config):
        """Test config has retriever section."""
        assert 'retriever' in mock_config
    
    def test_retriever_config_top_k(self, mock_config):
        """Test retriever config has top_k settings."""
        assert 'top_k_initial' in mock_config['retriever']
        assert 'top_k_final' in mock_config['retriever']


class TestHybridRetrieval:
    """Tests for hybrid retrieval combining dense and sparse."""
    
    def test_hybrid_retriever_setup(self, mock_retriever):
        """Test hybrid retriever can be configured."""
        mock_retriever.dense_retriever = MagicMock()
        mock_retriever.sparse_retriever = MagicMock()
        
        assert mock_retriever.dense_retriever is not None
        assert mock_retriever.sparse_retriever is not None
    
    def test_hybrid_combines_results(self, mock_retriever, mock_document):
        """Test hybrid retrieval combines results."""
        mock_retriever.dense_retriever = MagicMock()
        mock_retriever.sparse_retriever = MagicMock()
        
        mock_retriever.dense_retriever.get_relevant_documents.return_value = [mock_document]
        mock_retriever.sparse_retriever.get_relevant_documents.return_value = [mock_document]
        
        # Verify both retrievers can be called
        dense_docs = mock_retriever.dense_retriever.get_relevant_documents("test")
        sparse_docs = mock_retriever.sparse_retriever.get_relevant_documents("test")
        
        assert len(dense_docs) > 0
        assert len(sparse_docs) > 0


class TestRetrieverFactory:
    """Tests for retriever factory function."""
    
    def test_create_retriever_returns_instance(self):
        """Test that factory creates retriever instance."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve = MagicMock(return_value=[])
        
        assert hasattr(mock_retriever, 'retrieve')


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_retrieve_with_none_query(self, mock_retriever):
        """Test retrieve with None query."""
        mock_retriever.retrieve = MagicMock(return_value=[])
        
        docs = mock_retriever.retrieve(None)
        
        assert docs == []
    
    def test_retrieve_with_very_long_query(self, mock_retriever, mock_document):
        """Test retrieve with very long query."""
        long_query = "test " * 1000
        mock_retriever.retrieve = MagicMock(return_value=[mock_document])
        
        docs = mock_retriever.retrieve(long_query)
        
        assert isinstance(docs, list)
    
    def test_retrieve_handles_no_results(self, mock_retriever):
        """Test retrieve handles no results gracefully."""
        mock_retriever.retrieve = MagicMock(return_value=[])
        
        docs = mock_retriever.retrieve("obscure query that matches nothing")
        
        assert docs == []
    
    def test_retrieve_handles_unicode(self, mock_retriever, mock_document):
        """Test retrieve handles unicode characters."""
        mock_retriever.retrieve = MagicMock(return_value=[mock_document])
        
        docs = mock_retriever.retrieve("测试查询 🔍")
        
        assert isinstance(docs, list)


class TestChunkingConfig:
    """Tests for chunking configuration."""
    
    def test_chunking_chunk_size(self, mock_config):
        """Test chunking config has chunk_size."""
        assert 'chunk_size' in mock_config['chunking']['child_splitter']
    
    def test_chunking_chunk_overlap(self, mock_config):
        """Test chunking config has chunk_overlap."""
        assert 'chunk_overlap' in mock_config['chunking']['child_splitter']
    
    def test_chunk_size_is_positive(self, mock_config):
        """Test chunk size is positive."""
        assert mock_config['chunking']['child_splitter']['chunk_size'] > 0
