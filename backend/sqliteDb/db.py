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
                    created_by TEXT,
                    agent_id INTEGER REFERENCES agents(id)
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
                    data_source_type TEXT DEFAULT 'database',
                    ingestion_documents TEXT, -- JSON string list of ExtractedDocument
                    ingestion_file_name TEXT,
                    ingestion_file_type TEXT,
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
            
            if 'data_source_type' not in pc_columns:
                cursor.execute("ALTER TABLE prompt_configs ADD COLUMN data_source_type TEXT DEFAULT 'database'")
                logger.info("Added data_source_type column to prompt_configs table")
                
            if 'ingestion_documents' not in pc_columns:
                cursor.execute("ALTER TABLE prompt_configs ADD COLUMN ingestion_documents TEXT")
                cursor.execute("ALTER TABLE prompt_configs ADD COLUMN ingestion_file_name TEXT")
                cursor.execute("ALTER TABLE prompt_configs ADD COLUMN ingestion_file_type TEXT")
                logger.info("Added ingestion columns to prompt_configs table")
            
            # Create agents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    type TEXT DEFAULT 'sql', -- 'sql', 'rag', 'supervisor'
                    db_connection_uri TEXT, -- Encrypted/Secure URI
                    rag_config_id INTEGER,
                    system_prompt TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(rag_config_id) REFERENCES rag_configurations(id),
                    FOREIGN KEY(created_by) REFERENCES users(id)
                )
            """)

            # Create user_agents table for RBAC
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_agents (
                    user_id INTEGER,
                    agent_id INTEGER,
                    role TEXT DEFAULT 'viewer', -- 'viewer', 'editor', 'admin'
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    granted_by INTEGER,
                    PRIMARY KEY (user_id, agent_id),
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(agent_id) REFERENCES agents(id),
                    FOREIGN KEY(granted_by) REFERENCES users(id)
                )
            """)

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
    
    def get_latest_active_prompt(self, agent_id: Optional[int] = None) -> Optional[str]:
        """Get the latest active system prompt.
        
        Returns:
            The prompt text of the row where is_active=1 (ordered by version desc),
            or None if no active prompt exists.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if agent_id:
            cursor.execute(
                "SELECT prompt_text FROM system_prompts WHERE is_active = 1 AND agent_id = ? ORDER BY version DESC LIMIT 1",
                (agent_id,)
            )
        else:
            cursor.execute(
                "SELECT prompt_text FROM system_prompts WHERE is_active = 1 AND agent_id IS NULL ORDER BY version DESC LIMIT 1"
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
                              example_questions: Optional[str] = None,
                              embedding_config: Optional[str] = None,
                              retriever_config: Optional[str] = None,
                              agent_id: Optional[int] = None,
                              data_source_type: str = 'database',
                              ingestion_documents: Optional[str] = None,
                              ingestion_file_name: Optional[str] = None,
                              ingestion_file_type: Optional[str] = None) -> Dict[str, Any]:
        """Publish a new version of the system prompt with optional config metadata.
        
        Args:
            prompt_text: Content of the prompt
            user_id: ID of the creating user
            connection_id: ID of the database connection used
            schema_selection: JSON string of selected schema
            data_dictionary: Content of data dictionary
            reasoning: JSON string of reasoning metadata
            example_questions: JSON string list of questions
            embedding_config: JSON string of embedding parameters (ignored - for compatibility)
            retriever_config: JSON string of retrieval parameters (ignored - for compatibility)
            agent_id: ID of the agent this prompt belongs to
            data_source_type: Type of data source ('database' or 'file')
            ingestion_documents: JSON string list of ExtractedDocument (for file sources)
            ingestion_file_name: Uploaded file name
            ingestion_file_type: Uploaded file extension
            
        Returns:
            Dictionary with the new prompt details
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 1. Get the current max version number (global or per agent? technically global versioning is fine for now but per agent is better)
            # For simplicity, we keep versioning global or scoped? 
            # Let's keep version simplified: distinct prompt rows.
            
            # If agent_id is provided, we should deactivate active prompts FOR THIS AGENT
            # If agent_id is None (legacy/global), we deactivate global active prompts?
            # Or should we enforce agent_id?
            # For backward compatibility, if agent_id is None, it acts as "default" or "global".
            
            cursor.execute("SELECT MAX(version) FROM system_prompts")
            result = cursor.fetchone()
            current_max = result[0] if result and result[0] is not None else 0
            new_version = current_max + 1

            # 2. Deactivate all existing prompts for this agent (or global if None)
            if agent_id:
                cursor.execute("UPDATE system_prompts SET is_active = 0 WHERE is_active = 1 AND agent_id = ?", (agent_id,))
            else:
                cursor.execute("UPDATE system_prompts SET is_active = 0 WHERE is_active = 1 AND agent_id IS NULL")

            # 3. Insert the new prompt into system_prompts
            cursor.execute("""
                INSERT INTO system_prompts (
                    prompt_text, version, is_active, created_by, agent_id
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                prompt_text, new_version, 1, user_id, agent_id
            ))
            
            prompt_id = cursor.lastrowid

            # 4. Insert configuration metadata into prompt_configs
            cursor.execute("""
                INSERT INTO prompt_configs (
                    prompt_id, connection_id, schema_selection, 
                    data_dictionary, reasoning, example_questions,
                    data_source_type, ingestion_documents,
                    ingestion_file_name, ingestion_file_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prompt_id, connection_id, schema_selection,
                data_dictionary, reasoning, example_questions,
                data_source_type, ingestion_documents,
                ingestion_file_name, ingestion_file_type
            ))
            
            conn.commit()
            
            # Return full object matched to UI expectations
            return {
                "id": prompt_id,
                "prompt_text": prompt_text,
                "version": str(new_version),
                "is_active": 1,
                "created_by": user_id,
                "agent_id": agent_id
            }
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to publish prompt: {e}")
            raise
        finally:
            conn.close()

    def get_active_config(self, agent_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get the configuration metadata for the currently active prompt."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Build query based on agent_id
        if agent_id:
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
                    pc.example_questions,
                    pc.data_source_type,
                    pc.ingestion_documents,
                    pc.ingestion_file_name,
                    pc.ingestion_file_type
                FROM system_prompts sp
                LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
                LEFT JOIN users u ON sp.created_by = u.username
                WHERE sp.is_active = 1 AND sp.agent_id = ?
                LIMIT 1
            """
            cursor.execute(query, (agent_id,))
        else:
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
                    pc.example_questions,
                    pc.data_source_type,
                    pc.ingestion_documents,
                    pc.ingestion_file_name,
                    pc.ingestion_file_type
                FROM system_prompts sp
                LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
                LEFT JOIN users u ON sp.created_by = u.username
                WHERE sp.is_active = 1 AND sp.agent_id IS NULL
                LIMIT 1
            """
            cursor.execute(query)

        row = cursor.fetchone()
        conn.close()
        
        if row:
            data = dict(row)
            return data
        return None

    def get_all_prompts(self, agent_id: Optional[int] = None) -> list[Dict[str, Any]]:
        """Get all system prompt versions history."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        base_query = """
            SELECT 
                sp.id, 
                sp.prompt_text, 
                sp.version, 
                sp.is_active, 
                sp.created_at, 
                sp.created_by,
                u.username as created_by_username
            FROM system_prompts sp
            LEFT JOIN users u ON sp.created_by = u.username
        """
        
        if agent_id:
            cursor.execute(base_query + " WHERE sp.agent_id = ? ORDER BY sp.version DESC", (agent_id,))
        else:
            cursor.execute(base_query + " WHERE sp.agent_id IS NULL ORDER BY sp.version DESC")
            
        rows = cursor.fetchall()
        conn.close()
        
        # Convert version to string for API validation
        result = []
        for row in rows:
            data = dict(row)
            data['version'] = str(data['version'])
            result.append(data)
        
        return result

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

    def create_agent(self, name: str, description: str = None, agent_type: str = 'sql', 
                    db_connection_uri: str = None, rag_config_id: int = None, 
                    system_prompt: str = None, created_by: int = None) -> Dict[str, Any]:
        """Create a new agent."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO agents (name, description, type, db_connection_uri, rag_config_id, system_prompt, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, description, agent_type, db_connection_uri, rag_config_id, system_prompt, created_by))
            conn.commit()
            agent_id = cursor.lastrowid
            
            # Auto-assign creator as admin
            if created_by:
                cursor.execute("""
                    INSERT INTO user_agents (user_id, agent_id, role, granted_by)
                    VALUES (?, ?, 'admin', ?)
                """, (created_by, agent_id, created_by))
                conn.commit()
                
            return self.get_agent_by_id(agent_id)
        except sqlite3.IntegrityError:
            raise ValueError(f"Agent with name '{name}' already exists")
        finally:
            conn.close()

    def get_agent_by_id(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_agents_for_user(self, user_id: int) -> list[Dict[str, Any]]:
        """Get all agents a user has access to."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, ua.role as user_role 
            FROM agents a
            JOIN user_agents ua ON a.id = ua.agent_id
            WHERE ua.user_id = ?
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def check_user_access(self, user_id: int, agent_id: int, required_role: str = None) -> bool:
        """Check if user has access to an agent."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM user_agents WHERE user_id = ? AND agent_id = ?", (user_id, agent_id))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False
            
        if required_role:
            user_role = row['role']
            # Simple role hierarchy
            roles = {'viewer': 1, 'editor': 2, 'admin': 3}
            return roles.get(user_role, 0) >= roles.get(required_role, 0)
            
        return True


    def list_all_agents(self) -> list[Dict[str, Any]]:
        """List all agents (Admin only)."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agents")
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def assign_user_to_agent(self, agent_id: int, user_id: int, role: str = 'viewer', granted_by: int = None) -> bool:
        """Assign a user to an agent with a specific role."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO user_agents (user_id, agent_id, role, granted_by)
                VALUES (?, ?, ?, ?)
            """, (user_id, agent_id, role, granted_by))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to assign user {user_id} to agent {agent_id}: {e}")
            return False
        finally:
            conn.close()

    def revoke_user_access(self, agent_id: int, user_id: int) -> bool:
        """Revoke a user's access to an agent."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM user_agents WHERE user_id = ? AND agent_id = ?", (user_id, agent_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to revoke access for user {user_id} from agent {agent_id}: {e}")
            return False
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
