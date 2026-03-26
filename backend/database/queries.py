"""
Centralized SQL query repository for PostgreSQL database operations.

All SQL queries are organized by domain classes for easy maintenance and future migrations.
Queries are defined as string constants with %s parameter placeholders.
Each query includes parameter documentation in comments.

This module separates data access (SQL) from business logic (DatabaseService).
"""


class UserQueries:
    """SQL query constants for user management operations."""
    
    # Read operations
    GET_BY_EXTERNAL_ID = """
        SELECT id, username, email, full_name, role, is_active, external_id 
        FROM users 
        WHERE external_id = %s
    """
    # Parameters: (external_id,)
    
    GET_BY_ID = """
        SELECT id, username, email, full_name, role, is_active, external_id, created_at 
        FROM users 
        WHERE id = %s
    """
    # Parameters: (user_id,)
    
    LIST_ALL = """
        SELECT id, username, email, full_name, role, is_active, external_id, created_at 
        FROM users 
        ORDER BY created_at DESC
    """
    # Parameters: none
    
    SEARCH_WITH_PATTERN = """
        SELECT id, username, email, full_name, role, is_active, external_id, created_at 
        FROM users 
        WHERE is_active = 1 
          AND (username LIKE %s OR email LIKE %s OR full_name LIKE %s)
        ORDER BY username
        LIMIT %s
    """
    # Parameters: (search_pattern, search_pattern, search_pattern, limit)
    
    SEARCH_ALL_ACTIVE = """
        SELECT id, username, email, full_name, role, is_active, external_id, created_at 
        FROM users 
        WHERE is_active = 1
        ORDER BY username
        LIMIT %s
    """
    # Parameters: (limit,)
    
    GET_BY_EMAILS_TEMPLATE = """
        SELECT id, username, email, full_name, role, is_active, external_id, created_at 
        FROM users 
        WHERE is_active = 1 AND LOWER(email) IN ({placeholders})
        ORDER BY email
    """
    # Parameters: list of normalized_emails (dynamic placeholders)
    
    # Write operations
    INSERT_USER = """
        INSERT INTO users (username, email, password_hash, full_name, role, external_id, is_active) 
        VALUES (%s, %s, %s, %s, %s, %s, 1)
        RETURNING id, username, email, full_name, role, is_active, external_id, created_at
    """
    # Parameters: (username, email, password_hash, full_name, role, external_id)
    
    UPDATE_OIDC_USER = """
        UPDATE users 
        SET email = COALESCE(%s, email),
            full_name = COALESCE(%s, full_name),
            updated_at = CURRENT_TIMESTAMP
        WHERE external_id = %s
    """
    # Parameters: (email, full_name, external_id)
    
    UPDATE_ROLE = """
        UPDATE users 
        SET role = %s, updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    """
    # Parameters: (role, user_id)
    
    DEACTIVATE = """
        UPDATE users 
        SET is_active = 0, updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    """
    # Parameters: (user_id,)
    
    ACTIVATE = """
        UPDATE users 
        SET is_active = 1, updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    """
    # Parameters: (user_id,)


class AgentQueries:
    """SQL query constants for agent management operations."""
    
    GET_BY_ID = "SELECT * FROM agents WHERE id = %s"
    # Parameters: (agent_id,)
    
    LIST_ALL = "SELECT * FROM agents"
    # Parameters: none
    
    GET_FOR_USER = """
        SELECT a.*, ua.role as user_role 
        FROM agents a
        JOIN user_agents ua ON a.id = ua.agent_id
        WHERE ua.user_id = %s
    """
    # Parameters: (user_id,)
    
    GET_FOR_ADMIN = """
        SELECT a.*, ua.role as user_role 
        FROM agents a
        INNER JOIN user_agents ua ON a.id = ua.agent_id AND ua.user_id = %s
    """
    # Parameters: (user_id,)
    
    CHECK_NAME_EXISTS = """
        SELECT id 
        FROM agents 
        WHERE name = %s AND id != %s
    """
    # Parameters: (name, exclude_agent_id)
    
    CHECK_EXISTS = "SELECT id FROM agents WHERE id = %s"
    # Parameters: (agent_id,)
    
    INSERT_AGENT = """
        INSERT INTO agents (name, description, type, db_connection_uri, system_prompt, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    # Parameters: (name, description, agent_type, db_connection_uri, system_prompt, created_by)
    
    UPDATE_NAME_AND_DESCRIPTION = """
        UPDATE agents 
        SET name = %s, description = %s
        WHERE id = %s
    """
    # Parameters: (name, description, agent_id)
    
    UPDATE_NAME = """
        UPDATE agents 
        SET name = %s
        WHERE id = %s
    """
    # Parameters: (name, agent_id)
    
    UPDATE_DESCRIPTION = """
        UPDATE agents 
        SET description = %s
        WHERE id = %s
    """
    # Parameters: (description, agent_id)
    
    DELETE = "DELETE FROM agents WHERE id = %s"
    # Parameters: (agent_id,)


class UserAgentQueries:
    """SQL query constants for user-agent access control."""
    
    CHECK_ACCESS = """
        SELECT role 
        FROM user_agents 
        WHERE user_id = %s AND agent_id = %s
    """
    # Parameters: (user_id, agent_id)
    
    ASSIGN_USER = """
        INSERT INTO user_agents (user_id, agent_id, role, granted_by)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, agent_id) 
        DO UPDATE SET role = EXCLUDED.role, granted_by = EXCLUDED.granted_by
    """
    # Parameters: (user_id, agent_id, role, granted_by)
    
    REVOKE_ACCESS = """
        DELETE FROM user_agents 
        WHERE user_id = %s AND agent_id = %s
    """
    # Parameters: (user_id, agent_id)
    
    GET_AGENT_USERS = """
        SELECT u.id, u.username, u.email, u.full_name, u.role as user_role, 
               u.is_active, u.created_at, ua.role as agent_role, ua.granted_by
        FROM user_agents ua
        JOIN users u ON ua.user_id = u.id
        WHERE ua.agent_id = %s
        ORDER BY u.username
    """
    # Parameters: (agent_id,)
    
    DELETE_BY_AGENT = """
        DELETE FROM user_agents 
        WHERE agent_id = %s
    """
    # Parameters: (agent_id,)


class PromptQueries:
    """SQL query constants for system prompt operations."""
    
    GET_LATEST_ACTIVE = """
        SELECT prompt_text 
        FROM system_prompts 
        WHERE is_active = 1 AND agent_id = %s 
        ORDER BY version DESC 
        LIMIT 1
    """
    # Parameters: (agent_id,)
    
    GET_LATEST_ACTIVE_GLOBAL = """
        SELECT prompt_text 
        FROM system_prompts 
        WHERE is_active = 1 AND agent_id IS NULL 
        ORDER BY version DESC 
        LIMIT 1
    """
    # Parameters: none
    
    GET_MAX_VERSION = "SELECT MAX(version) FROM system_prompts"
    # Parameters: none
    
    GET_ALL_FOR_AGENT = """
        SELECT 
            sp.id, 
            sp.prompt_text, 
            sp.version, 
            sp.is_active, 
            sp.created_at, 
            sp.created_by,
            sp.agent_id,
            u.username as created_by_username
        FROM system_prompts sp
        LEFT JOIN users u ON sp.created_by = u.username
        WHERE sp.agent_id = %s
        ORDER BY sp.version DESC
    """
    # Parameters: (agent_id,)
    
    GET_ALL_GLOBAL = """
        SELECT 
            sp.id, 
            sp.prompt_text, 
            sp.version, 
            sp.is_active, 
            sp.created_at, 
            sp.created_by,
            sp.agent_id,
            u.username as created_by_username
        FROM system_prompts sp
        LEFT JOIN users u ON sp.created_by = u.username
        WHERE sp.agent_id IS NULL
        ORDER BY sp.version DESC
    """
    # Parameters: none
    
    DEACTIVATE_ACTIVE_FOR_AGENT = """
        UPDATE system_prompts 
        SET is_active = 0 
        WHERE is_active = 1 AND agent_id = %s
    """
    # Parameters: (agent_id,)
    
    DEACTIVATE_ACTIVE_GLOBAL = """
        UPDATE system_prompts 
        SET is_active = 0 
        WHERE is_active = 1 AND agent_id IS NULL
    """
    # Parameters: none
    
    INSERT_PROMPT = """
        INSERT INTO system_prompts (
            prompt_text, version, is_active, created_by, agent_id
        ) VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """
    # Parameters: (prompt_text, version, is_active, created_by, agent_id)
    
    DELETE_BY_AGENT = """
        DELETE FROM system_prompts 
        WHERE agent_id = %s
    """
    # Parameters: (agent_id,)


class PromptConfigQueries:
    """SQL query constants for prompt configuration operations."""
    
    GET_BY_ID = """
        SELECT 
            sp.id as prompt_id,
            pc.connection_id,
            pc.schema_selection,
            pc.data_dictionary,
            pc.reasoning,
            pc.example_questions,
            pc.data_source_type,
            pc.embedding_config,
            pc.retriever_config,
            pc.chunking_config,
            pc.llm_config,
            pc.ingestion_documents,
            pc.ingestion_file_name,
            pc.ingestion_file_type,
            sp.prompt_text,
            sp.agent_id,
            sp.version,
            dc.name AS db_name,
            dc.uri AS db_uri,
            dc.engine_type
        FROM system_prompts sp
        LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
        LEFT JOIN db_connections dc ON pc.connection_id = dc.id
        WHERE sp.id = %s
    """
    # Parameters: (config_id,)
    
    GET_ACTIVE_CONFIG_FOR_AGENT = """
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
        LEFT JOIN users u ON sp.created_by = u.username
        LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
        WHERE sp.is_active = 1 AND sp.agent_id = %s
        LIMIT 1
    """
    # Parameters: (agent_id,)
    
    GET_ACTIVE_CONFIG_GLOBAL = """
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
        LEFT JOIN users u ON sp.created_by = u.username
        LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
        WHERE sp.is_active = 1 AND sp.agent_id IS NULL
        LIMIT 1
    """
    # Parameters: none
    
    INSERT_CONFIG = """
        INSERT INTO prompt_configs (
            prompt_id, connection_id, schema_selection, 
            data_dictionary, reasoning, example_questions,
            data_source_type, ingestion_documents,
            ingestion_file_name, ingestion_file_type,
            embedding_config, retriever_config,
            chunking_config, llm_config
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    # Parameters: (prompt_id, connection_id, schema_selection, data_dictionary, reasoning, 
    #              example_questions, data_source_type, ingestion_documents, ingestion_file_name,
    #              ingestion_file_type, embedding_config, retriever_config, chunking_config, llm_config)
    
    DELETE_BY_PROMPT_AGENT = """
        DELETE FROM prompt_configs 
        WHERE prompt_id IN (SELECT id FROM system_prompts WHERE agent_id = %s)
    """
    # Parameters: (agent_id,)
    
    GET_EMBEDDING_CONFIGS_BY_AGENT = """
        SELECT pc.embedding_config 
        FROM system_prompts sp
        JOIN prompt_configs pc ON sp.id = pc.prompt_id
        WHERE sp.agent_id = %s
    """
    # Parameters: (agent_id,)
    
    GET_ALL_FOR_AGENT = """
        SELECT 
            sp.id,
            sp.prompt_text, 
            sp.version, 
            sp.is_active, 
            sp.created_at, 
            sp.created_by,
            sp.agent_id,
            u.username as created_by_username,
            sp.id AS config_id,
            pc.schema_selection,
            pc.connection_id,
            pc.data_dictionary,
            pc.reasoning,
            pc.example_questions,
            pc.data_source_type,
            pc.embedding_config,
            pc.retriever_config,
            pc.chunking_config,
            pc.llm_config,
            pc.ingestion_documents,
            pc.ingestion_file_name,
            pc.ingestion_file_type
        FROM system_prompts sp
        LEFT JOIN users u ON sp.created_by = u.username
        LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
        WHERE sp.agent_id = %s
        ORDER BY sp.version DESC
    """
    # Parameters: (agent_id,)
    
    GET_ALL_GLOBAL = """
        SELECT 
            sp.id,
            sp.prompt_text, 
            sp.version, 
            sp.is_active, 
            sp.created_at, 
            sp.created_by,
            sp.agent_id,
            u.username as created_by_username,
            sp.id AS config_id,
            pc.schema_selection,
            pc.connection_id,
            pc.data_dictionary,
            pc.reasoning,
            pc.example_questions,
            pc.data_source_type,
            pc.embedding_config,
            pc.retriever_config,
            pc.chunking_config,
            pc.llm_config,
            pc.ingestion_documents,
            pc.ingestion_file_name,
            pc.ingestion_file_type
        FROM system_prompts sp
        LEFT JOIN users u ON sp.created_by = u.username
        LEFT JOIN prompt_configs pc ON sp.id = pc.prompt_id
        WHERE sp.agent_id IS NULL
        ORDER BY sp.version DESC
    """
    # Parameters: none


class DBConnectionQueries:
    """SQL query constants for database connection operations."""
    
    LIST_ALL = """
        SELECT id, name, uri, engine_type, created_at 
        FROM db_connections 
        ORDER BY created_at DESC
    """
    # Parameters: none
    
    GET_BY_ID = """
        SELECT id, name, uri, engine_type 
        FROM db_connections 
        WHERE id = %s
    """
    # Parameters: (connection_id,)
    
    INSERT = """
        INSERT INTO db_connections (name, uri, engine_type, created_by) 
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """
    # Parameters: (name, uri, engine_type, created_by)
    
    DELETE = """
        DELETE FROM db_connections 
        WHERE id = %s
    """
    # Parameters: (connection_id,)


class VectorDBQueries:
    """SQL query constants for vector database registry operations."""
    
    GET_BY_NAME = """
        SELECT id, name, data_source_id, created_at, created_by 
        FROM vector_db_registry 
        WHERE name = %s
    """
    # Parameters: (name,)
    
    INSERT = """
        INSERT INTO vector_db_registry (name, data_source_id, created_by) 
        VALUES (%s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            data_source_id = EXCLUDED.data_source_id,
            created_by = EXCLUDED.created_by
        RETURNING id
    """
    # Parameters: (name, data_source_id, created_by[UUID])
    
    DELETE_BY_NAME = """
        DELETE FROM vector_db_registry 
        WHERE name = %s
    """
    # Parameters: (name,)
    
    DELETE_SCHEDULES_BY_NAME = """
        DELETE FROM vector_db_schedules 
        WHERE vector_db_name = %s
    """
    # Parameters: (vector_db_name,)
    
    DELETE_DOCUMENT_INDEX_BY_NAME = """
        DELETE FROM document_index 
        WHERE vector_db_name = %s
    """
    # Parameters: (vector_db_name,)


class MetricQueries:
    """SQL query constants for metrics operations."""
    
    GET_ACTIVE = """
        SELECT id, name, description, regex_pattern, sql_template, priority 
        FROM metric_definitions 
        WHERE is_active = 1 
        ORDER BY priority ASC
    """
    # Parameters: none


class SQLExampleQueries:
    """SQL query constants for SQL examples (few-shot learning)."""
    
    GET_ALL = """
        SELECT * 
        FROM sql_examples 
        ORDER BY created_at DESC
    """
    # Parameters: none


class AuditLogQueries:
    """SQL query constants for audit log operations."""
    
    NULLIFY_AGENT_RESOURCE = """
        UPDATE audit_logs 
        SET resource_id = NULL 
        WHERE resource_type = 'agent' AND resource_id = %s
    """
    # Parameters: (agent_id,)  # agent_id is UUID string


class TableInfoQueries:
    """SQL query constants for retrieving table and column information.
    
    Uses PostgreSQL information_schema.
    """
    
    GET_TABLE_COLUMNS = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """
    # Parameters: (table_name,)
    
    GET_ALL_TABLES = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """
    # Parameters: none


class EmbeddingCheckpointQueries:
    """SQL query constants for embedding checkpoint operations."""
    
    UPSERT_CHECKPOINT = """
        INSERT INTO embedding_checkpoints (job_id, batch_id, last_processed_record, status, updated_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (job_id, batch_id)
        DO UPDATE SET 
            last_processed_record = EXCLUDED.last_processed_record,
            status = EXCLUDED.status,
            updated_at = CURRENT_TIMESTAMP
    """
    # Parameters: (job_id, batch_id, last_processed_record, status)
    
    UPSERT_JOB_STATE = """
        INSERT INTO embedding_job_states (job_id, state, metadata, updated_at)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (job_id)
        DO UPDATE SET 
            state = EXCLUDED.state,
            metadata = EXCLUDED.metadata,
            updated_at = CURRENT_TIMESTAMP
    """
    # Parameters: (job_id, state, metadata)


class SystemSettingsQueries:
    """SQL query constants for system settings operations."""
    
    GET_BY_CATEGORY_KEY = """
        SELECT id, category, key, value, description, updated_at, updated_by
        FROM system_settings
        WHERE category = %s AND key = %s
    """
    # Parameters: (category, key)
    
    GET_BY_CATEGORY = """
        SELECT id, category, key, value, description, updated_at, updated_by
        FROM system_settings
        WHERE category = %s
        ORDER BY key
    """
    # Parameters: (category,)
    
    GET_ALL = """
        SELECT id, category, key, value, description, updated_at, updated_by
        FROM system_settings
        ORDER BY category, key
    """
    # Parameters: none
    
    UPSERT_SETTING = """
        INSERT INTO system_settings (category, key, value, description, updated_by)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (category, key)
        DO UPDATE SET 
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            updated_by = EXCLUDED.updated_by,
            updated_at = CURRENT_TIMESTAMP
    """
    # Parameters: (category, key, value, description, updated_by)
    
    UPDATE_VALUE = """
        UPDATE system_settings 
        SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
        WHERE category = %s AND key = %s
    """
    # Parameters: (value, updated_by, category, key)
    
    INSERT_HISTORY = """
        INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    # Parameters: (setting_id, category, key, previous_value, new_value, changed_by, change_reason)


__all__ = [
    'UserQueries',
    'AgentQueries',
    'UserAgentQueries',
    'PromptQueries',
    'PromptConfigQueries',
    'DBConnectionQueries',
    'VectorDBQueries',
    'MetricQueries',
    'SQLExampleQueries',
    'AuditLogQueries',
    'TableInfoQueries',
    'EmbeddingCheckpointQueries',
    'SystemSettingsQueries',
]
