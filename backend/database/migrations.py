"""
Database migration runner for executing SQL migration files.
Tracks which migrations have been applied to avoid duplicate execution.
"""
import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from typing import List, Tuple
import logging
import re

logger = logging.getLogger(__name__)


class MigrationRunner:
    """
    Handles database schema migrations.
    
    Migrations are SQL files in the migrations/ directory.
    Naming convention: 001_description.sql, 002_description.sql, etc.
    """
    
    def __init__(self, postgres_uri: str, migrations_dir: str = None):
        """
        Initialize the migration runner.
        
        Args:
            postgres_uri: PostgreSQL connection URI
            migrations_dir: Path to the migrations directory
        """
        self.postgres_uri = postgres_uri
        
        # Default migrations directory is at project root
        if migrations_dir is None:
            project_root = Path(__file__).parent.parent.parent
            self.migrations_dir = project_root / "migrations"
        else:
            self.migrations_dir = Path(migrations_dir)
            
    def get_connection(self) -> psycopg2.extensions.connection:
        """Get PostgreSQL database connection with dict cursor."""
        conn = psycopg2.connect(self.postgres_uri)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    
    def _ensure_migrations_table(self, conn: psycopg2.extensions.connection) -> None:
        """Create the migrations tracking table if it doesn't exist."""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checksum TEXT
            )
        """)
        conn.commit()
    
    def _get_applied_migrations(self, conn: psycopg2.extensions.connection) -> List[str]:
        """Get list of already applied migration filenames."""
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM _migrations ORDER BY filename")
        return [row['filename'] for row in cursor.fetchall()]
    
    def _get_pending_migrations(self) -> List[Path]:
        """Get list of migration files that haven't been applied yet."""
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return []
        
        # Get all .sql files and sort by name
        migration_files = sorted(self.migrations_dir.glob("*.sql"))
        
        conn = self.get_connection()
        try:
            self._ensure_migrations_table(conn)
            applied = set(self._get_applied_migrations(conn))
        finally:
            conn.close()
        
        # Filter to pending migrations
        pending = [f for f in migration_files if f.name not in applied]
        return pending
    
    def _calculate_checksum(self, content: str) -> str:
        """Calculate checksum of migration content."""
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _apply_migration(self, conn: psycopg2.extensions.connection, migration_file: Path) -> None:
        """Apply a single migration file.
        
        Handles common idempotency issues like:
        - Duplicate column errors (column already exists)
        - Duplicate index errors (index already exists)
        """
        logger.info(f"Applying migration: {migration_file.name}")
        
        content = migration_file.read_text()
        cursor = conn.cursor()
        
        try:
            # PostgreSQL doesn't support executescript, so we split and execute individually
            # Split by semicolon but be careful with semicolons inside strings
            statements = self._split_sql_statements(content)
            
            for statement in statements:
                statement = statement.strip()
                if statement:  # Skip empty statements
                    cursor.execute(statement)
            
            # Record the migration
            checksum = self._calculate_checksum(content)
            cursor.execute(
                "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s)",
                (migration_file.name, checksum)
            )
            
            conn.commit()
            logger.info(f"Successfully applied migration: {migration_file.name}")
            
        except psycopg2.errors.DuplicateColumn as e:
            # Column already exists - mark as applied
            logger.info(f"Migration {migration_file.name} skipped (column already exists): {e}")
            conn.rollback()
            cursor = conn.cursor()
            checksum = self._calculate_checksum(content)
            cursor.execute(
                "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s)",
                (migration_file.name, checksum)
            )
            conn.commit()
                
        except psycopg2.errors.DuplicateTable as e:
            # Table already exists - mark as applied
            logger.info(f"Migration {migration_file.name} skipped (table already exists): {e}")
            conn.rollback()
            cursor = conn.cursor()
            checksum = self._calculate_checksum(content)
            cursor.execute(
                "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s)",
                (migration_file.name, checksum)
            )
            conn.commit()
                
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            error_msg = str(e).lower()
            # Handle other idempotent cases
            if 'already exists' in error_msg:
                logger.info(f"Migration {migration_file.name} skipped (schema already up-to-date): {e}")
                conn.rollback()
                cursor = conn.cursor()
                checksum = self._calculate_checksum(content)
                cursor.execute(
                    "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s)",
                    (migration_file.name, checksum)
                )
                conn.commit()
            else:
                conn.rollback()
                logger.error(f"Failed to apply migration {migration_file.name}: {e}")
                raise
                
        except psycopg2.Error as e:
            conn.rollback()
            logger.error(f"Failed to apply migration {migration_file.name}: {e}")
            raise
    
    def _split_sql_statements(self, content: str) -> List[str]:
        """Split SQL content into individual statements.
        
        Simple approach: split by semicolon not inside quotes.
        Note: This is a basic implementation. For complex SQL with
        dollar-quoted strings or functions, may need more sophisticated parsing.
        """
        # Remove comments
        lines = []
        for line in content.split('\n'):
            # Remove SQL comments (-- style)
            if '--' in line:
                line = line[:line.index('--')]
            lines.append(line)
        content = '\n'.join(lines)
        
        # Simple split by semicolon (good enough for most migrations)
        statements = content.split(';')
        return [s.strip() for s in statements if s.strip()]
    
    def run_pending_migrations(self) -> List[str]:
        """
        Run all pending migrations.
        
        Returns:
            List of applied migration filenames
        """
        pending = self._get_pending_migrations()
        
        if not pending:
            logger.info("No pending migrations to apply")
            return []
        
        logger.info(f"Found {len(pending)} pending migrations")
        
        applied = []
        conn = self.get_connection()
        
        try:
            self._ensure_migrations_table(conn)
            
            for migration_file in pending:
                self._apply_migration(conn, migration_file)
                applied.append(migration_file.name)
                
        finally:
            conn.close()
        
        return applied
    
    def get_migration_status(self) -> List[dict]:
        """
        Get status of all migrations.
        
        Returns:
            List of dicts with filename, applied, applied_at
        """
        conn = self.get_connection()
        
        try:
            self._ensure_migrations_table(conn)
            
            # Get applied migrations
            cursor = conn.cursor()
            cursor.execute("SELECT filename, applied_at, checksum FROM _migrations")
            applied_dict = {row['filename']: dict(row) for row in cursor.fetchall()}
            
            # Get all migration files
            if not self.migrations_dir.exists():
                return []
            
            migration_files = sorted(self.migrations_dir.glob("*.sql"))
            
            status = []
            for f in migration_files:
                if f.name in applied_dict:
                    status.append({
                        "filename": f.name,
                        "applied": True,
                        "applied_at": applied_dict[f.name]['applied_at'],
                        "checksum": applied_dict[f.name]['checksum']
                    })
                else:
                    status.append({
                        "filename": f.name,
                        "applied": False,
                        "applied_at": None,
                        "checksum": None
                    })
            
            return status
            
        finally:
            conn.close()


def run_migrations(db_path: str = None) -> List[str]:
    """
    Convenience function to run all pending migrations.
    
    Args:
        db_path: Optional database path. Uses default if not provided.
        
    Returns:
        List of applied migration filenames
    """
    from backend.database.db import DB_PATH
    
    if db_path is None:
        db_path = str(DB_PATH)
    
    runner = MigrationRunner(db_path)
    return runner.run_pending_migrations()


if __name__ == "__main__":
    # Run migrations when executed directly
    logging.basicConfig(level=logging.INFO)
    applied = run_migrations()
    
    if applied:
        print(f"Applied {len(applied)} migrations:")
        for m in applied:
            print(f"  - {m}")
    else:
        print("No pending migrations")
