"""
Unit tests for backend/sqliteDb/db.py DatabaseService

Tests user management (OIDC), prompt management, and connection management.
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
    
    service = DatabaseService(db_path=temp_db)
    
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


class TestOIDCUserManagement:
    """Tests for OIDC user management."""
    
    def test_upsert_oidc_user_creates_new(self, db_service):
        """Test creating a new user via OIDC JIT provisioning."""
        user = db_service.upsert_oidc_user(
            external_id="keycloak-sub-12345",
            email="oidcuser@test.com",
            username="oidcuser",
            full_name="OIDC User",
            default_role="user"
        )
        
        assert user is not None
        assert user['username'] == "oidcuser"
        assert user['email'] == "oidcuser@test.com"
        assert user['external_id'] == "keycloak-sub-12345"
        assert user['role'] == "user"
    
    def test_upsert_oidc_user_updates_existing(self, db_service):
        """Test that upsert updates existing OIDC user."""
        # Create user
        db_service.upsert_oidc_user(
            external_id="keycloak-sub-12345",
            email="original@test.com",
            username="oidcuser",
            full_name="Original Name",
            default_role="user"
        )
        
        # Update user
        updated = db_service.upsert_oidc_user(
            external_id="keycloak-sub-12345",
            email="updated@test.com",
            full_name="Updated Name"
        )
        
        assert updated['email'] == "updated@test.com"
        assert updated['full_name'] == "Updated Name"
    
    def test_get_user_by_external_id(self, db_service):
        """Test retrieving user by OIDC external ID."""
        db_service.upsert_oidc_user(
            external_id="keycloak-sub-findme",
            email="findme@test.com",
            username="findme"
        )
        
        user = db_service.get_user_by_external_id("keycloak-sub-findme")
        
        assert user is not None
        assert user['username'] == "findme"
    
    def test_get_user_by_external_id_not_found(self, db_service):
        """Test that missing external_id returns None."""
        user = db_service.get_user_by_external_id("nonexistent-sub")
        
        assert user is None
    
    def test_update_user_role(self, db_service):
        """Test updating a user's role."""
        user = db_service.upsert_oidc_user(
            external_id="role-test-sub",
            username="roletest",
            default_role="user"
        )
        
        result = db_service.update_user_role(user['id'], "admin")
        
        assert result is True
        
        updated = db_service.get_user_by_external_id("role-test-sub")
        assert updated['role'] == "admin"
    
    def test_list_all_users(self, db_service):
        """Test listing all users."""
        db_service.upsert_oidc_user(external_id="user1-sub", username="user1")
        db_service.upsert_oidc_user(external_id="user2-sub", username="user2")
        
        users = db_service.list_all_users()
        
        assert len(users) >= 2
        usernames = [u['username'] for u in users]
        assert "user1" in usernames
        assert "user2" in usernames
    
    def test_deactivate_user(self, db_service):
        """Test deactivating a user."""
        user = db_service.upsert_oidc_user(
            external_id="deactivate-sub",
            username="deactivate"
        )
        
        result = db_service.deactivate_user(user['id'])
        
        assert result is True
        
        deactivated = db_service.get_user_by_external_id("deactivate-sub")
        assert deactivated['is_active'] == 0
    
    def test_activate_user(self, db_service):
        """Test reactivating a deactivated user."""
        user = db_service.upsert_oidc_user(
            external_id="activate-sub",
            username="activate"
        )
        db_service.deactivate_user(user['id'])
        
        result = db_service.activate_user(user['id'])
        
        assert result is True
        
        activated = db_service.get_user_by_external_id("activate-sub")
        assert activated['is_active'] == 1
    
    def test_get_user_by_id(self, db_service):
        """Test retrieving user by database ID."""
        user = db_service.upsert_oidc_user(
            external_id="getbyid-sub",
            username="getbyid"
        )
        
        retrieved = db_service.get_user_by_id(user['id'])
        
        assert retrieved is not None
        assert retrieved['username'] == "getbyid"


class TestUserRetrieval:
    """Tests for user retrieval."""
    
    def test_get_user_by_username_exists(self, db_service):
        """Test retrieving existing user."""
        db_service.upsert_oidc_user(
            external_id="findme-sub",
            username="findme",
            email="find@test.com"
        )
        
        user = db_service.get_user_by_username("findme")
        
        assert user is not None
        assert user['username'] == "findme"
    
    def test_get_user_by_username_not_found(self, db_service):
        """Test retrieving non-existent user returns None."""
        user = db_service.get_user_by_username("nonexistent")
        
        assert user is None


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
