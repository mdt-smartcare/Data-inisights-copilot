"""
Tests for embedding document generator.
"""


class TestEmbeddingDocument:
    """Tests for EmbeddingDocument dataclass."""
    
    def test_embedding_document_creation(self):
        """Test EmbeddingDocument can be created."""
        from backend.services.embedding_document_generator import EmbeddingDocument
        
        doc = EmbeddingDocument(
            document_id="doc1",
            document_type="table",
            content="Test content"
        )
        assert doc.document_id == "doc1"
        assert doc.document_type == "table"
        assert doc.content == "Test content"
    
    def test_embedding_document_with_source(self):
        """Test EmbeddingDocument with source info."""
        from backend.services.embedding_document_generator import EmbeddingDocument
        
        doc = EmbeddingDocument(
            document_id="col1",
            document_type="column",
            content="Column description",
            source_table="users",
            source_column="email"
        )
        assert doc.source_table == "users"
        assert doc.source_column == "email"
    
    def test_embedding_document_metadata_default(self):
        """Test EmbeddingDocument metadata defaults to empty dict."""
        from backend.services.embedding_document_generator import EmbeddingDocument
        
        doc = EmbeddingDocument(
            document_id="doc1",
            document_type="table",
            content="Test"
        )
        assert doc.metadata == {}
    
    def test_embedding_document_with_metadata(self):
        """Test EmbeddingDocument with custom metadata."""
        from backend.services.embedding_document_generator import EmbeddingDocument
        
        doc = EmbeddingDocument(
            document_id="doc1",
            document_type="table",
            content="Test",
            metadata={"key": "value"}
        )
        assert doc.metadata["key"] == "value"


class TestEmbeddingDocumentGeneratorInit:
    """Tests for EmbeddingDocumentGenerator initialization."""
    
    def test_generator_creates_empty_dictionary(self):
        """Test generator starts with empty dictionary."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        assert generator.dictionary == {}


class TestLoadDataDictionary:
    """Tests for load_data_dictionary method."""
    
    def test_load_empty_dictionary(self):
        """Test loading empty dictionary."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        generator.load_data_dictionary("")
        assert generator.dictionary == {}
    
    def test_load_json_dictionary(self):
        """Test loading JSON format dictionary."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        import json
        
        generator = EmbeddingDocumentGenerator()
        dict_content = json.dumps({
            "users": {
                "description": "User accounts",
                "columns": {
                    "id": "Unique identifier",
                    "email": "User email address"
                }
            }
        })
        
        generator.load_data_dictionary(dict_content)
        assert "users" in generator.dictionary
        assert "users.id" in generator.dictionary
        assert "users.email" in generator.dictionary
    
    def test_load_text_dictionary(self):
        """Test loading text format dictionary."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        dict_content = """
        users: User accounts table
        users.id: Unique identifier
        users.email: User email address
        """
        
        generator.load_data_dictionary(dict_content)
        assert "users" in generator.dictionary
        assert "users.id" in generator.dictionary
    
    def test_load_text_ignores_comments(self):
        """Test text dictionary ignores comments."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        dict_content = """
        # This is a comment
        users: User accounts
        """
        
        generator.load_data_dictionary(dict_content)
        assert "users" in generator.dictionary
        assert len([k for k in generator.dictionary if k.startswith('#')]) == 0


class TestLoadJsonDictionary:
    """Tests for _load_json_dictionary method."""
    
    def test_load_simple_json(self):
        """Test loading simple JSON structure."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        data = {
            "users": "User accounts table"
        }
        
        generator._load_json_dictionary(data)
        assert generator.dictionary["users"] == "User accounts table"
    
    def test_load_nested_json(self):
        """Test loading nested JSON structure."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        data = {
            "users": {
                "description": "User accounts",
                "columns": {
                    "id": {"description": "User ID"}
                }
            }
        }
        
        generator._load_json_dictionary(data)
        assert "users" in generator.dictionary
        assert "users.id" in generator.dictionary


class TestLoadTextDictionary:
    """Tests for _load_text_dictionary method."""
    
    def test_load_text_format(self):
        """Test loading text format."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        content = "table1: Description of table1"
        
        generator._load_text_dictionary(content)
        assert generator.dictionary["table1"] == "Description of table1"
    
    def test_load_multiline_text(self):
        """Test loading multiline text."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        content = """
        table1: First table
        table2: Second table
        """
        
        generator._load_text_dictionary(content)
        assert "table1" in generator.dictionary
        assert "table2" in generator.dictionary


class TestGenerateTableDocuments:
    """Tests for generate_table_documents method."""
    
    def test_generate_table_documents_method_exists(self):
        """Test method exists."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        assert hasattr(generator, 'generate_table_documents')
    
    def test_generate_from_empty_schema(self):
        """Test generating from empty schema."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        docs = generator.generate_table_documents({})
        assert docs == []
    
    def test_generate_table_document(self):
        """Test generating table document."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        # Schema should have tables dict with table names and columns as list of strings
        schema = {
            "tables": {
                "users": {
                    "columns": ["id", "email", "username"]  # List of column names as strings
                }
            }
        }
        
        docs = generator.generate_table_documents(schema)
        assert len(docs) > 0


class TestGenerateColumnDocuments:
    """Tests for generate_column_documents method."""
    
    def test_generate_column_documents_method_exists(self):
        """Test method exists."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        assert hasattr(generator, 'generate_column_documents')


class TestGenerateRelationshipDocuments:
    """Tests for generate_relationship_documents method."""
    
    def test_generate_relationship_documents_method_exists(self):
        """Test method exists."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        assert hasattr(generator, 'generate_relationship_documents')


class TestGenerateAll:
    """Tests for generate_all method."""
    
    def test_generate_all_method_exists(self):
        """Test method exists."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        assert hasattr(generator, 'generate_all')
    
    def test_generate_all_returns_list(self):
        """Test generate_all returns list of documents."""
        from backend.services.embedding_document_generator import EmbeddingDocumentGenerator
        
        generator = EmbeddingDocumentGenerator()
        result = generator.generate_all(schema={}, dictionary_content="")
        # generate_all returns a list of EmbeddingDocument
        assert isinstance(result, list)


class TestLoggerConfiguration:
    """Tests for logger configuration."""
    
    def test_logger_exists(self):
        """Test logger is configured."""
        from backend.services.embedding_document_generator import logger
        assert logger is not None
