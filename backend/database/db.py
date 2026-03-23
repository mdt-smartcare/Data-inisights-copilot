"""
PostgreSQL database service for user authentication and configuration management.
"""
import psycopg2
import psycopg2.extras
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import hashlib

from backend.core.logging import get_logger
from backend.database.queries import (
    UserQueries,
    AgentQueries,
    UserAgentQueries,
    PromptQueries,
    PromptConfigQueries,
    DBConnectionQueries,
    VectorDBQueries,
    MetricQueries,
    SQLExampleQueries,
    AuditLogQueries,
    SystemSettingsQueries,
    TableInfoQueries,
    EmbeddingCheckpointQueries
)
from backend.database.base_repository import BaseRepository

logger = get_logger(__name__)

# Database directory for data storage
DB_DIR = Path(__file__).parent.parent / "data"


class DatabaseService(BaseRepository):
    """PostgreSQL database service for user and configuration management.
    
    This service handles database operations including:
    - User management (OIDC JIT provisioning, role assignment)
    - System prompt versioning and configuration
    - Database connection management
    - Agent RBAC
    
    Inherits from BaseRepository for common database operations like:
    - fetch_one(): SELECT single row
    - fetch_all(): SELECT multiple rows
    - execute_write(): INSERT/UPDATE/DELETE query execution
    - execute_returning(): INSERT/UPDATE with RETURNING clause
    - transaction(): Context manager for multi-query transactions
    
    Note: User authentication is handled by Keycloak/OIDC.
    Users are created via Just-In-Time provisioning on first login.
    """
    
    def __init__(self, postgres_uri: str = None):
        """Initialize the database service.
        
        Args:
            postgres_uri: Optional PostgreSQL connection URI.
                         If not provided, constructs from environment variables.
        """
        if postgres_uri:
            self.postgres_uri = postgres_uri
        else:
            # Construct from environment or use defaults
            from backend.config import Settings
            settings = Settings()
            self.postgres_uri = settings.postgres_uri
        
        # Initialize BaseRepository with get_connection method
        super().__init__(self.get_connection)
        
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
            runner = MigrationRunner(self.postgres_uri)
            applied = runner.run_pending_migrations()
            if applied:
                logger.info(f"Applied {len(applied)} database migrations: {applied}")
        except ImportError:
            # Fallback for when running from different contexts
            try:
                from backend.database.migrations import MigrationRunner
                runner = MigrationRunner(self.postgres_uri)
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
        
        This method only ensures we can connect and runs migrations.
        ALL schema creation is handled by migration files in the migrations/ directory.
        
        Industry Standard: Migrations-only approach
        - 001_initial_schema.sql: Creates all base tables
        - 002+: Incremental schema changes
        """
        try:
            # Just ensure we can connect
            conn = self.get_connection()
            conn.close()
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def get_connection(self) -> psycopg2.extensions.connection:
        """Get PostgreSQL database connection with dict cursor."""
        conn = psycopg2.connect(self.postgres_uri)
        # Use RealDict cursor for dict-like row access (similar to sqlite3.Row)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn


    def get_user_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user information by OIDC external ID (Keycloak sub claim).
        
        Args:
            external_id: The OIDC subject claim (sub) that uniquely identifies the user
            
        Returns:
            Dictionary with user data, or None if not found
        """
        return self.fetch_one(UserQueries.GET_BY_EXTERNAL_ID, (external_id,))
    
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
        try:
            # Check if user already exists by external_id
            existing_user = self.get_user_by_external_id(external_id)
            
            if existing_user:
                # Update existing user's info (but not role - that's managed locally)
                self.execute_write(UserQueries.UPDATE_OIDC_USER, (email, full_name, external_id))
                
                # Fetch updated user
                user = self.get_user_by_external_id(external_id)
                logger.info(f"OIDC user updated: {username or external_id}")
                return user
            else:
                # Create new user with OIDC info
                # Use external_id as username if preferred_username not provided
                effective_username = username or external_id[:50]  # Truncate to fit column
                
                # For OIDC users, we don't have a password - use a placeholder
                # The password_hash column still exists but won't be used for OIDC auth
                placeholder_hash = "OIDC_USER_NO_PASSWORD"
                
                user = self.execute_returning(
                    UserQueries.INSERT_USER,
                    (effective_username, email, placeholder_hash, full_name, default_role, external_id)
                )
                
                logger.info(f"OIDC user created: {effective_username} with role: {default_role}")
                return user
                
        except (psycopg2.IntegrityError, psycopg2.DatabaseError) as e:
            logger.error(f"OIDC user upsert failed (integrity error): {e}")
            # This could happen if username conflicts with existing local user
            raise ValueError(f"User with this identity already exists: {e}")
        except Exception as e:
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
        affected = self.execute_write(UserQueries.UPDATE_ROLE, (new_role, user_id))
        
        if affected > 0:
            logger.info(f"User {user_id} role updated to: {new_role}")
            return True
        return False
    
    def list_all_users(self) -> List[Dict[str, Any]]:
        """List all users in the system.
        
        Returns:
            List of user dictionaries (without password_hash)
        """
        return self.fetch_all(UserQueries.LIST_ALL)

    def search_users(self, query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        """Search users by username or email.
        
        Args:
            query: Search query string (matches username or email)
            limit: Maximum number of results
            
        Returns:
            List of matching user dictionaries
        """
        if query:
            search_pattern = f"%{query}%"
            return self.fetch_all(UserQueries.SEARCH_WITH_PATTERN, (search_pattern, search_pattern, search_pattern, limit))
        else:
            return self.fetch_all(UserQueries.SEARCH_ALL_ACTIVE, (limit,))

    def get_users_by_emails(self, emails: List[str]) -> List[Dict[str, Any]]:
        """Get users by a list of email addresses.
        
        Args:
            emails: List of email addresses to look up
            
        Returns:
            List of user dictionaries for matching emails
        """
        if not emails:
            return []
        
        # Normalize emails to lowercase
        normalized_emails = [e.lower().strip() for e in emails if e and e.strip()]
        if not normalized_emails:
            return []
        
        # Build dynamic query with placeholders
        placeholders = ','.join(['%s' for _ in normalized_emails])
        query = UserQueries.GET_BY_EMAILS_TEMPLATE.format(placeholders=placeholders)
        return self.fetch_all(query, tuple(normalized_emails))
    
    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user account.
        
        Args:
            user_id: The user's database ID
            
        Returns:
            True if update succeeded, False if user not found
        """
        affected = self.execute_write(UserQueries.DEACTIVATE, (user_id,))
        
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
        affected = self.execute_write(UserQueries.ACTIVATE, (user_id,))
        
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
        return self.fetch_one(UserQueries.GET_BY_ID, (user_id,))

    def get_config_by_id(self, config_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific configuration by ID."""
        return self.fetch_one(PromptConfigQueries.GET_BY_ID, (config_id,))
    
    def get_latest_active_prompt(self, agent_id: Optional[int] = None) -> Optional[str]:
        """Get the latest active system prompt.
        
        Returns:
            The prompt text of the row where is_active=1 (ordered by version desc),
            or None if no active prompt exists.
        """
        if agent_id:
            row = self.fetch_one(PromptQueries.GET_LATEST_ACTIVE, (agent_id,))
        else:
            row = self.fetch_one(PromptQueries.GET_LATEST_ACTIVE_GLOBAL)
        
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
        with self.transaction() as (conn, cursor):
            # 1. Get the current max version number
            cursor.execute(PromptQueries.GET_MAX_VERSION)
            result = cursor.fetchone()
            current_max = result[0] if result and result[0] is not None else 0
            new_version = current_max + 1

            # 2. Deactivate all existing prompts for this agent (or global if None)
            if agent_id:
                cursor.execute(PromptQueries.DEACTIVATE_ACTIVE_FOR_AGENT, (agent_id,))
            else:
                cursor.execute(PromptQueries.DEACTIVATE_ACTIVE_GLOBAL)

            # 3. Insert the new prompt into system_prompts
            cursor.execute(PromptQueries.INSERT_PROMPT, (
                prompt_text, new_version, 1, user_id, agent_id
            ))
            
            prompt_id = cursor.fetchone()['id']

            # 4. Insert configuration metadata into prompt_configs
            cursor.execute(PromptConfigQueries.INSERT_CONFIG, (
                prompt_id, connection_id, schema_selection,
                data_dictionary, reasoning, example_questions,
                data_source_type, ingestion_documents,
                ingestion_file_name, ingestion_file_type,
                embedding_config, retriever_config,
                chunking_config, llm_config
            ))
            
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

    def get_active_config(self, agent_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get the configuration metadata for the currently active prompt."""
        if agent_id:
            return self.fetch_one(PromptConfigQueries.GET_ACTIVE_CONFIG_FOR_AGENT, (agent_id,))
        else:
            return self.fetch_one(PromptConfigQueries.GET_ACTIVE_CONFIG_GLOBAL)

    def get_all_prompts(self, agent_id: Optional[int] = None) -> list[Dict[str, Any]]:
        """Get all system prompt versions history with configuration metadata."""
        if agent_id:
            rows = self.fetch_all(PromptConfigQueries.GET_ALL_FOR_AGENT, (agent_id,))
        else:
            rows = self.fetch_all(PromptConfigQueries.GET_ALL_GLOBAL)
        
        # Convert version to string for API validation
        for row in rows:
            row['version'] = str(row['version'])
        
        return rows

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
        try:
            result = self.execute_returning(DBConnectionQueries.INSERT, (name, uri, engine_type, created_by))
            return result['id']
        except psycopg2.IntegrityError:
            raise ValueError(f"Connection with name '{name}' already exists")

    def get_db_connections(self) -> list[Dict[str, Any]]:
        """Get all saved database connections."""
        return self.fetch_all(DBConnectionQueries.LIST_ALL)

    def delete_db_connection(self, connection_id: int) -> bool:
        """Delete a database connection by ID."""
        affected = self.execute_write(DBConnectionQueries.DELETE, (connection_id,))
        return affected > 0

    def get_db_connection_by_id(self, connection_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific database connection by ID."""
        return self.fetch_one(DBConnectionQueries.GET_BY_ID, (connection_id,))
        
    def get_vector_db_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get vector db by name to check existence/collisions."""
        return self.fetch_one(VectorDBQueries.GET_BY_NAME, (name,))

    def register_vector_db(self, name: str, data_source_id: str, created_by: Optional[str] = None) -> int:
        """Register a new vector DB namespace."""
        try:
            result = self.execute_returning(VectorDBQueries.INSERT, (name, data_source_id, created_by))
            return result['id']
        except psycopg2.IntegrityError:
            raise ValueError(f"Vector DB with name '{name}' already exists.")

    def get_active_metrics(self) -> list[Dict[str, Any]]:
        """Get all active metric definitions ordered by priority.
        
        Returns:
            List of metric dictionary objects
        """
        try:
            return self.fetch_all(MetricQueries.GET_ACTIVE)
        except psycopg2.OperationalError:
            # Table might not exist yet if migration hasn't run or in tests
            logger.warning("metric_definitions table not found")
            return []

    def get_sql_examples(self) -> list[Dict[str, Any]]:
        """Get all SQL examples for few-shot learning."""
        try:
            return self.fetch_all(SQLExampleQueries.GET_ALL)
        except psycopg2.OperationalError:
            logger.warning("sql_examples table not found")
            return []

    def create_agent(self, name: str, description: str = None, agent_type: str = 'sql', 
                    db_connection_uri: str = None, rag_config_id: int = None, 
                    system_prompt: str = None, created_by: int = None) -> Dict[str, Any]:
        """Create a new agent and automatically assign the creator as admin."""
        try:
            with self.transaction() as (conn, cursor):
                # Insert agent
                cursor.execute(AgentQueries.INSERT_AGENT, 
                    (name, description, agent_type, db_connection_uri, rag_config_id, system_prompt, created_by))
                agent_id = cursor.fetchone()['id']
                
                # Auto-assign creator as admin in user_agents table
                if created_by:
                    cursor.execute(UserAgentQueries.ASSIGN_USER, 
                        (created_by, agent_id, 'admin', created_by))
                
            return self.get_agent_by_id(agent_id)
        except psycopg2.IntegrityError:
            raise ValueError(f"Agent with name '{name}' already exists")

    def get_agent_by_id(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent by ID."""
        return self.fetch_one(AgentQueries.GET_BY_ID, (agent_id,))

    def get_agents_for_user(self, user_id: int) -> list[Dict[str, Any]]:
        """Get all agents a user has access to."""
        return self.fetch_all(AgentQueries.GET_FOR_USER, (user_id,))

    def get_agents_for_admin(self, user_id: int) -> list[Dict[str, Any]]:
        """Get all agents an admin has access to via user_agents table.
        
        Access is determined solely by user_agents assignments. The created_by field
        is for audit purposes only and does not grant implicit access.
        """
        return self.fetch_all(AgentQueries.GET_FOR_ADMIN, (user_id,))

    def check_user_access(self, user_id: int, agent_id: int, required_role: str = None) -> bool:
        """Check if user has access to an agent."""
        row = self.fetch_one(UserAgentQueries.CHECK_ACCESS, (user_id, agent_id))
        
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
        return self.fetch_all(AgentQueries.LIST_ALL)

    def assign_user_to_agent(self, agent_id: int, user_id: int, role: str = 'user', granted_by: int = None) -> bool:
        """Assign a user to an agent with a specific role."""
        try:
            self.execute_write(UserAgentQueries.ASSIGN_USER, (user_id, agent_id, role, granted_by))
            return True
        except Exception as e:
            logger.error(f"Failed to assign user {user_id} to agent {agent_id}: {e}")
            return False

    def revoke_user_access(self, agent_id: int, user_id: int) -> bool:
        """Revoke a user's access to an agent."""
        try:
            affected = self.execute_write(UserAgentQueries.REVOKE_ACCESS, (user_id, agent_id))
            return affected > 0
        except Exception as e:
            logger.error(f"Failed to revoke access for user {user_id} from agent {agent_id}: {e}")
            return False

    def get_agent_users(self, agent_id: int) -> list:
        """Get all users assigned to an agent with their details."""
        try:
            return self.fetch_all(UserAgentQueries.GET_AGENT_USERS, (agent_id,))
        except Exception as e:
            logger.error(f"Failed to get users for agent {agent_id}: {e}")
            return []

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
        # Check if agent exists
        existing = self.fetch_one(AgentQueries.CHECK_EXISTS, (agent_id,))
        if not existing:
            return None
        
        # Build update query dynamically based on provided fields
        updates = []
        params = []
        
        if name is not None:
            # Check for name uniqueness (excluding current agent)
            conflict = self.fetch_one(AgentQueries.CHECK_NAME_EXISTS, (name, agent_id))
            if conflict:
                raise ValueError(f"Agent with name '{name}' already exists")
            updates.append("name = %s")
            params.append(name)
            
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        
        if not updates:
            # Nothing to update
            return self.get_agent_by_id(agent_id)
        
        # Execute dynamic update
        params.append(agent_id)
        if len(updates) == 2:
            self.execute_write(AgentQueries.UPDATE_NAME_AND_DESCRIPTION, tuple(params))
        elif 'name' in updates[0]:
            self.execute_write(AgentQueries.UPDATE_NAME, (name, agent_id))
        else:
            self.execute_write(AgentQueries.UPDATE_DESCRIPTION, (description, agent_id))
        
        return self.get_agent_by_id(agent_id)

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
        with self.transaction() as (conn, cursor):
            # Check if agent exists
            cursor.execute(AgentQueries.CHECK_EXISTS, (agent_id,))
            if not cursor.fetchone():
                return False
            
            # Get all vector_db_names associated with this agent from prompt_configs
            cursor.execute(PromptConfigQueries.GET_EMBEDDING_CONFIGS_BY_AGENT, (agent_id,))
            
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
            cursor.execute(PromptConfigQueries.DELETE_BY_PROMPT_AGENT, (agent_id,))
            
            # 2. Delete system_prompts
            cursor.execute(PromptQueries.DELETE_BY_AGENT, (agent_id,))
            
            # 3. Delete user_agents
            cursor.execute(UserAgentQueries.DELETE_BY_AGENT, (agent_id,))
            
            # 4. Delete vector_db related records and ChromaDB folders for each vector_db_name
            chroma_base_path = DB_DIR.parent / "data" / "indexes"
            for vdb_name in vector_db_names:
                cursor.execute(VectorDBQueries.DELETE_SCHEDULES_BY_NAME, (vdb_name,))
                cursor.execute(VectorDBQueries.DELETE_DOCUMENT_INDEX_BY_NAME, (vdb_name,))
                cursor.execute(VectorDBQueries.DELETE_SCHEMA_DRIFT_BY_NAME, (vdb_name,))
                cursor.execute(VectorDBQueries.DELETE_BY_NAME, (vdb_name,))
                
                # Delete ChromaDB folder on disk
                chroma_path = chroma_base_path / vdb_name
                if chroma_path.exists() and chroma_path.is_dir():
                    try:
                        shutil.rmtree(chroma_path)
                        logger.info(f"Deleted ChromaDB folder: {chroma_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete ChromaDB folder {chroma_path}: {e}")
            
            # 5. Nullify audit_logs resource_id for this agent
            cursor.execute(AuditLogQueries.NULLIFY_AGENT_RESOURCE, (str(agent_id),))
            
            # 6. Delete the agent itself
            cursor.execute(AgentQueries.DELETE, (agent_id,))
            
            logger.info(f"Successfully deleted agent {agent_id} and all related records (vector_dbs: {vector_db_names})")
            return True

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
