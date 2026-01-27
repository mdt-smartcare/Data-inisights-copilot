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
            
            # Add role column if it doesn't exist (migration for existing databases)
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'role' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
                logger.info("Added role column to users table")
            
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
                    (admin_username, admin_email, admin_password_hash, "Administrator", "admin")
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
            role: User role (default: 'user', can be 'admin' for elevated privileges)
            
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
