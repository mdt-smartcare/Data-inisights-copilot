"""
Tests for connector.py to increase code coverage.
"""
from unittest.mock import patch, MagicMock, mock_open
import yaml


class TestDatabaseConnectorClass:
    """Tests for DatabaseConnector class."""
    
    def test_database_connector_import(self):
        """Test DatabaseConnector can be imported."""
        from backend.connector import DatabaseConnector
        assert DatabaseConnector is not None
    
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({'db': 'test'}))
    @patch('backend.connector.load_dotenv')
    def test_database_connector_init(self, mock_dotenv, mock_file):
        """Test DatabaseConnector initialization."""
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        assert connector is not None
        assert connector.engine is None
        assert connector.connection is None
        assert connector.is_connected is False


class TestDatabaseConnectorMethods:
    """Tests for DatabaseConnector methods."""
    
    def test_load_config_method_exists(self):
        """Test _load_config method exists."""
        from backend.connector import DatabaseConnector
        assert hasattr(DatabaseConnector, '_load_config')
    
    def test_connect_method_exists(self):
        """Test connect method exists."""
        from backend.connector import DatabaseConnector
        assert hasattr(DatabaseConnector, 'connect')
    
    def test_disconnect_method_exists(self):
        """Test disconnect method exists."""
        from backend.connector import DatabaseConnector
        assert hasattr(DatabaseConnector, 'disconnect')
    
    def test_execute_query_method_exists(self):
        """Test execute_query method exists."""
        from backend.connector import DatabaseConnector
        assert hasattr(DatabaseConnector, 'execute_query')
    
    def test_get_all_tables_method_exists(self):
        """Test get_all_tables method exists."""
        from backend.connector import DatabaseConnector
        assert hasattr(DatabaseConnector, 'get_all_tables')


class TestDatabaseConnectorLoadConfig:
    """Tests for _load_config method."""
    
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({'host': 'localhost'}))
    @patch('backend.connector.load_dotenv')
    def test_load_config_success(self, mock_dotenv, mock_file):
        """Test _load_config loads yaml file."""
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        assert connector.config is not None
        assert connector.config.get('host') == 'localhost'
    
    @patch('builtins.open', side_effect=FileNotFoundError)
    @patch('backend.connector.load_dotenv')
    def test_load_config_file_not_found(self, mock_dotenv, mock_file):
        """Test _load_config handles missing file."""
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        assert connector.config is None


class TestDatabaseConnectorConnect:
    """Tests for connect method."""
    
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({}))
    @patch('backend.connector.load_dotenv')
    @patch('backend.connector.os.getenv')
    def test_connect_no_database_url(self, mock_getenv, mock_dotenv, mock_file):
        """Test connect fails without DATABASE_URL."""
        mock_getenv.return_value = None
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        result = connector.connect()
        assert result is False
    
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({}))
    @patch('backend.connector.load_dotenv')
    @patch('backend.connector.os.getenv')
    @patch('backend.connector.create_engine')
    def test_connect_success(self, mock_engine, mock_getenv, mock_dotenv, mock_file):
        """Test connect succeeds with valid config."""
        mock_getenv.return_value = 'postgresql://localhost/test'
        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value = mock_conn
        
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        result = connector.connect()
        
        assert result is True
        assert connector.is_connected is True


class TestDatabaseConnectorDisconnect:
    """Tests for disconnect method."""
    
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({}))
    @patch('backend.connector.load_dotenv')
    def test_disconnect_no_connection(self, mock_dotenv, mock_file):
        """Test disconnect when not connected."""
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        connector.disconnect()
        assert connector.is_connected is False
    
    @patch('builtins.open', new_callable=mock_open, read_data=yaml.dump({}))
    @patch('backend.connector.load_dotenv')
    def test_disconnect_with_connection(self, mock_dotenv, mock_file):
        """Test disconnect closes connection."""
        from backend.connector import DatabaseConnector
        connector = DatabaseConnector()
        connector.connection = MagicMock()
        connector.engine = MagicMock()
        connector.is_connected = True
        
        connector.disconnect()
        
        connector.connection.close.assert_called_once()
        connector.engine.dispose.assert_called_once()
        assert connector.is_connected is False


class TestDatabaseConnectorSingleton:
    """Tests for singleton instance."""
    
    def test_db_connector_singleton_exists(self):
        """Test db_connector singleton is created."""
        from backend.connector import db_connector
        assert db_connector is not None


class TestConnectorImports:
    """Tests for connector module imports."""
    
    def test_create_engine_import(self):
        """Test create_engine is imported."""
        from backend.connector import create_engine
        assert create_engine is not None
    
    def test_text_import(self):
        """Test text is imported."""
        from backend.connector import text
        assert text is not None
    
    def test_yaml_import(self):
        """Test yaml is imported."""
        from backend.connector import yaml
        assert yaml is not None
    
    def test_load_dotenv_import(self):
        """Test load_dotenv is imported."""
        from backend.connector import load_dotenv
        assert load_dotenv is not None
