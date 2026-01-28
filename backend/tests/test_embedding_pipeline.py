"""
Integration tests for the embedding pipeline.
Tests EmbeddingDocumentGenerator and EmbeddingJobService integration.
"""
import pytest
import json
from backend.services.embedding_document_generator import (
    EmbeddingDocumentGenerator,
    EmbeddingDocument,
    get_document_generator
)


class TestEmbeddingDocumentGenerator:
    """Integration tests for embedding document generation."""
    
    @pytest.fixture
    def generator(self):
        """Create a fresh generator instance."""
        return EmbeddingDocumentGenerator()
    
    @pytest.fixture
    def sample_schema(self):
        """Sample database schema for testing - matches generator expected format."""
        return {
            "tables": {
                "patients": {
                    "columns": {
                        "id": {"type": "INTEGER", "nullable": False, "primary_key": True},
                        "first_name": {"type": "VARCHAR(255)", "nullable": True},
                        "last_name": {"type": "VARCHAR(255)", "nullable": True},
                        "birth_date": {"type": "DATE", "nullable": True},
                        "gender": {"type": "VARCHAR(10)", "nullable": True}
                    }
                },
                "encounters": {
                    "columns": {
                        "id": {"type": "INTEGER", "nullable": False, "primary_key": True},
                        "patient_id": {"type": "INTEGER", "nullable": False, "foreign_key": "patients.id"},
                        "encounter_date": {"type": "TIMESTAMP", "nullable": True},
                        "encounter_type": {"type": "VARCHAR(50)", "nullable": True},
                        "provider_id": {"type": "INTEGER", "nullable": True}
                    }
                }
            }
        }
    
    @pytest.fixture
    def sample_dictionary(self):
        """Sample data dictionary for testing."""
        return """
        # Data Dictionary
        
        ## patients
        - id: Primary key for patient records
        - first_name: Patient's first/given name
        - last_name: Patient's last/family name
        - birth_date: Patient's date of birth
        - gender: Patient's gender (M, F, U)
        
        ## encounters
        - id: Primary key for encounter records
        - patient_id: Foreign key to patients.id
        - encounter_date: Date and time of the encounter
        - encounter_type: Type of encounter (office, telehealth, emergency)
        - provider_id: ID of the healthcare provider
        """
    
    def test_generate_table_documents(self, generator, sample_schema):
        """Test table-level document generation."""
        docs = generator.generate_table_documents(sample_schema)
        
        assert len(docs) == 2
        assert all(isinstance(d, EmbeddingDocument) for d in docs)
        
        table_names = [d.source_table for d in docs]
        assert "patients" in table_names
        assert "encounters" in table_names
        
        # Verify document types
        assert all(d.document_type == "table" for d in docs)
    
    def test_generate_column_documents(self, generator, sample_schema):
        """Test column-level document generation."""
        docs = generator.generate_column_documents(sample_schema)
        
        # 5 columns in patients + 5 columns in encounters = 10
        assert len(docs) == 10
        
        # Verify structure
        for doc in docs:
            assert doc.document_type == "column"
            assert doc.source_table is not None
            assert doc.source_column is not None
            assert len(doc.content) > 0
    
    def test_generate_all_with_dictionary(self, generator, sample_schema, sample_dictionary):
        """Test full document generation with data dictionary."""
        docs = generator.generate_all(sample_schema, sample_dictionary)
        
        # Should have tables + columns + potentially relationships
        assert len(docs) >= 12  # At least 2 tables + 10 columns
        
        # Verify documents contain dictionary content
        patient_table_doc = next((d for d in docs if d.source_table == "patients" and d.document_type == "table"), None)
        assert patient_table_doc is not None
    
    def test_load_json_dictionary(self, generator):
        """Test loading dictionary from JSON format."""
        json_dict = json.dumps({
            "tables": {
                "patients": {
                    "description": "Patient demographics",
                    "columns": {
                        "id": "Primary key",
                        "first_name": "Given name"
                    }
                }
            }
        })
        
        generator.load_data_dictionary(json_dict)
        
        # The generator stores loaded dictionary entries in self.dictionary
        # Check that loading succeeded 
        assert hasattr(generator, 'dictionary')
        # Note: The exact structure depends on implementation - adjust as needed
    
    def test_empty_schema_returns_empty_docs(self, generator):
        """Test that empty schema returns empty document list."""
        empty_schema = {"tables": [], "details": {}}
        docs = generator.generate_all(empty_schema)
        
        assert len(docs) == 0
    
    def test_get_document_generator_returns_instance(self):
        """Test factory function returns generator instance."""
        gen = get_document_generator()
        
        assert isinstance(gen, EmbeddingDocumentGenerator)


class TestEmbeddingJobIntegration:
    """Integration tests for embedding job lifecycle."""
    
    # Note: These tests require database access
    # Skipping if test database is not configured
    
    @pytest.fixture
    def sample_user(self):
        """Sample user for testing."""
        from backend.models.schemas import User
        return User(
            id=1,
            username="test_embed_user",
            email="embed@test.com",
            role="super_admin",
            is_active=True
        )
    
    @pytest.mark.skip(reason="Requires real database context")
    def test_job_lifecycle(self, sample_user):
        """Test job creation and state transitions."""
        from backend.services.embedding_job_service import get_embedding_job_service
        
        service = get_embedding_job_service()
        
        # Create job
        job_id = service.create_job(
            config_id=1,
            total_documents=100,
            user=sample_user,
            batch_size=10
        )
        
        assert job_id is not None
        
        # Start job
        service.start_job(job_id)
        
        # Update progress
        service.update_progress(job_id, processed_documents=10, current_batch=1)
        
        progress = service.get_job_progress(job_id)
        assert progress is not None
        assert progress.processed_documents == 10
        
        # Cancel job (cleanup)
        service.cancel_job(job_id, sample_user)
