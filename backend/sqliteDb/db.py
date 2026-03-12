"""
SQLite database service for user authentication.
"""
import sqlite3
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import hashlib

from backend.core.logging import get_logger

logger = get_logger(__name__)

# Database path
DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "app.db"


class DatabaseService:
    """SQLite database service for user and configuration management.
    
    This service handles database operations including:
    - User management (OIDC JIT provisioning, role assignment)
    - System prompt versioning and configuration
    - Database connection management
    - Agent RBAC
    
    Note: User authentication is handled by Keycloak/OIDC.
    Users are created via Just-In-Time provisioning on first login.
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
        """Run any pending SQL migrations from the migrations directory.
        
        This is the ONLY place where schema changes happen.
        All table creation and alterations must be done via migration files.
        """
        try:
            # Use relative import to avoid path issues
            from .migrations import MigrationRunner
            runner = MigrationRunner(self.db_path)
            applied = runner.run_pending_migrations()
            if applied:
                logger.info(f"Applied {len(applied)} database migrations: {applied}")
        except ImportError:
            # Fallback for when running from different contexts
            try:
                from backend.sqliteDb.migrations import MigrationRunner
                runner = MigrationRunner(self.db_path)
                applied = runner.run_pending_migrations()
                if applied:
                    logger.info(f"Applied {len(applied)} database migrations: {applied}")
            except Exception as e:
                logger.error(f"Migration runner failed: {e}")
                raise RuntimeError(f"Database migrations failed: {e}. Cannot start without migrations.")
        except Exception as e:
            logger.error(f"Migration runner failed: {e}")
            raise RuntimeError(f"Database migrations failed: {e}. Cannot start without migrations.")
    
    def _init_database(self):
        """Initialize database by running migrations.
        
        This method only ensures the database file exists and runs migrations.
        ALL schema creation is handled by migration files in the migrations/ directory.
        
        Industry Standard: Migrations-only approach
        - 000_initial_schema.sql: Creates all base tables
        - 001+: Incremental schema changes
        """
        try:
            # Just ensure we can connect (creates the file if it doesn't exist)
            conn = self.get_connection()
            conn.close()
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn


    def get_user_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user information by OIDC external ID (Keycloak sub claim).
        
        Args:
            external_id: The OIDC subject claim (sub) that uniquely identifies the user
            
        Returns:
            Dictionary with user data, or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, username, email, full_name, role, is_active, external_id FROM users WHERE external_id = ?",
            (external_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def upsert_oidc_user(
        self,
        external_id: str,
        email: Optional[str] = None,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
        default_role: str = "user"
    ) -> Dict[str, Any]:
        """Create or update a user from OIDC token claims (Just-In-Time provisioning).
        
        This method is called when a user authenticates via Keycloak for the first time.
        It creates a new user record if not exists, or updates the existing user's info.
        
        For existing users, only email and full_name are updated (not role).
        The role is managed locally by admins after initial provisioning.
        
        Args:
            external_id: OIDC subject claim (required, unique identifier from Keycloak)
            email: User's email from OIDC token
            username: Preferred username from OIDC token (falls back to external_id if not provided)
            full_name: User's display name from OIDC token
            default_role: Default role for new users (from Keycloak mapping or config)
            
        Returns:
            Dictionary with user data (without password_hash)
            
        Raises:
            ValueError: If external_id conflicts with existing user
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if user already exists by external_id
            existing_user = self.get_user_by_external_id(external_id)
            
            if existing_user:
                # Update existing user's info (but not role - that's managed locally)
                cursor.execute(
                    """UPDATE users 
                       SET email = COALESCE(?, email),
                           full_name = COALESCE(?, full_name),
                           updated_at = CURRENT_TIMESTAMP
                       WHERE external_id = ?""",
                    (email, full_name, external_id)
                )
                conn.commit()
                
                # Fetch updated user
                cursor.execute(
                    "SELECT id, username, email, full_name, role, is_active, external_id, created_at FROM users WHERE external_id = ?",
                    (external_id,)
                )
                user = dict(cursor.fetchone())
                conn.close()
                logger.info(f"OIDC user updated: {username or external_id}")
                return user
            else:
                # Create new user with OIDC info
                # Use external_id as username if preferred_username not provided
                effective_username = username or external_id[:50]  # Truncate to fit column
                
                # For OIDC users, we don't have a password - use a placeholder
                # The password_hash column still exists but won't be used for OIDC auth
                placeholder_hash = "OIDC_USER_NO_PASSWORD"
                
                cursor.execute(
                    """INSERT INTO users (username, email, password_hash, full_name, role, external_id, is_active) 
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    (effective_username, email, placeholder_hash, full_name, default_role, external_id)
                )
                conn.commit()
                user_id = cursor.lastrowid
                
                # Fetch created user
                cursor.execute(
                    "SELECT id, username, email, full_name, role, is_active, external_id, created_at FROM users WHERE id = ?",
                    (user_id,)
                )
                user = dict(cursor.fetchone())
                conn.close()
                logger.info(f"OIDC user created: {effective_username} with role: {default_role}")
                return user
                
        except sqlite3.IntegrityError as e:
            conn.close()
            logger.error(f"OIDC user upsert failed (integrity error): {e}")
            # This could happen if username conflicts with existing local user
            raise ValueError(f"User with this identity already exists: {e}")
        except Exception as e:
            conn.close()
            logger.error(f"OIDC user upsert error: {e}")
            raise
    
    def update_user_role(self, user_id: int, new_role: str) -> bool:
        """Update a user's role (admin function for local role management).
        
        Args:
            user_id: The user's database ID
            new_role: New role to assign (admin, user)
            
        Returns:
            True if update succeeded, False if user not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_role, user_id)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        if affected > 0:
            logger.info(f"User {user_id} role updated to: {new_role}")
            return True
        return False
    
    def list_all_users(self) -> List[Dict[str, Any]]:
        """List all users in the system.
        
        Returns:
            List of user dictionaries (without password_hash)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, username, email, full_name, role, is_active, external_id, created_at 
               FROM users ORDER BY created_at DESC"""
        )
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def search_users(self, query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        """Search users by username or email.
        
        Args:
            query: Search query string (matches username or email)
            limit: Maximum number of results
            
        Returns:
            List of matching user dictionaries
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if query:
            search_pattern = f"%{query}%"
            cursor.execute(
                """SELECT id, username, email, full_name, role, is_active, external_id, created_at 
                   FROM users 
                   WHERE is_active = 1 AND (username LIKE ? OR email LIKE ? OR full_name LIKE ?)
                   ORDER BY username
                   LIMIT ?""",
                (search_pattern, search_pattern, search_pattern, limit)
            )
        else:
            cursor.execute(
                """SELECT id, username, email, full_name, role, is_active, external_id, created_at 
                   FROM users 
                   WHERE is_active = 1
                   ORDER BY username
                   LIMIT ?""",
                (limit,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

    def get_users_by_emails(self, emails: List[str]) -> List[Dict[str, Any]]:
        """Get users by a list of email addresses.
        
        Args:
            emails: List of email addresses to look up
            
        Returns:
            List of user dictionaries for matching emails
        """
        if not emails:
            return []
            
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Normalize emails to lowercase
        normalized_emails = [e.lower().strip() for e in emails if e and e.strip()]
        if not normalized_emails:
            conn.close()
            return []
        
        placeholders = ','.join(['?' for _ in normalized_emails])
        cursor.execute(
            f"""SELECT id, username, email, full_name, role, is_active, external_id, created_at 
               FROM users 
               WHERE is_active = 1 AND LOWER(email) IN ({placeholders})
               ORDER BY email""",
            normalized_emails
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user account.
        
        Args:
            user_id: The user's database ID
            
        Returns:
            True if update succeeded, False if user not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE users SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        if affected > 0:
            logger.info(f"User {user_id} deactivated")
            return True
        return False
    
    def activate_user(self, user_id: int) -> bool:
        """Activate (reactivate) a user account.
        
        Args:
            user_id: The user's database ID
            
        Returns:
            True if update succeeded, False if user not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE users SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id,)
        )
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        if affected > 0:
            logger.info(f"User {user_id} activated")
            return True
        return False
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve user information by database ID.
        
        Args:
            user_id: User's database ID
            
        Returns:
            Dictionary with user data, or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, username, email, full_name, role, is_active, external_id, created_at FROM users WHERE id = ?",
            (user_id,)
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
                sp.id as prompt_id,
                sp.version,
                sp.prompt_text,
                sp.agent_id,
                pc.connection_id,
                pc.schema_selection,
                pc.data_dictionary,
                pc.embedding_config,
                pc.retriever_config,
                pc.chunking_config,
                pc.llm_config,
                pc.data_source_type,
                pc.ingestion_documents,
                pc.ingestion_file_name,
                pc.ingestion_file_type
            FROM system_prompts sp
            LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
            WHERE sp.id = ?
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
                              chunking_config: Optional[str] = None,
                              llm_config: Optional[str] = None,
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
                    ingestion_file_name, ingestion_file_type,
                    embedding_config, retriever_config,
                    chunking_config, llm_config
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prompt_id, connection_id, schema_selection,
                data_dictionary, reasoning, example_questions,
                data_source_type, ingestion_documents,
                ingestion_file_name, ingestion_file_type,
                embedding_config, retriever_config,
                chunking_config, llm_config
            ))
            
            conn.commit()
            
            # Return full object matched to UI expectations
            return {
                "id": prompt_id,
                "prompt_text": prompt_text,
                "version": str(new_version),
                "version_number": new_version,
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
                    pc.ingestion_file_type,
                    pc.embedding_config,
                    pc.retriever_config,
                    pc.chunking_config,
                    pc.llm_config
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
                    pc.ingestion_file_type,
                    pc.embedding_config,
                    pc.retriever_config,
                    pc.chunking_config,
                    pc.llm_config
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
        """Get all system prompt versions history with configuration metadata."""
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
                sp.agent_id,
                u.username as created_by_username,
                pc.connection_id,
                pc.schema_selection,
                pc.data_dictionary,
                pc.reasoning,
                pc.example_questions,
                pc.data_source_type,
                pc.ingestion_documents,
                pc.ingestion_file_name,
                pc.ingestion_file_type,
                pc.embedding_config,
                pc.retriever_config,
                pc.chunking_config,
                pc.llm_config
            FROM system_prompts sp
            LEFT JOIN users u ON sp.created_by = u.username
            LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
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
        
    def get_vector_db_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get vector db by name to check existence/collisions."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, data_source_id, created_at, created_by FROM vector_db_registry WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None

    def register_vector_db(self, name: str, data_source_id: str, created_by: Optional[str] = None) -> int:
        """Register a new vector DB namespace."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO vector_db_registry (name, data_source_id, created_by) VALUES (?, ?, ?)",
                (name, data_source_id, created_by)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Vector DB with name '{name}' already exists.")
        finally:
            conn.close()

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
        """Create a new agent and automatically assign the creator as admin."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO agents (name, description, type, db_connection_uri, rag_config_id, system_prompt, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, description, agent_type, db_connection_uri, rag_config_id, system_prompt, created_by))
            conn.commit()
            agent_id = cursor.lastrowid
            
            # Auto-assign creator as admin in user_agents table
            if created_by:
                cursor.execute("""
                    INSERT OR REPLACE INTO user_agents (user_id, agent_id, role, granted_by)
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

    def get_agents_for_admin(self, user_id: int) -> list[Dict[str, Any]]:
        """Get all agents an admin has access to via user_agents table.
        
        Access is determined solely by user_agents assignments. The created_by field
        is for audit purposes only and does not grant implicit access.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, ua.role as user_role 
            FROM agents a
            INNER JOIN user_agents ua ON a.id = ua.agent_id AND ua.user_id = ?
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
            # Simple role hierarchy (higher number = more privilege)
            roles = {'user': 1, 'admin': 2}
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

    def assign_user_to_agent(self, agent_id: int, user_id: int, role: str = 'user', granted_by: int = None) -> bool:
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

    def get_agent_users(self, agent_id: int) -> list:
        """Get all users assigned to an agent with their details."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT u.id, u.username, u.email, u.full_name, u.role as user_role, 
                       u.is_active, u.created_at, ua.role as agent_role, ua.granted_by
                FROM user_agents ua
                JOIN users u ON ua.user_id = u.id
                WHERE ua.agent_id = ?
                ORDER BY u.username
            """, (agent_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get users for agent {agent_id}: {e}")
            return []
        finally:
            conn.close()

    def update_agent(self, agent_id: int, name: str = None, description: str = None) -> Optional[Dict[str, Any]]:
        """Update an agent's name and/or description.
        
        Args:
            agent_id: The ID of the agent to update
            name: New name for the agent (optional)
            description: New description for the agent (optional)
            
        Returns:
            Updated agent dict or None if not found
            
        Raises:
            ValueError: If name is already taken by another agent
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Check if agent exists
            cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
            existing = cursor.fetchone()
            if not existing:
                return None
            
            # Build update query dynamically based on provided fields
            updates = []
            params = []
            
            if name is not None:
                # Check for name uniqueness (excluding current agent)
                cursor.execute("SELECT id FROM agents WHERE name = ? AND id != ?", (name, agent_id))
                if cursor.fetchone():
                    raise ValueError(f"Agent with name '{name}' already exists")
                updates.append("name = ?")
                params.append(name)
                
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            
            if not updates:
                # Nothing to update
                return dict(existing)
            
            params.append(agent_id)
            query = f"UPDATE agents SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            
            return self.get_agent_by_id(agent_id)
        finally:
            conn.close()

    def delete_agent(self, agent_id: int) -> bool:
        """Delete an agent and all related records (cascade deletion).
        
        Deletion order (child tables first):
        1. Get all vector_db_names from prompt_configs (embedded in embedding_config JSON)
        2. Delete prompt_configs (via system_prompts)
        3. Delete system_prompts
        4. Delete user_agents
        5. Delete vector_db related records for each vector_db_name
        6. Nullify audit_logs resource_id
        7. Delete agents
        
        Args:
            agent_id: The ID of the agent to delete
            
        Returns:
            True if agent was deleted, False if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # Check if agent exists
            cursor.execute("SELECT id FROM agents WHERE id = ?", (agent_id,))
            if not cursor.fetchone():
                return False
            
            # Get all vector_db_names associated with this agent from prompt_configs
            cursor.execute("""
                SELECT pc.embedding_config 
                FROM prompt_configs pc
                JOIN system_prompts sp ON pc.prompt_id = sp.id
                WHERE sp.agent_id = ?
            """, (agent_id,))
            
            vector_db_names = set()
            for row in cursor.fetchall():
                if row['embedding_config']:
                    try:
                        config = json.loads(row['embedding_config']) if isinstance(row['embedding_config'], str) else row['embedding_config']
                        if config and 'vectorDbName' in config:
                            vector_db_names.add(config['vectorDbName'])
                    except (json.JSONDecodeError, TypeError):
                        pass
            
            # 1. Delete prompt_configs for prompts belonging to this agent
            cursor.execute("""
                DELETE FROM prompt_configs 
                WHERE prompt_id IN (SELECT id FROM system_prompts WHERE agent_id = ?)
            """, (agent_id,))
            
            # 2. Delete system_prompts
            cursor.execute("DELETE FROM system_prompts WHERE agent_id = ?", (agent_id,))
            
            # 3. Delete user_agents
            cursor.execute("DELETE FROM user_agents WHERE agent_id = ?", (agent_id,))
            
            # 4. Delete vector_db related records and ChromaDB folders for each vector_db_name
            chroma_base_path = DB_DIR.parent / "data" / "indexes"
            for vdb_name in vector_db_names:
                cursor.execute("DELETE FROM vector_db_schedules WHERE vector_db_name = ?", (vdb_name,))
                cursor.execute("DELETE FROM document_index WHERE vector_db_name = ?", (vdb_name,))
                cursor.execute("DELETE FROM schema_drift_logs WHERE vector_db_name = ?", (vdb_name,))
                cursor.execute("DELETE FROM vector_db_registry WHERE name = ?", (vdb_name,))
                
                # Delete ChromaDB folder on disk
                chroma_path = chroma_base_path / vdb_name
                if chroma_path.exists() and chroma_path.is_dir():
                    try:
                        shutil.rmtree(chroma_path)
                        logger.info(f"Deleted ChromaDB folder: {chroma_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete ChromaDB folder {chroma_path}: {e}")
            
            # 5. Nullify audit_logs resource_id for this agent
            cursor.execute("""
                UPDATE audit_logs 
                SET resource_id = NULL 
                WHERE resource_type = 'agent' AND resource_id = ?
            """, (str(agent_id),))
            
            # 6. Delete the agent itself
            cursor.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            
            conn.commit()
            logger.info(f"Successfully deleted agent {agent_id} and all related records (vector_dbs: {vector_db_names})")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete agent {agent_id}: {e}")
            raise
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
            user = db.get_user_by_external_id("some_external_id")
    
    Returns:
        DatabaseService: The global database service instance
    """
    return db_service
