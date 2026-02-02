"""
Tests for sqliteDb/migrations.py to increase code coverage.
"""
from pathlib import Path


class TestMigrationRunnerClass:
    """Tests for MigrationRunner class."""
    
    def test_class_import(self):
        """Test MigrationRunner can be imported."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert MigrationRunner is not None
    
    def test_init_with_default_migrations_dir(self):
        """Test MigrationRunner initialization with default migrations dir."""
        from backend.sqliteDb.migrations import MigrationRunner
        runner = MigrationRunner(":memory:")
        assert runner.db_path == ":memory:"
        assert runner.migrations_dir is not None
    
    def test_init_with_custom_migrations_dir(self):
        """Test MigrationRunner initialization with custom migrations dir."""
        from backend.sqliteDb.migrations import MigrationRunner
        runner = MigrationRunner(":memory:", "/custom/path")
        assert runner.migrations_dir == Path("/custom/path")


class TestMigrationRunnerMethods:
    """Tests for MigrationRunner methods."""
    
    def test_get_connection_exists(self):
        """Test get_connection method exists."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert hasattr(MigrationRunner, 'get_connection')
    
    def test_ensure_migrations_table_exists(self):
        """Test _ensure_migrations_table method exists."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert hasattr(MigrationRunner, '_ensure_migrations_table')
    
    def test_get_applied_migrations_exists(self):
        """Test _get_applied_migrations method exists."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert hasattr(MigrationRunner, '_get_applied_migrations')
    
    def test_get_pending_migrations_exists(self):
        """Test _get_pending_migrations method exists."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert hasattr(MigrationRunner, '_get_pending_migrations')
    
    def test_apply_migration_exists(self):
        """Test _apply_migration method exists."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert hasattr(MigrationRunner, '_apply_migration')
    
    def test_run_pending_migrations_exists(self):
        """Test run_pending_migrations method exists."""
        from backend.sqliteDb.migrations import MigrationRunner
        assert hasattr(MigrationRunner, 'run_pending_migrations')


class TestMigrationRunnerConnection:
    """Tests for database connection methods."""
    
    def test_get_connection_returns_connection(self):
        """Test get_connection returns valid connection."""
        from backend.sqliteDb.migrations import MigrationRunner
        runner = MigrationRunner(":memory:")
        conn = runner.get_connection()
        assert conn is not None
        conn.close()


class TestMigrationRunnerEnsureTable:
    """Tests for migrations table creation."""
    
    def test_ensure_migrations_table_creates_table(self):
        """Test _ensure_migrations_table creates tracking table."""
        from backend.sqliteDb.migrations import MigrationRunner
        runner = MigrationRunner(":memory:")
        conn = runner.get_connection()
        
        runner._ensure_migrations_table(conn)
        
        # Verify table exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_migrations'")
        result = cursor.fetchone()
        assert result is not None
        conn.close()


class TestMigrationRunnerAppliedMigrations:
    """Tests for getting applied migrations."""
    
    def test_get_applied_migrations_empty(self):
        """Test _get_applied_migrations returns empty list for new db."""
        from backend.sqliteDb.migrations import MigrationRunner
        runner = MigrationRunner(":memory:")
        conn = runner.get_connection()
        runner._ensure_migrations_table(conn)
        
        applied = runner._get_applied_migrations(conn)
        assert applied == []
        conn.close()


class TestMigrationRunnerPendingMigrations:
    """Tests for getting pending migrations."""
    
    def test_get_pending_migrations_no_dir(self):
        """Test _get_pending_migrations with non-existent directory."""
        from backend.sqliteDb.migrations import MigrationRunner
        runner = MigrationRunner(":memory:", "/nonexistent/dir")
        pending = runner._get_pending_migrations()
        assert pending == []


class TestMigrationRunnerImports:
    """Tests for migrations module imports."""
    
    def test_sqlite3_import(self):
        """Test sqlite3 is used."""
        from backend.sqliteDb.migrations import sqlite3
        assert sqlite3 is not None
    
    def test_path_import(self):
        """Test Path is imported."""
        from backend.sqliteDb.migrations import Path
        assert Path is not None
    
    def test_logger_exists(self):
        """Test logger is defined."""
        from backend.sqliteDb.migrations import logger
        assert logger is not None


class TestRunMigrationsFunction:
    """Tests for run_migrations function."""
    
    def test_run_migrations_import(self):
        """Test run_migrations can be imported."""
        from backend.sqliteDb.migrations import run_migrations
        assert run_migrations is not None
        assert callable(run_migrations)
