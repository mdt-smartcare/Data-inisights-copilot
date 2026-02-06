"""
Unit tests for backend/pipeline/transform.py AdvancedDataTransformer

Tests document creation and parent-child chunking.
"""
import pytest
import pandas as pd
import numpy as np
import os
from langchain_core.documents import Document

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_config():
    """Create mock transformer config."""
    return {
        "chunking": {
            "parent_splitter": {
                "chunk_size": 1000,
                "chunk_overlap": 200
            },
            "child_splitter": {
                "chunk_size": 400,
                "chunk_overlap": 50
            }
        }
    }


@pytest.fixture
def sample_table_data():
    """Create sample table data for testing."""
    users_df = pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"],
        "email": ["alice@test.com", "bob@test.com", "charlie@test.com"],
        "age": [25, 30, 35]
    })
    
    orders_df = pd.DataFrame({
        "id": [101, 102],
        "user_id": [1, 2],
        "total": [99.99, 149.99],
        "status": ["completed", "pending"]
    })
    
    return {
        "users": users_df,
        "orders": orders_df
    }


class TestSimpleInMemoryStore:
    """Tests for SimpleInMemoryStore class."""
    
    def test_store_initializes_empty(self):
        """Test that store starts empty."""
        from backend.pipeline.transform import SimpleInMemoryStore
        
        store = SimpleInMemoryStore()
        
        assert list(store.yield_keys()) == []
    
    def test_mset_stores_documents(self):
        """Test storing documents."""
        from backend.pipeline.transform import SimpleInMemoryStore
        
        store = SimpleInMemoryStore()
        doc1 = Document(page_content="Content 1")
        doc2 = Document(page_content="Content 2")
        
        store.mset([("key1", doc1), ("key2", doc2)])
        
        assert "key1" in list(store.yield_keys())
        assert "key2" in list(store.yield_keys())
    
    def test_mget_retrieves_documents(self):
        """Test retrieving documents."""
        from backend.pipeline.transform import SimpleInMemoryStore
        
        store = SimpleInMemoryStore()
        doc1 = Document(page_content="Content 1")
        store.mset([("key1", doc1)])
        
        results = store.mget(["key1"])
        
        assert len(results) == 1
        assert results[0].page_content == "Content 1"
    
    def test_mget_skips_missing_keys(self):
        """Test that mget skips missing keys."""
        from backend.pipeline.transform import SimpleInMemoryStore
        
        store = SimpleInMemoryStore()
        doc1 = Document(page_content="Content 1")
        store.mset([("key1", doc1)])
        
        results = store.mget(["key1", "missing_key"])
        
        assert len(results) == 1
    
    def test_mdelete_removes_documents(self):
        """Test deleting documents."""
        from backend.pipeline.transform import SimpleInMemoryStore
        
        store = SimpleInMemoryStore()
        doc1 = Document(page_content="Content 1")
        store.mset([("key1", doc1)])
        
        store.mdelete(["key1"])
        
        assert "key1" not in list(store.yield_keys())
    
    def test_mdelete_ignores_missing_keys(self):
        """Test that mdelete doesn't error on missing keys."""
        from backend.pipeline.transform import SimpleInMemoryStore
        
        store = SimpleInMemoryStore()
        
        # Should not raise
        store.mdelete(["nonexistent"])


class TestAdvancedDataTransformerSafeFormat:
    """Tests for _safe_format_value method."""
    
    def test_formats_simple_values(self, mock_config):
        """Test formatting simple values."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        assert transformer._safe_format_value("hello") == "hello"
        assert transformer._safe_format_value(42) == "42"
        assert transformer._safe_format_value(3.14) == "3.14"
    
    def test_returns_none_for_na_values(self, mock_config):
        """Test that NA values return None."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        assert transformer._safe_format_value(None) is None
        assert transformer._safe_format_value(pd.NA) is None
        assert transformer._safe_format_value(np.nan) is None
    
    def test_returns_none_for_empty_strings(self, mock_config):
        """Test that empty/null strings return None."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        assert transformer._safe_format_value("") is None
        assert transformer._safe_format_value("null") is None
        assert transformer._safe_format_value("None") is None
        assert transformer._safe_format_value("nan") is None
    
    def test_formats_lists(self, mock_config):
        """Test formatting list values."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        result = transformer._safe_format_value(["a", "b", "c"])
        assert result == "a, b, c"
    
    def test_returns_none_for_empty_lists(self, mock_config):
        """Test that empty lists return None."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        assert transformer._safe_format_value([]) is None


class TestAdvancedDataTransformerEnrich:
    """Tests for _enrich_medical_content method."""
    
    def test_enriches_with_medical_context(self, mock_config):
        """Test enrichment with medical context mappings."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        transformer.medical_context = {"bp": "Blood Pressure"}
        
        result = transformer._enrich_medical_content("bp", "120/80")
        
        assert "Blood Pressure" in result
        assert "bp" in result
        assert "120/80" in result
    
    def test_enriches_boolean_medical_flags(self, mock_config):
        """Test enrichment of boolean medical flags."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        result_true = transformer._enrich_medical_content("is_diabetic", True)
        result_false = transformer._enrich_medical_content("is_diabetic", False)
        
        assert "Yes" in result_true
        assert "No" in result_false
    
    def test_default_enrichment(self, mock_config):
        """Test default enrichment format."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        result = transformer._enrich_medical_content("regular_field", "value")
        
        assert result == "regular_field: value"


class TestAdvancedDataTransformerGetRowId:
    """Tests for _get_row_id method."""
    
    def test_uses_id_column(self, mock_config):
        """Test that id column is preferred."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        row = pd.Series({"id": 123, "name": "Test"})
        
        result = transformer._get_row_id(row)
        
        assert result == "123"
    
    def test_uses_patient_track_id(self, mock_config):
        """Test fallback to patient_track_id."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        row = pd.Series({"patient_track_id": 456, "name": "Test"})
        
        result = transformer._get_row_id(row)
        
        assert result == "456"
    
    def test_uses_user_id(self, mock_config):
        """Test fallback to user_id."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        row = pd.Series({"user_id": 789, "name": "Test"})
        
        result = transformer._get_row_id(row)
        
        assert result == "789"
    
    def test_generates_hash_when_no_id(self, mock_config):
        """Test hash generation when no ID column exists."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        row = pd.Series({"name": "Test", "value": 100})
        
        result = transformer._get_row_id(row)
        
        # Should be a 12-character hash
        assert len(result) == 12


class TestAdvancedDataTransformerDocuments:
    """Tests for create_documents_from_tables method."""
    
    def test_creates_documents_from_tables(self, mock_config, sample_table_data):
        """Test document creation from table data."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        docs = transformer.create_documents_from_tables(sample_table_data)
        
        # Should create one document per row
        assert len(docs) == 5  # 3 users + 2 orders
        assert all(isinstance(d, Document) for d in docs)
    
    def test_documents_have_correct_metadata(self, mock_config, sample_table_data):
        """Test that documents have correct metadata."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        docs = transformer.create_documents_from_tables(sample_table_data)
        
        for doc in docs:
            assert "source_table" in doc.metadata
            assert "source_id" in doc.metadata
            assert "is_latest" in doc.metadata
    
    def test_documents_contain_row_content(self, mock_config, sample_table_data):
        """Test that document content contains row data."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        docs = transformer.create_documents_from_tables(sample_table_data)
        
        # Find Alice's document
        alice_docs = [d for d in docs if "Alice" in d.page_content]
        assert len(alice_docs) == 1
        assert "alice@test.com" in alice_docs[0].page_content


class TestAdvancedDataTransformerChunking:
    """Tests for perform_parent_child_chunking method."""
    
    def test_creates_child_documents(self, mock_config):
        """Test that chunking creates child documents."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        # Create a large document that will be split
        large_content = "This is test content. " * 100
        docs = [Document(page_content=large_content, metadata={"source": "test"})]
        
        child_docs, docstore = transformer.perform_parent_child_chunking(docs)
        
        # Should have created child documents
        assert len(child_docs) >= 1
        # Docstore should have parent documents
        assert len(list(docstore.yield_keys())) >= 1
    
    def test_child_documents_have_parent_id(self, mock_config):
        """Test that child documents reference parent ID."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        large_content = "This is test content for chunking. " * 50
        docs = [Document(page_content=large_content, metadata={"source": "test"})]
        
        child_docs, docstore = transformer.perform_parent_child_chunking(docs)
        
        for child in child_docs:
            assert "doc_id" in child.metadata
            # Parent should exist in docstore
            parent_id = child.metadata["doc_id"]
            parents = docstore.mget([parent_id])
            assert len(parents) == 1
    
    def test_small_document_not_split(self, mock_config):
        """Test that small documents may not be split further."""
        from backend.pipeline.transform import AdvancedDataTransformer
        
        transformer = AdvancedDataTransformer(mock_config)
        
        small_content = "Small content"
        docs = [Document(page_content=small_content, metadata={"source": "test"})]
        
        child_docs, docstore = transformer.perform_parent_child_chunking(docs)
        
        # Small doc might still produce 1 child
        assert len(child_docs) >= 1
