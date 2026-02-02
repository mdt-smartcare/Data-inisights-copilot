"""
Unit tests for backend/sqliteDb/db.py DatabaseService

Tests user CRUD, authentication, prompt management, and connection management.
"""
import pytest
import tempfile
import os


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    # Create temp file
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    yield path
    
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def db_service(temp_db):
    """Create a DatabaseService instance with temporary database."""
    from backend.sqliteDb.db import DatabaseService
    
    # Temporarily override admin password env to avoid issues
    original_admin = os.environ.get('ADMIN_PASSWORD')
    os.environ['ADMIN_PASSWORD'] = 'test_admin_pass'
    
    service = DatabaseService(db_path=temp_db)
    
    # Restore original
    if original_admin:
        os.environ['ADMIN_PASSWORD'] = original_admin
    elif 'ADMIN_PASSWORD' in os.environ:
        del os.environ['ADMIN_PASSWORD']
    
    return service


class TestDatabaseServiceInitialization:
    """Tests for DatabaseService initialization."""
    
    def test_init_creates_database_file(self, temp_db):
        """Test that initialization creates database file."""
        from backend.sqliteDb.db import DatabaseService
        
        os.unlink(temp_db)  # Remove file so we can test creation
        assert not os.path.exists(temp_db)
        
        _ = DatabaseService(db_path=temp_db)
        
        assert os.path.exists(temp_db)
    
    def test_init_creates_users_table(self, db_service, temp_db):
        """Test that initialization creates users table."""
        import sqlite3
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
        assert result[0] == 'users'
    
    def test_init_creates_system_prompts_table(self, db_service, temp_db):
        """Test that initialization creates system_prompts table."""
        import sqlite3
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_prompts'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
    
    def test_init_creates_db_connections_table(self, db_service, temp_db):
        """Test that initialization creates db_connections table."""
        import sqlite3
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='db_connections'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None
    
    def test_init_creates_default_admin_user(self, temp_db):
        """Test that initialization creates default admin user."""
        from backend.sqliteDb.db import DatabaseService
        
        os.environ['ADMIN_USERNAME'] = 'testadmin'
        os.environ['ADMIN_PASSWORD'] = 'testpass123'
        os.environ['ADMIN_EMAIL'] = 'admin@test.com'
        
        service = DatabaseService(db_path=temp_db)
        user = service.get_user_by_username('testadmin')
        
        assert user is not None
        assert user['username'] == 'testadmin'
        assert user['role'] == 'super_admin'
        
        # Cleanup env vars
        del os.environ['ADMIN_USERNAME']
        del os.environ['ADMIN_PASSWORD']
        del os.environ['ADMIN_EMAIL']


class TestPasswordHashing:
    """Tests for DatabaseService password hashing."""
    
    def test_hash_password_returns_string(self, db_service):
        """Test that hash_password returns a string."""
        hashed = db_service.hash_password("testpassword")
        
        assert isinstance(hashed, str)
        assert len(hashed) > 0
    
    def test_hash_password_is_bcrypt(self, db_service):
        """Test that hash uses bcrypt format."""
        hashed = db_service.hash_password("testpassword")
        
        # Bcrypt hashes start with $2a$, $2b$, or $2y$
        assert hashed.startswith(("$2a$", "$2b$", "$2y$"))
    
    def test_verify_password_correct(self, db_service):
        """Test password verification with correct password."""
        password = "mysecretpassword"
        hashed = db_service.hash_password(password)
        
        assert db_service.verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self, db_service):
        """Test password verification with wrong password."""
        password = "mysecretpassword"
        hashed = db_service.hash_password(password)
        
        assert db_service.verify_password("wrongpassword", hashed) is False
    
    def test_hash_password_unique_salts(self, db_service):
        """Test that same password produces different hashes (random salt)."""
        password = "samepassword"
        hash1 = db_service.hash_password(password)
        hash2 = db_service.hash_password(password)
        
        assert hash1 != hash2
        # But both should verify
        assert db_service.verify_password(password, hash1)
        assert db_service.verify_password(password, hash2)


class TestUserCreation:
    """Tests for user creation."""
    
    def test_create_user_basic(self, db_service):
        """Test basic user creation."""
        user = db_service.create_user(
            username="newuser",
            password="password123",
            email="newuser@test.com"
        )
        
        assert user['username'] == "newuser"
        assert user['email'] == "newuser@test.com"
        assert user['role'] == "user"
        assert 'id' in user
    
    def test_create_user_with_full_name(self, db_service):
        """Test user creation with full name."""
        user = db_service.create_user(
            username="johndoe",
            password="pass123",
            email="john@test.com",
            full_name="John Doe"
        )
        
        assert user['full_name'] == "John Doe"
    
    def test_create_user_with_role(self, db_service):
        """Test user creation with specific role."""
        user = db_service.create_user(
            username="editor1",
            password="pass123",
            email="editor@test.com",
            role="editor"
        )
        
        assert user['role'] == "editor"
    
    def test_create_user_duplicate_username_raises(self, db_service):
        """Test that duplicate username raises ValueError."""
        db_service.create_user(username="uniqueuser", password="pass123")
        
        with pytest.raises(ValueError) as exc_info:
            db_service.create_user(username="uniqueuser", password="pass456")
        
        assert "already exists" in str(exc_info.value)
    
    def test_create_user_duplicate_email_raises(self, db_service):
        """Test that duplicate email raises ValueError."""
        db_service.create_user(
            username="user1",
            password="pass123",
            email="same@test.com"
        )
        
        with pytest.raises(ValueError) as exc_info:
            db_service.create_user(
                username="user2",
                password="pass456",
                email="same@test.com"
            )
        
        assert "already exists" in str(exc_info.value)
    
    def test_create_user_no_email(self, db_service):
        """Test user creation without email."""
        user = db_service.create_user(
            username="nomail",
            password="pass123"
        )
        
        assert user['username'] == "nomail"
        assert user['email'] is None


class TestUserRetrieval:
    """Tests for user retrieval."""
    
    def test_get_user_by_username_exists(self, db_service):
        """Test retrieving existing user."""
        db_service.create_user(
            username="findme",
            password="pass123",
            email="find@test.com"
        )
        
        user = db_service.get_user_by_username("findme")
        
        assert user is not None
        assert user['username'] == "findme"
        assert 'password_hash' in user  # Should include hash for auth
    
    def test_get_user_by_username_not_found(self, db_service):
        """Test retrieving non-existent user returns None."""
        user = db_service.get_user_by_username("nonexistent")
        
        assert user is None
    
    def test_get_user_includes_role(self, db_service):
        """Test that retrieved user includes role."""
        db_service.create_user(
            username="roleuser",
            password="pass123",
            role="editor"
        )
        
        user = db_service.get_user_by_username("roleuser")
        
        assert user['role'] == "editor"


class TestAuthentication:
    """Tests for user authentication."""
    
    def test_authenticate_user_success(self, db_service):
        """Test successful authentication."""
        db_service.create_user(
            username="authuser",
            password="correctpass"
        )
        
        result = db_service.authenticate_user("authuser", "correctpass")
        
        assert result is not None
        assert result['username'] == "authuser"
        assert 'password_hash' not in result  # Should not expose hash
    
    def test_authenticate_user_wrong_password(self, db_service):
        """Test authentication with wrong password."""
        db_service.create_user(
            username="authuser2",
            password="correctpass"
        )
        
        result = db_service.authenticate_user("authuser2", "wrongpass")
        
        assert result is None
    
    def test_authenticate_user_not_found(self, db_service):
        """Test authentication with non-existent user."""
        result = db_service.authenticate_user("ghostuser", "anypass")
        
        assert result is None
    
    def test_authenticate_inactive_user_fails(self, db_service, temp_db):
        """Test that inactive user cannot authenticate."""
        db_service.create_user(
            username="inactive",
            password="pass123"
        )
        
        # Manually deactivate user
        import sqlite3
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?", ("inactive",))
        conn.commit()
        conn.close()
        
        result = db_service.authenticate_user("inactive", "pass123")
        
        assert result is None


class TestDatabaseConnections:
    """Tests for database connection management."""
    
    def test_add_db_connection(self, db_service):
        """Test adding a database connection."""
        conn_id = db_service.add_db_connection(
            name="TestDB",
            uri="postgresql://user:pass@localhost/db",
            engine_type="postgresql",
            created_by="admin"
        )
        
        assert isinstance(conn_id, int)
        assert conn_id > 0
    
    def test_add_db_connection_duplicate_name_raises(self, db_service):
        """Test that duplicate connection name raises error."""
        db_service.add_db_connection(
            name="UniqueDB",
            uri="postgresql://localhost/db1"
        )
        
        with pytest.raises(ValueError) as exc_info:
            db_service.add_db_connection(
                name="UniqueDB",
                uri="postgresql://localhost/db2"
            )
        
        assert "already exists" in str(exc_info.value)
    
    def test_get_db_connections_empty(self, db_service):
        """Test getting connections when none exist."""
        connections = db_service.get_db_connections()
        
        assert isinstance(connections, list)
        assert len(connections) == 0
    
    def test_get_db_connections_multiple(self, db_service):
        """Test getting multiple connections."""
        db_service.add_db_connection(name="DB1", uri="postgresql://localhost/db1")
        db_service.add_db_connection(name="DB2", uri="postgresql://localhost/db2")
        
        connections = db_service.get_db_connections()
        
        assert len(connections) == 2
        names = [c['name'] for c in connections]
        assert "DB1" in names
        assert "DB2" in names
    
    def test_delete_db_connection(self, db_service):
        """Test deleting a database connection."""
        conn_id = db_service.add_db_connection(
            name="ToDelete",
            uri="postgresql://localhost/deletedb"
        )
        
        result = db_service.delete_db_connection(conn_id)
        
        assert result is True
        
        # Verify deleted
        connections = db_service.get_db_connections()
        assert not any(c['name'] == "ToDelete" for c in connections)
    
    def test_delete_db_connection_not_found(self, db_service):
        """Test deleting non-existent connection."""
        result = db_service.delete_db_connection(99999)
        
        assert result is False
    
    def test_get_db_connection_by_id(self, db_service):
        """Test getting connection by ID."""
        conn_id = db_service.add_db_connection(
            name="GetByID",
            uri="postgresql://localhost/getbyid"
        )
        
        conn = db_service.get_db_connection_by_id(conn_id)
        
        assert conn is not None
        assert conn['name'] == "GetByID"
        assert conn['uri'] == "postgresql://localhost/getbyid"
    
    def test_get_db_connection_by_id_not_found(self, db_service):
        """Test getting non-existent connection returns None."""
        conn = db_service.get_db_connection_by_id(99999)
        
        assert conn is None


class TestSystemPrompts:
    """Tests for system prompt management."""
    
    def test_get_latest_active_prompt_none(self, db_service):
        """Test getting active prompt when none exists."""
        result = db_service.get_latest_active_prompt()
        
        assert result is None
    
    def test_publish_system_prompt(self, db_service):
        """Test publishing a new system prompt."""
        result = db_service.publish_system_prompt(
            prompt_text="You are a helpful SQL assistant.",
            user_id="admin"
        )
        
        assert result is not None
        assert result['prompt_text'] == "You are a helpful SQL assistant."
        assert result['is_active'] == 1
        assert 'version' in result
    
    def test_publish_deactivates_previous(self, db_service):
        """Test that publishing new prompt deactivates previous."""
        db_service.publish_system_prompt(
            prompt_text="First prompt",
            user_id="admin"
        )
        
        db_service.publish_system_prompt(
            prompt_text="Second prompt",
            user_id="admin"
        )
        
        # Only second should be active
        active = db_service.get_latest_active_prompt()
        assert active == "Second prompt"
    
    def test_publish_prompt_version_increment(self, db_service):
        """Test that version number increments with each publish."""
        result1 = db_service.publish_system_prompt(
            prompt_text="Version 1",
            user_id="admin"
        )
        
        result2 = db_service.publish_system_prompt(
            prompt_text="Version 2",
            user_id="admin"
        )
        
        assert result2['version_number'] > result1['version_number']
    
    def test_get_all_prompts(self, db_service):
        """Test getting all prompt versions."""
        db_service.publish_system_prompt(prompt_text="Prompt 1", user_id="admin")
        db_service.publish_system_prompt(prompt_text="Prompt 2", user_id="admin")
        db_service.publish_system_prompt(prompt_text="Prompt 3", user_id="admin")
        
        prompts = db_service.get_all_prompts()
        
        assert len(prompts) >= 3
    
    def test_get_active_config(self, db_service):
        """Test getting active configuration."""
        db_service.publish_system_prompt(
            prompt_text="Active prompt",
            user_id="admin",
            data_dictionary="Some dictionary content"
        )
        
        config = db_service.get_active_config()
        
        assert config is not None
        assert config['prompt_text'] == "Active prompt"
        assert config['data_dictionary'] == "Some dictionary content"
    
    def test_publish_prompt_with_metadata(self, db_service):
        """Test publishing prompt with all metadata."""
        result = db_service.publish_system_prompt(
            prompt_text="Full prompt",
            user_id="admin",
            connection_id=1,
            schema_selection='{"tables": ["users"]}',
            data_dictionary="User table dictionary",
            reasoning='{"step": "selected users table"}',
            example_questions='["How many users?", "List active users"]'
        )
        
        assert result is not None
        assert result['prompt_text'] == "Full prompt"


class TestMetricsAndExamples:
    """Tests for metrics and SQL examples."""
    
    def test_get_active_metrics_empty(self, db_service):
        """Test getting metrics when table doesn't exist."""
        metrics = db_service.get_active_metrics()
        
        # Should return empty list, not raise
        assert isinstance(metrics, list)
    
    def test_get_sql_examples_empty(self, db_service):
        """Test getting SQL examples when table doesn't exist."""
        examples = db_service.get_sql_examples()
        
        # Should return empty list, not raise
        assert isinstance(examples, list)


class TestConnectionManagement:
    """Tests for database connection utility."""
    
    def test_get_connection_returns_connection(self, db_service):
        """Test that get_connection returns a valid connection."""
        conn = db_service.get_connection()
        
        assert conn is not None
        # Should be able to execute queries
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()
        
        assert result[0] == 1
    
    def test_get_connection_has_row_factory(self, db_service):
        """Test that connection has row_factory set."""
        import sqlite3
        
        conn = db_service.get_connection()
        
        # Row factory should allow dict-like access
        assert conn.row_factory == sqlite3.Row
        conn.close()


class TestSingletonPattern:
    """Tests for global database service singleton."""
    
    def test_get_db_service_returns_same_instance(self):
        """Test that get_db_service returns singleton."""
        from backend.sqliteDb.db import get_db_service
        
        service1 = get_db_service()
        service2 = get_db_service()
        
        assert service1 is service2
    
    def test_global_db_service_exists(self):
        """Test that global db_service is initialized."""
        from backend.sqliteDb.db import db_service
        
        assert db_service is not None
