"""
Unit tests for backend/pipeline/extract.py DataExtractor

Tests data extraction from database tables.
"""
import pytest
from unittest.mock import patch, mock_open
import pandas as pd
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"


@pytest.fixture
def mock_config():
    """Create mock extraction config."""
    return {
        "tables": {
            "exclude_tables": ["audit_log", "temp_data"],
            "global_exclude_columns": ["password", "secret"]
        }
    }


@pytest.fixture
def mock_config_yaml(mock_config):
    """Create mock YAML string."""
    import yaml
    return yaml.dump(mock_config)


class TestDataExtractor:
    """Tests for DataExtractor class."""
    
    def test_init_loads_config(self, mock_config, mock_config_yaml):
        """Test that extractor loads configuration on init."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            from backend.pipeline.extract import DataExtractor
            
            extractor = DataExtractor("config/test.yaml")
            
            assert extractor.config == mock_config
            assert "audit_log" in extractor.excluded_tables
    
    def test_get_allowed_tables_excludes_configured_tables(self, mock_config_yaml):
        """Test that excluded tables are filtered out."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            with patch('backend.pipeline.extract.db_connector') as mock_db:
                mock_db.get_all_tables.return_value = [
                    "users", "orders", "audit_log", "products"
                ]
                
                from backend.pipeline.extract import DataExtractor
                
                extractor = DataExtractor("config/test.yaml")
                allowed = extractor.get_allowed_tables()
                
                assert "users" in allowed
                assert "orders" in allowed
                assert "products" in allowed
                assert "audit_log" not in allowed
    
    def test_get_safe_columns_excludes_sensitive(self, mock_config_yaml):
        """Test that sensitive columns are excluded."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            with patch('backend.pipeline.extract.db_connector') as mock_db:
                mock_db.execute_query.return_value = [
                    ("id",), ("name",), ("email",), ("password",), ("secret",)
                ]
                
                from backend.pipeline.extract import DataExtractor
                
                extractor = DataExtractor("config/test.yaml")
                safe_cols = extractor.get_safe_columns("users")
                
                assert "id" in safe_cols
                assert "name" in safe_cols
                assert "email" in safe_cols
                assert "password" not in safe_cols
                assert "secret" not in safe_cols
    
    def test_extract_all_tables_returns_dataframes(self, mock_config_yaml):
        """Test that extraction returns DataFrames for each table."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            with patch('backend.pipeline.extract.db_connector') as mock_db:
                mock_db.get_all_tables.return_value = ["users"]
                mock_db.execute_query.side_effect = [
                    # First call: get columns
                    [("id",), ("name",)],
                    # Second call: select data
                    [(1, "John"), (2, "Jane")]
                ]
                
                from backend.pipeline.extract import DataExtractor
                
                extractor = DataExtractor("config/test.yaml")
                table_data = extractor.extract_all_tables()
                
                assert "users" in table_data
                assert isinstance(table_data["users"], pd.DataFrame)
                assert len(table_data["users"]) == 2
    
    def test_extract_with_limit(self, mock_config_yaml):
        """Test that table limit is applied."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            with patch('backend.pipeline.extract.db_connector') as mock_db:
                mock_db.get_all_tables.return_value = ["users"]
                mock_db.execute_query.side_effect = [
                    [("id",), ("name",)],
                    [(1, "John")]
                ]
                
                from backend.pipeline.extract import DataExtractor
                
                extractor = DataExtractor("config/test.yaml")
                _ = extractor.extract_all_tables(table_limit=10)
                
                # Verify LIMIT was added to query
                last_call = mock_db.execute_query.call_args_list[-1]
                assert "LIMIT" in last_call[0][0]
    
    def test_extract_handles_errors_gracefully(self, mock_config_yaml):
        """Test that extraction continues on error."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            with patch('backend.pipeline.extract.db_connector') as mock_db:
                mock_db.get_all_tables.return_value = ["users", "orders"]
                mock_db.execute_query.side_effect = [
                    # users columns
                    [("id",), ("name",)],
                    # users data - raises error
                    Exception("Connection lost"),
                    # orders columns
                    [("id",), ("total",)],
                    # orders data
                    [(1, 100.0)]
                ]
                
                from backend.pipeline.extract import DataExtractor
                
                extractor = DataExtractor("config/test.yaml")
                table_data = extractor.extract_all_tables()
                
                # Should have orders but not users
                assert "orders" in table_data
    
    def test_skips_tables_with_no_safe_columns(self, mock_config_yaml):
        """Test that tables with no safe columns are skipped."""
        config_all_excluded = {
            "tables": {
                "exclude_tables": [],
                "global_exclude_columns": ["id", "name"]
            }
        }
        import yaml
        config_yaml = yaml.dump(config_all_excluded)
        
        with patch("builtins.open", mock_open(read_data=config_yaml)):
            with patch('backend.pipeline.extract.db_connector') as mock_db:
                mock_db.get_all_tables.return_value = ["users"]
                mock_db.execute_query.return_value = [("id",), ("name",)]
                
                from backend.pipeline.extract import DataExtractor
                
                extractor = DataExtractor("config/test.yaml")
                table_data = extractor.extract_all_tables()
                
                assert "users" not in table_data


class TestCreateDataExtractor:
    """Tests for factory function."""
    
    def test_creates_extractor_with_default_config(self, mock_config_yaml):
        """Test factory creates extractor with default path."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)):
            from backend.pipeline.extract import create_data_extractor
            
            extractor = create_data_extractor()
            
            assert extractor is not None
    
    def test_creates_extractor_with_custom_config(self, mock_config_yaml):
        """Test factory creates extractor with custom path."""
        with patch("builtins.open", mock_open(read_data=mock_config_yaml)) as m:
            from backend.pipeline.extract import create_data_extractor
            
            create_data_extractor("custom/path.yaml")
            
            m.assert_called_with("custom/path.yaml", "r")
