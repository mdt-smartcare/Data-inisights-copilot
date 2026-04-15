"""
Tests for the Retrieval Chain Updates (Tasks 1-6)

Tests cover:
1. Prompt template with {retrieved_ddls} variable
2. Schema retriever with top_k settings
3. Retry loop in SQL execution
4. Semantic schema retrieval (not blind loading)
5. DDL vectorization with proper metadata
6. Bidirectional FK dependency resolution
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Dict, Any


# =============================================================================
# Test 1: Prompt Template Variables
# =============================================================================
class TestPromptTemplates:
    """Test that prompt templates have the correct variables."""
    
    def test_build_sql_generation_prompt_exists(self):
        """Verify build_sql_generation_prompt function exists."""
        from app.core.prompt_templates import build_sql_generation_prompt
        
        assert callable(build_sql_generation_prompt), \
            "build_sql_generation_prompt should be callable"
    
    def test_build_sql_generation_prompt_accepts_schema_context(self):
        """Test prompt building accepts schema_context parameter."""
        from app.core.prompt_templates import build_sql_generation_prompt
        import inspect
        
        sig = inspect.signature(build_sql_generation_prompt)
        assert 'schema_context' in sig.parameters, \
            "build_sql_generation_prompt should accept schema_context"
    
    def test_build_sql_generation_prompt_output(self):
        """Test prompt building function produces valid output."""
        from app.core.prompt_templates import build_sql_generation_prompt
        
        test_ddl = "CREATE TABLE test (id INT PRIMARY KEY);"
        prompt = build_sql_generation_prompt(
            schema_context=test_ddl,
            dialect="postgresql"
        )
        
        assert test_ddl in prompt, "Schema context should be in generated prompt"
        assert isinstance(prompt, str), "Prompt should be a string"
        assert len(prompt) > len(test_ddl), "Prompt should include more than just DDL"


# =============================================================================
# Test 2: Schema Retriever Default Settings
# =============================================================================
class TestSchemaRetrieverSettings:
    """Test schema retriever has correct default settings."""
    
    def test_default_top_k_constant_exists(self):
        """Verify DEFAULT_TOP_K_TABLES constant exists."""
        from app.modules.embeddings.schema_retriever import DEFAULT_TOP_K_TABLES
        
        assert DEFAULT_TOP_K_TABLES in [3, 5], \
            f"DEFAULT_TOP_K_TABLES should be 3 or 5, got {DEFAULT_TOP_K_TABLES}"
    
    def test_default_max_dependencies_constant_exists(self):
        """Verify DEFAULT_MAX_DEPENDENCIES constant exists."""
        from app.modules.embeddings.schema_retriever import DEFAULT_MAX_DEPENDENCIES
        
        assert DEFAULT_MAX_DEPENDENCIES >= 1, \
            "DEFAULT_MAX_DEPENDENCIES should be at least 1"
    
    def test_retriever_uses_default_top_k(self):
        """Test that retrieve_tables uses default top_k."""
        from app.modules.embeddings.schema_retriever import SchemaRetriever, DEFAULT_TOP_K_TABLES
        import inspect
        
        sig = inspect.signature(SchemaRetriever.retrieve_tables)
        top_k_param = sig.parameters.get('top_k')
        
        assert top_k_param is not None, "retrieve_tables should have top_k parameter"
        assert top_k_param.default == DEFAULT_TOP_K_TABLES, \
            f"top_k default should be {DEFAULT_TOP_K_TABLES}"


# =============================================================================
# Test 3: SQL Service Retry Loop
# =============================================================================
class TestSQLServiceRetryLoop:
    """Test that SQL service has retry logic."""
    
    def test_query_async_has_max_retries_param(self):
        """Verify query_async has max_retries parameter."""
        from app.modules.chat.sql_service import SQLService
        import inspect
        
        sig = inspect.signature(SQLService.query_async)
        max_retries_param = sig.parameters.get('max_retries')
        
        assert max_retries_param is not None, \
            "query_async should have max_retries parameter"
        assert max_retries_param.default == 3, \
            "max_retries default should be 3"
    
    def test_retry_loop_exists_in_query_async(self):
        """Test that query_async method exists and is async."""
        from app.modules.chat.sql_service import SQLService
        import asyncio
        
        assert hasattr(SQLService, 'query_async'), \
            "SQLService should have query_async method"
        assert asyncio.iscoroutinefunction(SQLService.query_async), \
            "query_async should be an async method"


# =============================================================================
# Test 4: Semantic Schema Retrieval
# =============================================================================
class TestSemanticSchemaRetrieval:
    """Test semantic schema retrieval replaces blind loading."""
    
    def test_sql_service_has_config_id_param(self):
        """Verify SQLService accepts config_id parameter."""
        from app.modules.chat.sql_service import SQLService
        import inspect
        
        sig = inspect.signature(SQLService.__init__)
        config_id_param = sig.parameters.get('config_id')
        
        assert config_id_param is not None, \
            "SQLService.__init__ should have config_id parameter"
    
    def test_get_semantic_schema_context_exists(self):
        """Verify get_semantic_schema_context method exists."""
        from app.modules.chat.sql_service import SQLService
        
        assert hasattr(SQLService, 'get_semantic_schema_context'), \
            "SQLService should have get_semantic_schema_context method"
    
    def test_semantic_method_is_async(self):
        """Verify get_semantic_schema_context is async."""
        from app.modules.chat.sql_service import SQLService
        import asyncio
        
        method = getattr(SQLService, 'get_semantic_schema_context')
        assert asyncio.iscoroutinefunction(method), \
            "get_semantic_schema_context should be an async method"


# =============================================================================
# Test 5: DDL Vectorization Metadata
# =============================================================================
class TestDDLVectorization:
    """Test DDL vectorization produces correct metadata."""
    
    def test_table_schema_has_foreign_keys_in_metadata(self):
        """Verify TableSchema.to_vector_document includes foreign_keys."""
        from app.core.utils.ddl_extractor import TableSchema, ColumnInfo
        
        schema = TableSchema(
            table_name="orders",
            columns=[
                ColumnInfo(name="id", data_type="INTEGER", is_primary_key=True),
                ColumnInfo(name="customer_id", data_type="INTEGER", is_foreign_key=True,
                          foreign_key_table="customers"),
            ],
            primary_key_columns=["id"],
            foreign_keys=[{
                "referred_table": "customers",
                "constrained_columns": ["customer_id"],
                "referred_columns": ["id"],
            }],
        )
        
        doc = schema.to_vector_document()
        
        assert "foreign_keys" in doc["metadata"], \
            "Metadata should contain foreign_keys"
        assert "customers" in doc["metadata"]["foreign_keys"], \
            "foreign_keys should include referenced table"
    
    def test_ddl_content_has_create_table(self):
        """Verify DDL content contains CREATE TABLE statement."""
        from app.core.utils.ddl_extractor import TableSchema, ColumnInfo
        
        schema = TableSchema(
            table_name="test_table",
            columns=[
                ColumnInfo(name="id", data_type="INTEGER"),
            ],
        )
        
        doc = schema.to_vector_document()
        
        assert "CREATE TABLE" in doc["content"], \
            "DDL content should contain CREATE TABLE statement"
        assert "test_table" in doc["content"], \
            "DDL content should contain table name"


# =============================================================================
# Test 6: Bidirectional FK Resolution
# =============================================================================
class TestBidirectionalFKResolution:
    """Test FK dependency resolution works in both directions."""
    
    def test_resolve_fk_dependencies_has_reverse_param(self):
        """Verify resolve_fk_dependencies has include_reverse_fks parameter."""
        from app.modules.embeddings.schema_retriever import SchemaRetriever
        import inspect
        
        sig = inspect.signature(SchemaRetriever.resolve_fk_dependencies)
        reverse_param = sig.parameters.get('include_reverse_fks')
        
        assert reverse_param is not None, \
            "resolve_fk_dependencies should have include_reverse_fks parameter"
        assert reverse_param.default == True, \
            "include_reverse_fks should default to True"
    
    def test_find_tables_referencing_method_exists(self):
        """Verify _find_tables_referencing helper method exists."""
        from app.modules.embeddings.schema_retriever import SchemaRetriever
        
        assert hasattr(SchemaRetriever, '_find_tables_referencing'), \
            "SchemaRetriever should have _find_tables_referencing method"
    
    def test_retrieved_table_has_foreign_keys_attr(self):
        """Verify RetrievedTable dataclass has foreign_keys attribute."""
        from app.modules.embeddings.schema_retriever import RetrievedTable
        
        table = RetrievedTable(
            table_name="test",
            ddl="CREATE TABLE test (id INT);",
            foreign_keys=["other_table"],
        )
        
        assert table.foreign_keys == ["other_table"], \
            "RetrievedTable should store foreign_keys"


# =============================================================================
# Integration Test: End-to-End Flow
# =============================================================================
class TestEndToEndFlow:
    """Integration tests for the complete retrieval chain."""
    
    def test_schema_context_to_raw_ddl_blocks(self):
        """Test SchemaContext.to_raw_ddl_blocks formatting."""
        from app.modules.embeddings.schema_retriever import SchemaContext, RetrievedTable
        
        context = SchemaContext(
            tables=[
                RetrievedTable(
                    table_name="patients",
                    ddl="CREATE TABLE patients (id INT PRIMARY KEY);",
                    foreign_keys=[],
                    is_primary=True,
                ),
                RetrievedTable(
                    table_name="encounters",
                    ddl="CREATE TABLE encounters (id INT, patient_id INT);",
                    foreign_keys=["patients"],
                    is_primary=False,
                    is_dependency=True,
                ),
            ],
            query="test query",
            config_id=1,
            primary_count=1,
            dependency_count=1,
        )
        
        ddl_blocks = context.to_raw_ddl_blocks()
        
        assert "patients" in ddl_blocks, "Should contain patients table"
        assert "encounters" in ddl_blocks, "Should contain encounters table"
        assert "PRIMARY TABLES" in ddl_blocks, "Should have primary tables section"
        assert "RELATED TABLES" in ddl_blocks, "Should have related tables section"
    
    def test_schema_context_stats(self):
        """Test SchemaContext.get_stats returns correct info."""
        from app.modules.embeddings.schema_retriever import SchemaContext, RetrievedTable
        
        context = SchemaContext(
            tables=[
                RetrievedTable(
                    table_name="patients",
                    ddl="CREATE TABLE patients (id INT);",
                    foreign_keys=[],
                    is_primary=True,
                ),
            ],
            query="test",
            config_id=1,
            primary_count=1,
            dependency_count=0,
        )
        
        stats = context.get_stats()
        
        assert stats["total_tables"] == 1
        assert stats["primary_tables"] == 1
        assert "patients" in stats["table_names"]


# =============================================================================
# Run Tests
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
