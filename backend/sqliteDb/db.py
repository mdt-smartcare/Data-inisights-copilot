"""
SQLite database service for user authentication.
"""
import sqlite3
import os
from pathlib import Path
import bcrypt
from typing import Optional, Dict, Any
import logging
import json
import hashlib

logger = logging.getLogger(__name__)

# Database path
DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "app.db"


class DatabaseService:
    """SQLite database service for user management.
    
    This service handles all user-related database operations including:
    - User registration and creation
    - User authentication with bcrypt password hashing
    - User retrieval and management
    - Database schema initialization and migrations
    """
    
    def __init__(self, db_path: str = None):
        """Initialize the database service.
        
        Args:
            db_path: Optional custom path to the SQLite database file.
                    If not provided, uses default path (backend/sqliteDb/app.db)
        """
        self.db_path = db_path or str(DB_PATH)
        self._init_database()
        self._run_migrations()
    
    def _run_migrations(self):
        """Run any pending SQL migrations from the migrations directory."""
        try:
            from backend.sqliteDb.migrations import MigrationRunner
            runner = MigrationRunner(self.db_path)
            applied = runner.run_pending_migrations()
            if applied:
                logger.info(f"Applied {len(applied)} database migrations: {applied}")
        except Exception as e:
            logger.warning(f"Migration runner failed (non-fatal): {e}")
    
    def _init_database(self):
        """Initialize database schema and create default admin user.
        
        This method:
        1. Creates the users table if it doesn't exist
        2. Handles schema migrations (e.g., adding role column to existing databases)
        3. Creates a default admin user from environment variables
        
        Environment Variables:
            ADMIN_USERNAME: Admin username (default: admin)
            ADMIN_PASSWORD: Admin password (default: admin123 - CHANGE IN PRODUCTION!)
            ADMIN_EMAIL: Admin email (default: admin@example.com)
        
        Note: This runs automatically on service initialization.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create users table with all necessary fields for authentication and user management
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    role TEXT DEFAULT 'user',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create system_prompts table for dynamic prompt management
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_text TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    is_active INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Create db_connections table for managing database endpoints
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    uri TEXT NOT NULL,
                    engine_type TEXT DEFAULT 'postgresql',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by TEXT
                )
            """)

            # Create prompt_configs table to link prompts to their configuration source
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompt_configs (
                    prompt_id INTEGER PRIMARY KEY,
                    connection_id INTEGER,
                    schema_selection TEXT, -- JSON string
                    data_dictionary TEXT,
                    reasoning TEXT, -- JSON string
                    example_questions TEXT, -- JSON string list
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY(prompt_id) REFERENCES system_prompts(id)
                )
            """)

            
            # Add role column if it doesn't exist (migration for existing databases)
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'role' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
                logger.info("Added role column to users table")

            # Add reasoning column to prompt_configs if it doesn't exist
            cursor.execute("PRAGMA table_info(prompt_configs)")
            pc_columns = [col[1] for col in cursor.fetchall()]
            if 'reasoning' not in pc_columns:
                cursor.execute("ALTER TABLE prompt_configs ADD COLUMN reasoning TEXT")
                logger.info("Added reasoning column to prompt_configs table")

            if 'example_questions' not in pc_columns:
                cursor.execute("ALTER TABLE prompt_configs ADD COLUMN example_questions TEXT")
                logger.info("Added example_questions column to prompt_configs table")
            
            # Get admin credentials from environment variables
            admin_username = os.getenv('ADMIN_USERNAME', 'admin')
            admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@example.com')
            
            # Check if admin exists, if not create it
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (admin_username,))
            if cursor.fetchone()[0] == 0:
                admin_password_hash = self.hash_password(admin_password)
                cursor.execute(
                    """INSERT INTO users (username, email, password_hash, full_name, role) 
                       VALUES (?, ?, ?, ?, ?)""",
                    (admin_username, admin_email, admin_password_hash, "Administrator", "super_admin")
                )
                logger.info(f"Default admin user '{admin_username}' created")
            
            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt with automatic salt generation.
        
        Args:
            password: Plain text password to hash
            
        Returns:
            String containing the bcrypt hash (safe to store in database)
            
        Note: Bcrypt automatically includes the salt in the hash output,
              so no separate salt storage is needed.
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()  # Generate a random salt
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain text password against its bcrypt hash.
        
        Args:
            plain_password: Plain text password to verify
            hashed_password: Bcrypt hash from database
            
        Returns:
            True if password matches, False otherwise
        """
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    
    def create_user(self, username: str, password: str, email: Optional[str] = None, 
                   full_name: Optional[str] = None, role: str = "user") -> Dict[str, Any]:
        """Create a new user account in the database.
        
        Args:
            username: Unique username (will be validated by database constraint)
            password: Plain text password (will be hashed before storage)
            email: Optional email address (must be unique if provided)
            full_name: Optional full name of the user
            role: User role (default: 'user', can be 'super_admin', 'editor', 'user', 'viewer')
            
        Returns:
            Dictionary containing created user information (without password)
            
        Raises:
            ValueError: If username or email already exists
            Exception: For other database errors
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            password_hash = self.hash_password(password)
            cursor.execute(
                """INSERT INTO users (username, email, password_hash, full_name, role) 
                   VALUES (?, ?, ?, ?, ?)""",
                (username, email, password_hash, full_name, role)
            )
            conn.commit()
            user_id = cursor.lastrowid
            
            # Return created user (without password)
            cursor.execute(
                "SELECT id, username, email, full_name, role, created_at FROM users WHERE id = ?",
                (user_id,)
            )
            user = dict(cursor.fetchone())
            conn.close()
            logger.info(f"User created: {username} with role: {role}")
            return user
        except sqlite3.IntegrityError as e:
            conn.close()
            logger.error(f"User creation failed: {e}")
            raise ValueError("Username or email already exists")
        except Exception as e:
            conn.close()
            logger.error(f"User creation error: {e}")
            raise
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve user information by username.
        
        Args:
            username: Username to search for
            
        Returns:
            Dictionary with user data including password_hash, or None if not found
            
        Note: This method returns the password hash, which should only be used
              for internal authentication. Use authenticate_user for login validation.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, username, email, password_hash, full_name, role, is_active FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None

    def get_config_by_id(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific configuration by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                rc.id,
                rc.version,
                rc.prompt_template,
                rc.connection_id,
                rc.schema_snapshot,
                rc.data_dictionary,
                rc.embedding_config,
                rc.retriever_config
            FROM rag_configurations rc
            WHERE rc.id = ?
        """
        cursor.execute(query, (config_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            # Rehydrate schema snapshot if it's stored as JSON string
            # (It is stored as TEXT in migration)
            return data
        return None
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate a user with username and password.
        
        This is the main login verification method. It:
        1. Retrieves the user from database
        2. Checks if user is active
        3. Verifies password using bcrypt
        4. Returns user info WITHOUT password hash
        
        Args:
            username: Username to authenticate
            password: Plain text password to verify
            
        Returns:
            Dictionary with user info (no password) if authentication succeeds,
            None if authentication fails for any reason
            
        Security Note: Failed authentication does not distinguish between
        'user not found' and 'wrong password' to prevent username enumeration.
        """
        user = self.get_user_by_username(username)
        
        if not user:
            logger.warning(f"Authentication failed: User not found - {username}")
            return None
        
        if not user.get('is_active'):
            logger.warning(f"Authentication failed: User inactive - {username}")
            return None
        
        if not self.verify_password(password, user['password_hash']):
            logger.warning(f"Authentication failed: Invalid password - {username}")
            return None
        
        # Remove password hash before returning
        user.pop('password_hash', None)
        logger.info(f"Authentication successful: {username}")
        return user
    
    def get_latest_active_prompt(self) -> Optional[str]:
        """Get the latest active system prompt.
        
        Returns:
            The prompt text of the row where is_active=1 (ordered by version_number desc),
            or None if no active prompt exists.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT prompt_template FROM rag_configurations WHERE is_active = 1 ORDER BY version_number DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row['prompt_template']
        return None

    def publish_system_prompt(self, prompt_text: str, user_id: str, 
                              connection_id: Optional[int] = None, 
                              schema_selection: Optional[str] = None, 
                              data_dictionary: Optional[str] = None,
                              reasoning: Optional[str] = None,
                              example_questions: Optional[str] = None,
                              embedding_config: Optional[str] = None,
                              retriever_config: Optional[str] = None) -> Dict[str, Any]:
        """Publish a new version of the system prompt with optional config metadata.
        
        Args:
            prompt_text: Content of the prompt
            user_id: ID of the creating user
            connection_id: ID of the database connection used
            schema_selection: JSON string of selected schema
            data_dictionary: Content of data dictionary
            reasoning: JSON string of reasoning metadata
            example_questions: JSON string list of questions
            embedding_config: JSON string of embedding parameters
            retriever_config: JSON string of retrieval parameters
            
        Returns:
            Dictionary with the new prompt details
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Get the current max version number
            cursor.execute("SELECT MAX(version_number) FROM rag_configurations")
            result = cursor.fetchone()
            current_max = result[0] if result and result[0] is not None else 0
            new_version_num = current_max + 1
            new_version_str = f"1.{new_version_num}.0" # Simple semantic versioning

            # 2. Deactivate all existing configs
            cursor.execute("UPDATE rag_configurations SET is_active = 0 WHERE is_active = 1")

            # 3. Insert the new config
            # Combining schema_selection, reasoning, example_questions into snapshot logic if needed
            # But the table expects schema_snapshot (snapshot of DB schema) separate from selection
            # For now, we will store the selection as the snapshot since we re-fetch details on demand
            schema_snapshot = schema_selection if schema_selection else "{}"
            
            # Additional metadata bag
            metadata = {
                "reasoning": json.loads(reasoning) if reasoning else None,
                "example_questions": json.loads(example_questions) if example_questions else None
            }
            
            # Generate config hash (simplified)
            import hashlib
            config_hash = hashlib.sha256(
                f"{prompt_text}{schema_snapshot}{data_dictionary}".encode()
            ).hexdigest()

            cursor.execute("""
                INSERT INTO rag_configurations (
                    version, version_number, schema_snapshot, data_dictionary, 
                    prompt_template, status, created_by, connection_id, is_active, 
                    config_hash, change_summary, embedding_config, retriever_config
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                new_version_str, new_version_num, schema_snapshot, data_dictionary,
                prompt_text, 'published', user_id, connection_id, 1,
                config_hash, json.dumps(metadata), embedding_config, retriever_config
            ))
            
            config_id = cursor.lastrowid
            conn.commit()
            
            # Return full object matched to UI expectations
            return {
                "id": config_id,
                "prompt_text": prompt_text,
                "version": new_version_str,
                "version_number": new_version_num,
                "is_active": 1
            }
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to publish config: {e}")
            raise
        finally:
            conn.close()

    def get_active_config(self) -> Optional[Dict[str, Any]]:
        """Get the configuration metadata for the currently active prompt."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                rc.id as prompt_id,
                rc.version,
                rc.prompt_template as prompt_text,
                rc.created_at,
                rc.created_by,
                u.username as created_by_username,
                rc.connection_id,
                rc.schema_snapshot as schema_selection,
                rc.data_dictionary,
                rc.change_summary,
                rc.embedding_config,
                rc.retriever_config
            FROM rag_configurations rc
            LEFT JOIN users u ON rc.created_by = CAST(u.id AS TEXT)
            WHERE rc.is_active = 1
            LIMIT 1
        """
        cursor.execute(query)
        row = cursor.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            # Rehydrate change_summary into reasoning/questions if present
            try:
                if data['change_summary']:
                    meta = json.loads(data['change_summary'])
                    if isinstance(meta, dict):
                        data['reasoning'] = json.dumps(meta.get('reasoning'))
                        data['example_questions'] = json.dumps(meta.get('example_questions'))
            except:
                pass
            return data
        return None

    def get_all_prompts(self) -> list[Dict[str, Any]]:
        """Get all system prompt versions history."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                rc.id, 
                rc.prompt_template as prompt_text, 
                rc.version, 
                rc.is_active, 
                rc.created_at, 
                rc.created_by,
                u.username as created_by_username
            FROM rag_configurations rc
            LEFT JOIN users u ON rc.created_by = CAST(u.id AS TEXT)
            ORDER BY rc.version_number DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def add_db_connection(self, name: str, uri: str, engine_type: str = 'postgresql', created_by: Optional[str] = None, pool_config: Optional[str] = None) -> int:
        """Add a new database connection.
        
        Args:
            name: Friendly name for the connection
            uri: Connection string (e.g., postgresql://user:pass@host/db)
            engine_type: Database type (postgresql, mysql, sqlite)
            created_by: User ID creating the connection
            pool_config: JSON string of pool configuration
            
        Returns:
            The ID of the newly created connection
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO db_connections (name, uri, engine_type, created_by, pool_config) VALUES (?, ?, ?, ?, ?)",
                (name, uri, engine_type, created_by, pool_config)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Connection with name '{name}' already exists")
        finally:
            conn.close()

    def get_db_connections(self) -> list[Dict[str, Any]]:
        """Get all saved database connections."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, uri, engine_type, created_at, pool_config FROM db_connections ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def delete_db_connection(self, connection_id: int) -> bool:
        """Delete a database connection by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM db_connections WHERE id = ?", (connection_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def get_db_connection_by_id(self, connection_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific database connection by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, uri, engine_type, pool_config FROM db_connections WHERE id = ?", (connection_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_active_metrics(self) -> list[Dict[str, Any]]:
        """Get all active metric definitions ordered by priority.
        
        Returns:
            List of metric dictionary objects
        """
        conn = self.get_connection()
        cursor = conn.cursor() # Use dictionary cursor via row_factory in get_connection
        
        try:
            cursor.execute("""
                SELECT id, name, description, regex_pattern, sql_template, priority 
                FROM metric_definitions 
                WHERE is_active = 1 
                ORDER BY priority ASC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            # Table might not exist yet if migration hasn't run or in tests
            logger.warning("metric_definitions table not found")
            return []
        finally:
            conn.close()

    def get_sql_examples(self) -> list[Dict[str, Any]]:
        """Get all SQL examples for few-shot learning."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM sql_examples ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            logger.warning("sql_examples table not found")
            return []
        finally:
            conn.close()



# Global database instance (Singleton pattern)
# This ensures all parts of the application share the same database connection pool
db_service = DatabaseService()


def get_db_service() -> DatabaseService:
    """Get the singleton database service instance.
    
    This function is used as a FastAPI dependency for dependency injection.
    It ensures all route handlers share the same database service instance.
    
    Usage in FastAPI routes:
        @router.post("/endpoint")
        async def endpoint(db: DatabaseService = Depends(get_db_service)):
            # Use db service here
            user = db.get_user_by_username("username")
    
    Returns:
        DatabaseService: The global database service instance
    """
    return db_service
