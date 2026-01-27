"""
SQLite database service for user authentication.
"""
import sqlite3
import os
from pathlib import Path
import bcrypt
from typing import Optional, Dict, Any
import logging

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
            The prompt text of the row where is_active=1 (ordered by version desc),
            or None if no active prompt exists.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT prompt_text FROM system_prompts WHERE is_active = 1 ORDER BY version DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row['prompt_text']
        return None

    def publish_system_prompt(self, prompt_text: str, user_id: str, 
                              connection_id: Optional[int] = None, 
                              schema_selection: Optional[str] = None, 
                              data_dictionary: Optional[str] = None,
                              reasoning: Optional[str] = None,
                              example_questions: Optional[str] = None) -> Dict[str, Any]:
        """Publish a new version of the system prompt with optional config metadata.
        
        Args:
            prompt_text: Content of the prompt
            user_id: ID of the creating user
            connection_id: ID of the database connection used
            schema_selection: JSON string of selected schema
            data_dictionary: Content of data dictionary
            reasoning: JSON string of reasoning metadata
            example_questions: JSON string list of questions
            
        Returns:
            Dictionary with the new prompt details
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Get the current max version
            cursor.execute("SELECT MAX(version) FROM system_prompts")
            result = cursor.fetchone()
            current_max_version = result[0] if result and result[0] is not None else 0
            new_version = current_max_version + 1

            # 2. Deactivate all existing prompts
            cursor.execute("UPDATE system_prompts SET is_active = 0 WHERE is_active = 1")

            # 3. Insert the new prompt
            cursor.execute("""
                INSERT INTO system_prompts (prompt_text, version, is_active, created_by)
                VALUES (?, ?, 1, ?)
            """, (prompt_text, new_version, user_id))
            
            prompt_id = cursor.lastrowid
            
            # 4. Insert config metadata if available
            # 4. Insert config metadata if available
            if connection_id is not None:
                cursor.execute("""
                    INSERT INTO prompt_configs (prompt_id, connection_id, schema_selection, data_dictionary, reasoning, example_questions)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (prompt_id, connection_id, schema_selection, data_dictionary, reasoning, example_questions))
            
            conn.commit()
            
            # Return full object
            return {
                "id": prompt_id,
                "prompt_text": prompt_text,
                "version": new_version,
                "is_active": 1
            }
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to publish prompt: {e}")
            raise
        finally:
            conn.close()

    def get_active_config(self) -> Optional[Dict[str, Any]]:
        """Get the configuration metadata for the currently active prompt."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                sp.id as prompt_id,
                sp.version,
                sp.prompt_text,
                sp.created_at,
                sp.created_by,
                u.username as created_by_username,
                pc.connection_id,
                pc.schema_selection,
                pc.data_dictionary,
                pc.reasoning,
                pc.example_questions
            FROM system_prompts sp
            LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
            LEFT JOIN users u ON sp.created_by = CAST(u.id AS TEXT)
            WHERE sp.is_active = 1
            LIMIT 1
        """
        cursor.execute(query)
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None

    def get_all_prompts(self) -> list[Dict[str, Any]]:
        """Get all system prompt versions history.
        
        Returns:
            List of prompt dictionaries ordered by version desc
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                sp.id, 
                sp.prompt_text, 
                sp.version, 
                sp.is_active, 
                sp.created_at, 
                sp.created_by,
                u.username as created_by_username
            FROM system_prompts sp
            LEFT JOIN users u ON sp.created_by = CAST(u.id AS TEXT)
            ORDER BY sp.version DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def add_db_connection(self, name: str, uri: str, engine_type: str = 'postgresql', created_by: Optional[str] = None) -> int:
        """Add a new database connection.
        
        Args:
            name: Friendly name for the connection
            uri: Connection string (e.g., postgresql://user:pass@host/db)
            engine_type: Database type (postgresql, mysql, sqlite)
            created_by: User ID creating the connection
            
        Returns:
            The ID of the newly created connection
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO db_connections (name, uri, engine_type, created_by) VALUES (?, ?, ?, ?)",
                (name, uri, engine_type, created_by)
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
        cursor.execute("SELECT id, name, uri, engine_type, created_at FROM db_connections ORDER BY created_at DESC")
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
        cursor.execute("SELECT id, name, uri, engine_type FROM db_connections WHERE id = ?", (connection_id,))
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
