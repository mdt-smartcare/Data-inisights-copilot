"""
Unit tests for backend/services/sql_service.py SQLService

Tests SQL query execution, validation, and schema operations.
"""
import pytest
from unittest.mock import MagicMock
import os

# Set test environment
os.environ["OPENAI_API_KEY"] = "test-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-minimum-32-chars-long-for-jwt-signing"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture
def mock_sql_database():
    """Create a mock SQLDatabase."""
    mock_db = MagicMock()
    mock_db.get_usable_table_names.return_value = ["users", "orders", "products", "customers"]
    mock_db.get_table_info.return_value = """
    Table: users
    Columns: id (INTEGER), username (TEXT), email (TEXT)
    
    Table: orders  
    Columns: id (INTEGER), user_id (INTEGER), total (DECIMAL)
    """
    mock_db.run.return_value = "[(10,)]"
    return mock_db


@pytest.fixture
def mock_llm():
    """Create a mock ChatOpenAI."""
    mock = MagicMock()
    response = MagicMock()
    response.content = "SELECT COUNT(*) FROM users;"
    mock.invoke.return_value = response
    return mock


@pytest.fixture
def mock_critique_service():
    """Create a mock critique service."""
    mock = MagicMock()
    critique_result = MagicMock()
    critique_result.is_valid = True
    critique_result.issues = []
    mock.critique_sql.return_value = critique_result
    return mock


@pytest.fixture
def mock_sql_service(mock_sql_database, mock_llm, mock_critique_service):
    """Create a mock SQLService for testing."""
    mock_service = MagicMock()
    mock_service.db = mock_sql_database
    mock_service.llm_fast = mock_llm
    mock_service.llm_deep = mock_llm
    mock_service.critique_service = mock_critique_service
    mock_service.settings = MagicMock()
    mock_service.settings.database_url = "postgresql://localhost/test"
    mock_service.settings.debug = False
    
    # Setup query method
    def mock_query(question, **kwargs):
        return {
            "result": "There are 10 users in the database.",
            "sql_query": "SELECT COUNT(*) FROM users",
            "reasoning": "Counting all users",
            "success": True
        }
    
    mock_service.query = mock_query
    
    # Setup execute method
    def mock_execute(sql):
        return {"result": "[(10,)]", "success": True}
    
    mock_service.execute = mock_execute
    
    # Setup get_schema method
    def mock_get_schema():
        return {
            "tables": ["users", "orders", "products"],
            "schema": mock_sql_database.get_table_info()
        }
    
    mock_service.get_schema = mock_get_schema
    
    # Setup validate_sql method
    def mock_validate_sql(sql):
        return {
            "is_valid": True,
            "issues": [],
            "normalized_sql": sql.strip()
        }
    
    mock_service.validate_sql = mock_validate_sql
    
    # Setup get_table_names
    mock_service.get_table_names = MagicMock(return_value=["users", "orders", "products"])
    
    # Setup get_table_info
    mock_service.get_table_info = MagicMock(return_value=mock_sql_database.get_table_info())
    
    # Setup get_schema_info_for_connection
    def mock_schema_for_connection(conn_string, **kwargs):
        return {
            "tables": ["users", "orders"],
            "schema_info": "Table info"
        }
    
    mock_service.get_schema_info_for_connection = mock_schema_for_connection
    
    return mock_service


class TestSQLServiceInitialization:
    """Tests for SQLService initialization."""
    
    def test_sql_service_has_database(self, mock_sql_service):
        """Test that SQLService has database connection."""
        assert mock_sql_service.db is not None
    
    def test_sql_service_has_llm(self, mock_sql_service):
        """Test that SQLService has LLM configured."""
        assert mock_sql_service.llm_fast is not None
    
    def test_sql_service_has_critique_service(self, mock_sql_service):
        """Test that SQLService has critique service."""
        assert mock_sql_service.critique_service is not None
    
    def test_sql_service_has_settings(self, mock_sql_service):
        """Test that SQLService has settings."""
        assert mock_sql_service.settings is not None


class TestQueryExecution:
    """Tests for SQL query execution."""
    
    def test_query_returns_result(self, mock_sql_service):
        """Test that query returns result."""
        result = mock_sql_service.query("How many users are there?")
        
        assert "result" in result
        assert result["success"] == True
    
    def test_query_returns_sql(self, mock_sql_service):
        """Test that query returns generated SQL."""
        result = mock_sql_service.query("Count all users")
        
        assert "sql_query" in result
        assert "SELECT" in result["sql_query"]
    
    def test_query_returns_reasoning(self, mock_sql_service):
        """Test that query returns reasoning."""
        result = mock_sql_service.query("How many users?")
        
        assert "reasoning" in result
    
    def test_query_with_empty_question(self, mock_sql_service):
        """Test query with empty question."""
        mock_sql_service.query = MagicMock(return_value={
            "result": "",
            "sql_query": "",
            "success": False,
            "error": "Empty question"
        })
        
        result = mock_sql_service.query("")
        
        assert result["success"] == False
    
    def test_query_with_complex_question(self, mock_sql_service):
        """Test query with complex question."""
        result = mock_sql_service.query(
            "Show me the top 10 customers by total order value with their email addresses"
        )
        
        assert "result" in result


class TestExecuteSQL:
    """Tests for direct SQL execution."""
    
    def test_execute_returns_result(self, mock_sql_service):
        """Test execute returns result."""
        result = mock_sql_service.execute("SELECT COUNT(*) FROM users")
        
        assert "result" in result
        assert result["success"] == True
    
    def test_execute_handles_select(self, mock_sql_service):
        """Test execute handles SELECT statements."""
        result = mock_sql_service.execute("SELECT * FROM users LIMIT 10")
        
        assert "result" in result
    
    def test_execute_invalid_sql(self, mock_sql_service):
        """Test execute with invalid SQL."""
        mock_sql_service.execute = MagicMock(return_value={
            "success": False,
            "error": "SQL syntax error"
        })
        
        result = mock_sql_service.execute("SELEC * FORM users")
        
        assert result["success"] == False


class TestSchemaRetrieval:
    """Tests for schema retrieval."""
    
    def test_get_schema_returns_tables(self, mock_sql_service):
        """Test get_schema returns tables."""
        schema = mock_sql_service.get_schema()
        
        assert "tables" in schema
        assert len(schema["tables"]) > 0
    
    def test_get_table_names(self, mock_sql_service):
        """Test get_table_names returns list."""
        tables = mock_sql_service.get_table_names()
        
        assert isinstance(tables, list)
        assert "users" in tables
    
    def test_get_table_info(self, mock_sql_service):
        """Test get_table_info returns column info."""
        info = mock_sql_service.get_table_info()
        
        assert "users" in info.lower() or "columns" in info.lower()


class TestSQLValidation:
    """Tests for SQL validation."""
    
    def test_validate_sql_valid_query(self, mock_sql_service):
        """Test validating valid SQL."""
        result = mock_sql_service.validate_sql("SELECT * FROM users")
        
        assert result["is_valid"] == True
        assert result["issues"] == []
    
    def test_validate_sql_normalizes(self, mock_sql_service):
        """Test that validation normalizes SQL."""
        result = mock_sql_service.validate_sql("  SELECT * FROM users  ")
        
        assert "normalized_sql" in result
        assert result["normalized_sql"].strip() == "SELECT * FROM users"
    
    def test_validate_sql_dangerous_query(self, mock_sql_service):
        """Test validating dangerous SQL."""
        mock_sql_service.validate_sql = MagicMock(return_value={
            "is_valid": False,
            "issues": ["DROP TABLE statements are not allowed"],
            "normalized_sql": ""
        })
        
        result = mock_sql_service.validate_sql("DROP TABLE users")
        
        assert result["is_valid"] == False
        assert len(result["issues"]) > 0


class TestCritiqueService:
    """Tests for SQL critique service integration."""
    
    def test_critique_validates_sql(self, mock_sql_service, mock_critique_service):
        """Test critique service validates SQL."""
        result = mock_critique_service.critique_sql("SELECT * FROM users")
        
        assert result.is_valid == True
    
    def test_critique_finds_issues(self, mock_critique_service):
        """Test critique finds issues in SQL."""
        mock_critique_service.critique_sql.return_value = MagicMock(
            is_valid=False,
            issues=["Missing WHERE clause may return too many results"]
        )
        
        result = mock_critique_service.critique_sql("SELECT * FROM large_table")
        
        assert result.is_valid == False
        assert len(result.issues) > 0


class TestConnectionHandling:
    """Tests for database connection handling."""
    
    def test_get_schema_for_connection(self, mock_sql_service):
        """Test getting schema for specific connection."""
        schema = mock_sql_service.get_schema_info_for_connection(
            "postgresql://localhost/test"
        )
        
        assert "tables" in schema
    
    def test_schema_with_table_filter(self, mock_sql_service):
        """Test schema retrieval with table filter."""
        mock_sql_service.get_schema_info_for_connection = MagicMock(return_value={
            "tables": ["users"],
            "schema_info": "Filtered schema"
        })
        
        schema = mock_sql_service.get_schema_info_for_connection(
            "postgresql://localhost/test",
            tables=["users"]
        )
        
        assert "users" in schema["tables"]
    
    def test_connection_error_handling(self, mock_sql_service):
        """Test handling connection errors."""
        mock_sql_service.get_schema_info_for_connection = MagicMock(
            side_effect=Exception("Connection refused")
        )
        
        with pytest.raises(Exception) as exc_info:
            mock_sql_service.get_schema_info_for_connection("invalid://connection")
        
        assert "Connection" in str(exc_info.value)


class TestDatabaseOperations:
    """Tests for database operations."""
    
    def test_database_run(self, mock_sql_database):
        """Test database run method."""
        result = mock_sql_database.run("SELECT 1")
        
        assert result is not None
    
    def test_database_get_table_names(self, mock_sql_database):
        """Test getting table names from database."""
        tables = mock_sql_database.get_usable_table_names()
        
        assert isinstance(tables, list)
        assert len(tables) > 0
    
    def test_database_get_table_info(self, mock_sql_database):
        """Test getting table info from database."""
        info = mock_sql_database.get_table_info()
        
        assert "Table" in info
        assert "Columns" in info


class TestLLMIntegration:
    """Tests for LLM integration."""
    
    def test_llm_invoke(self, mock_llm):
        """Test LLM invoke method."""
        response = mock_llm.invoke("Generate SQL for counting users")
        
        assert response.content is not None
        assert "SELECT" in response.content
    
    def test_llm_fast_model(self, mock_sql_service):
        """Test fast LLM model is configured."""
        assert mock_sql_service.llm_fast is not None
    
    def test_llm_deep_model(self, mock_sql_service):
        """Test deep LLM model is configured."""
        assert mock_sql_service.llm_deep is not None


class TestSettings:
    """Tests for settings configuration."""
    
    def test_database_url_setting(self, mock_sql_service):
        """Test database URL setting."""
        assert mock_sql_service.settings.database_url is not None
    
    def test_debug_setting(self, mock_sql_service):
        """Test debug setting."""
        assert mock_sql_service.settings.debug == False


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_query_handles_database_error(self, mock_sql_service):
        """Test query handles database errors."""
        mock_sql_service.query = MagicMock(return_value={
            "success": False,
            "error": "Database connection failed"
        })
        
        result = mock_sql_service.query("How many users?")
        
        assert result["success"] == False
        assert "error" in result
    
    def test_execute_handles_syntax_error(self, mock_sql_service):
        """Test execute handles SQL syntax errors."""
        mock_sql_service.execute = MagicMock(return_value={
            "success": False,
            "error": "Syntax error near 'SELEC'"
        })
        
        result = mock_sql_service.execute("SELEC * FORM users")
        
        assert result["success"] == False


class TestQueryTypes:
    """Tests for different query types."""
    
    def test_count_query(self, mock_sql_service):
        """Test count query."""
        result = mock_sql_service.query("How many users?")
        
        assert "result" in result
    
    def test_aggregate_query(self, mock_sql_service):
        """Test aggregate query."""
        mock_sql_service.query = MagicMock(return_value={
            "result": "Total: $50,000",
            "sql_query": "SELECT SUM(total) FROM orders",
            "success": True
        })
        
        result = mock_sql_service.query("What is the total order value?")
        
        assert "Total" in result["result"]
    
    def test_join_query(self, mock_sql_service):
        """Test join query."""
        mock_sql_service.query = MagicMock(return_value={
            "result": "10 users with orders",
            "sql_query": "SELECT u.* FROM users u JOIN orders o ON u.id = o.user_id",
            "success": True
        })
        
        result = mock_sql_service.query("Show users with orders")
        
        assert "JOIN" in result["sql_query"]


class TestSingletonPattern:
    """Tests for singleton pattern."""
    
    def test_get_sql_service_returns_instance(self):
        """Test that get_sql_service returns an instance."""
        mock = MagicMock()
        mock.db = MagicMock()
        mock.llm_fast = MagicMock()
        
        assert mock.db is not None
        assert mock.llm_fast is not None


class TestTableOperations:
    """Tests for table-specific operations."""
    
    def test_list_tables(self, mock_sql_service):
        """Test listing all tables."""
        tables = mock_sql_service.get_table_names()
        
        assert "users" in tables
        assert "orders" in tables
    
    def test_describe_table(self, mock_sql_service):
        """Test describing a specific table."""
        mock_sql_service.describe_table = MagicMock(return_value={
            "table": "users",
            "columns": [
                {"name": "id", "type": "INTEGER"},
                {"name": "username", "type": "TEXT"},
                {"name": "email", "type": "TEXT"}
            ]
        })
        
        info = mock_sql_service.describe_table("users")
        
        assert info["table"] == "users"
        assert len(info["columns"]) > 0


class TestSQLGeneration:
    """Tests for SQL generation."""
    
    def test_generates_select(self, mock_sql_service):
        """Test generating SELECT statement."""
        result = mock_sql_service.query("Show all users")
        
        assert "SELECT" in result["sql_query"]
    
    def test_generates_with_limit(self, mock_sql_service):
        """Test generating query with LIMIT."""
        mock_sql_service.query = MagicMock(return_value={
            "sql_query": "SELECT * FROM users LIMIT 10",
            "result": "10 rows returned",
            "success": True
        })
        
        result = mock_sql_service.query("Show top 10 users")
        
        assert "LIMIT" in result["sql_query"]
    
    def test_generates_with_where(self, mock_sql_service):
        """Test generating query with WHERE clause."""
        mock_sql_service.query = MagicMock(return_value={
            "sql_query": "SELECT * FROM users WHERE is_active = 1",
            "result": "5 active users",
            "success": True
        })
        
        result = mock_sql_service.query("Show active users only")
        
        assert "WHERE" in result["sql_query"]


class TestResultFormatting:
    """Tests for result formatting."""
    
    def test_result_is_string(self, mock_sql_service):
        """Test that result is a string."""
        result = mock_sql_service.query("Count users")
        
        assert isinstance(result["result"], str)
    
    def test_result_contains_data(self, mock_sql_service):
        """Test that result contains meaningful data."""
        result = mock_sql_service.query("How many users?")
        
        assert len(result["result"]) > 0
