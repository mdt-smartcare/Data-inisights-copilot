-- Migration: 001_initial_schema.sql
-- Description: Consolidated PostgreSQL schema from all SQLite migrations (000-021)
-- Author: PostgreSQL Migration
-- Date: 2026-03-19
-- Note: This consolidates all 21 SQLite migrations into one PostgreSQL-compatible schema
--       All ALTER TABLE additions from migrations 004-019 are incorporated into CREATE TABLE statements

-- ============================================
-- Core User Management
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT DEFAULT 'user',
    is_active INTEGER DEFAULT 1,
    external_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_external_id ON users(external_id) WHERE external_id IS NOT NULL;

-- ============================================
-- Database Connections
-- ============================================
CREATE TABLE IF NOT EXISTS db_connections (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    uri TEXT NOT NULL,
    engine_type TEXT DEFAULT 'postgresql',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- ============================================
-- RAG Configurations (Versioning)
-- ============================================
CREATE TABLE IF NOT EXISTS rag_configurations (
    id SERIAL PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    version_number INTEGER NOT NULL,
    schema_snapshot TEXT NOT NULL,
    data_dictionary TEXT,
    prompt_template TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    published_by INTEGER,
    parent_version_id INTEGER,
    change_summary TEXT,
    config_hash TEXT NOT NULL,
    connection_id INTEGER REFERENCES db_connections(id),
    is_active INTEGER DEFAULT 0,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (published_by) REFERENCES users(id),
    FOREIGN KEY (parent_version_id) REFERENCES rag_configurations(id)
);

CREATE INDEX IF NOT EXISTS idx_rag_config_status ON rag_configurations(status);
CREATE INDEX IF NOT EXISTS idx_rag_config_version ON rag_configurations(version_number DESC);
CREATE INDEX IF NOT EXISTS idx_rag_config_created ON rag_configurations(created_at DESC);

-- ============================================
-- Agents
-- ============================================
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    type TEXT DEFAULT 'sql',
    db_connection_uri TEXT,
    rag_config_id INTEGER,
    system_prompt TEXT,
    embedding_model TEXT DEFAULT 'bge-m3',
    embedding_dimension INTEGER DEFAULT 1024,
    embedding_provider TEXT DEFAULT 'sentence-transformers',
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(rag_config_id) REFERENCES rag_configurations(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
);

-- ============================================
-- User-Agent RBAC
-- ============================================
CREATE TABLE IF NOT EXISTS user_agents (
    user_id INTEGER,
    agent_id INTEGER,
    role TEXT DEFAULT 'user',
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    granted_by INTEGER,
    PRIMARY KEY (user_id, agent_id),
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(agent_id) REFERENCES agents(id),
    FOREIGN KEY(granted_by) REFERENCES users(id)
);

-- ============================================
-- System Prompts
-- ============================================
CREATE TABLE IF NOT EXISTS system_prompts (
    id SERIAL PRIMARY KEY,
    prompt_text TEXT NOT NULL,
    version INTEGER NOT NULL,
    is_active INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    agent_id INTEGER REFERENCES agents(id)
);

-- ============================================
-- Prompt Configs
-- ============================================
CREATE TABLE IF NOT EXISTS prompt_configs (
    prompt_id INTEGER PRIMARY KEY,
    connection_id INTEGER,
    schema_selection TEXT,
    data_dictionary TEXT,
    reasoning TEXT,
    example_questions TEXT,
    data_source_type TEXT DEFAULT 'database',
    ingestion_documents TEXT,
    ingestion_file_name TEXT,
    ingestion_file_type TEXT,
    embedding_config TEXT,
    retriever_config TEXT,
    chunking_config TEXT,
    llm_config TEXT,
    FOREIGN KEY(prompt_id) REFERENCES system_prompts(id)
);

-- ============================================
-- Vector DB Registry
-- ============================================
CREATE TABLE IF NOT EXISTS vector_db_registry (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    data_source_id TEXT,
    embedding_model TEXT,
    llm TEXT,
    last_full_run TIMESTAMP,
    last_incremental_run TIMESTAMP,
    version TEXT DEFAULT '1.0.0',
    schema_snapshot TEXT,
    schema_snapshot_at TIMESTAMP,
    agent_id INTEGER REFERENCES agents(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- ============================================
-- Document Index (for incremental embeddings)
-- ============================================
CREATE TABLE IF NOT EXISTS document_index (
    id SERIAL PRIMARY KEY,
    vector_db_name TEXT NOT NULL,
    source_id TEXT NOT NULL,
    checksum TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vector_db_name, source_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_index_vdbname ON document_index(vector_db_name);

-- ============================================
-- Embedding Versions
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_versions (
    id SERIAL PRIMARY KEY,
    config_id INTEGER NOT NULL,
    version_hash TEXT NOT NULL UNIQUE,
    embedding_model TEXT NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    total_documents INTEGER NOT NULL DEFAULT 0,
    table_documents INTEGER NOT NULL DEFAULT 0,
    column_documents INTEGER NOT NULL DEFAULT 0,
    relationship_documents INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    generation_time_seconds REAL,
    validation_passed INTEGER DEFAULT 0,
    validation_details TEXT,
    error_message TEXT,
    error_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER NOT NULL,
    FOREIGN KEY (config_id) REFERENCES rag_configurations(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_versions_config ON embedding_versions(config_id);
CREATE INDEX IF NOT EXISTS idx_embedding_versions_status ON embedding_versions(status);

-- ============================================
-- Embedding Documents
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_documents (
    id SERIAL PRIMARY KEY,
    version_id INTEGER NOT NULL,
    document_id TEXT NOT NULL,
    document_type TEXT NOT NULL,
    source_table TEXT,
    source_column TEXT,
    content TEXT NOT NULL,
    embedding TEXT NOT NULL,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (version_id) REFERENCES embedding_versions(id) ON DELETE CASCADE,
    UNIQUE(version_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_docs_version ON embedding_documents(version_id);
CREATE INDEX IF NOT EXISTS idx_embedding_docs_type ON embedding_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_embedding_docs_table ON embedding_documents(source_table);

-- ============================================
-- RAG Audit Log
-- ============================================
CREATE TABLE IF NOT EXISTS rag_audit_log (
    id SERIAL PRIMARY KEY,
    config_id INTEGER,
    action TEXT NOT NULL,
    performed_by INTEGER NOT NULL,
    performed_by_email TEXT NOT NULL,
    performed_by_role TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changes TEXT,
    reason TEXT,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    FOREIGN KEY (config_id) REFERENCES rag_configurations(id) ON DELETE SET NULL,
    FOREIGN KEY (performed_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_rag_audit_user ON rag_audit_log(performed_by);
CREATE INDEX IF NOT EXISTS idx_rag_audit_action ON rag_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_rag_audit_timestamp ON rag_audit_log(performed_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_audit_config ON rag_audit_log(config_id);

-- ============================================
-- Notifications
-- ============================================
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    title TEXT NOT NULL,
    message TEXT,
    action_url TEXT,
    action_label TEXT,
    related_entity_type TEXT,
    related_entity_id INTEGER,
    channels TEXT DEFAULT '["in_app"]',
    status TEXT DEFAULT 'unread',
    read_at TIMESTAMP,
    dismissed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_status ON notifications(user_id, status);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type);
CREATE INDEX IF NOT EXISTS idx_notifications_priority ON notifications(priority);

-- ============================================
-- Notification Preferences
-- ============================================
CREATE TABLE IF NOT EXISTS notification_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    in_app_enabled INTEGER DEFAULT 1,
    email_enabled INTEGER DEFAULT 1,
    webhook_enabled INTEGER DEFAULT 0,
    webhook_url TEXT,
    webhook_format TEXT DEFAULT 'slack',
    notification_types TEXT DEFAULT '{}',
    quiet_hours_enabled INTEGER DEFAULT 0,
    quiet_hours_start TEXT,
    quiet_hours_end TEXT,
    quiet_hours_timezone TEXT DEFAULT 'UTC',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================
-- Notification Delivery Log
-- ============================================
CREATE TABLE IF NOT EXISTS notification_delivery_log (
    id SERIAL PRIMARY KEY,
    notification_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 1,
    last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    next_retry_at TIMESTAMP,
    response_code INTEGER,
    response_body TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP,
    FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_delivery_log_notification ON notification_delivery_log(notification_id);
CREATE INDEX IF NOT EXISTS idx_delivery_log_status ON notification_delivery_log(status);
CREATE INDEX IF NOT EXISTS idx_delivery_log_channel ON notification_delivery_log(channel);

-- ============================================
-- Embedding Jobs
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_jobs (
    id SERIAL PRIMARY KEY,
    job_id TEXT UNIQUE NOT NULL,
    config_id INTEGER,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    phase TEXT,
    total_documents INTEGER NOT NULL,
    processed_documents INTEGER DEFAULT 0,
    failed_documents INTEGER DEFAULT 0,
    progress_percentage REAL DEFAULT 0.0,
    current_batch INTEGER DEFAULT 0,
    total_batches INTEGER NOT NULL,
    batch_size INTEGER NOT NULL DEFAULT 50,
    documents_per_second REAL,
    estimated_completion_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    embedding_started_at TIMESTAMP,
    agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    embedding_model TEXT,
    embedding_dimension INTEGER,
    started_by INTEGER NOT NULL,
    cancelled_by INTEGER,
    error_message TEXT,
    error_details TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    config_metadata TEXT,
    FOREIGN KEY (config_id) REFERENCES system_prompts(id) ON DELETE SET NULL,
    FOREIGN KEY (started_by) REFERENCES users(id),
    FOREIGN KEY (cancelled_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_jobs_status ON embedding_jobs(status);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_job_id ON embedding_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_started_by ON embedding_jobs(started_by);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_created ON embedding_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_config ON embedding_jobs(config_id);

-- ============================================
-- Embedding Job Batches
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_job_batches (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    batch_number INTEGER NOT NULL,
    document_ids TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    processing_time_ms INTEGER,
    attempt_count INTEGER DEFAULT 0,
    last_error TEXT,
    FOREIGN KEY (job_id) REFERENCES embedding_jobs(id) ON DELETE CASCADE,
    UNIQUE(job_id, batch_number)
);

CREATE INDEX IF NOT EXISTS idx_job_batches_job ON embedding_job_batches(job_id);
CREATE INDEX IF NOT EXISTS idx_job_batches_status ON embedding_job_batches(status);

-- ============================================
-- Embedding Job Events
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_job_events (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES embedding_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_events_job ON embedding_job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_timestamp ON embedding_job_events(timestamp DESC);

-- ============================================
-- System Settings
-- ============================================
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    value_type TEXT DEFAULT 'string',
    description TEXT,
    is_sensitive INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    UNIQUE(category, key)
);

CREATE INDEX IF NOT EXISTS idx_settings_category ON system_settings(category);

-- ============================================
-- Settings History
-- ============================================
CREATE TABLE IF NOT EXISTS settings_history (
    id SERIAL PRIMARY KEY,
    setting_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    previous_value TEXT,
    new_value TEXT NOT NULL,
    changed_by TEXT,
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(setting_id) REFERENCES system_settings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_settings_history_setting_id ON settings_history(setting_id);
CREATE INDEX IF NOT EXISTS idx_settings_history_changed_at ON settings_history(changed_at);

-- ============================================
-- Usage Metrics
-- ============================================
CREATE TABLE IF NOT EXISTS usage_metrics (
    id SERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL,
    session_id TEXT,
    user_id TEXT,
    operation_type TEXT NOT NULL,
    model_name TEXT,
    provider TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    estimated_cost_usd REAL,
    duration_ms INTEGER,
    batch_size INTEGER,
    results_count INTEGER,
    query_text TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usage_metrics_operation_type ON usage_metrics(operation_type);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_created_at ON usage_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_trace_id ON usage_metrics(trace_id);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_user_id ON usage_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_model ON usage_metrics(model_name);

-- ============================================
-- Model Registry: Embedding Models
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_models (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    max_tokens INTEGER DEFAULT 512,
    is_custom INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);

-- ============================================
-- Model Registry: LLM Models
-- ============================================
CREATE TABLE IF NOT EXISTS llm_models (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    context_length INTEGER NOT NULL,
    max_output_tokens INTEGER DEFAULT 4096,
    parameters TEXT DEFAULT '{}',
    is_custom INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);

-- ============================================
-- Embedding-LLM Compatibility
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_llm_compatibility (
    id SERIAL PRIMARY KEY,
    embedding_model_id INTEGER NOT NULL,
    llm_model_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(embedding_model_id) REFERENCES embedding_models(id) ON DELETE CASCADE,
    FOREIGN KEY(llm_model_id) REFERENCES llm_models(id) ON DELETE CASCADE,
    UNIQUE(embedding_model_id, llm_model_id)
);

-- ============================================
-- Vector DB Schedules
-- ============================================
CREATE TABLE IF NOT EXISTS vector_db_schedules (
    id SERIAL PRIMARY KEY,
    vector_db_name TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 0,
    schedule_type TEXT DEFAULT 'daily',
    schedule_hour INTEGER DEFAULT 2,
    schedule_minute INTEGER DEFAULT 0,
    schedule_day_of_week INTEGER,
    schedule_cron TEXT,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status TEXT,
    last_run_job_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_vector_db_schedules_enabled ON vector_db_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_vector_db_schedules_next_run ON vector_db_schedules(next_run_at);


-- ============================================
-- Uploaded File Tables (for SQL querying on uploaded CSVs/Excel)
-- ============================================
CREATE TABLE IF NOT EXISTS uploaded_file_tables (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    table_name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    columns TEXT NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, table_name)
);

CREATE TABLE IF NOT EXISTS uploaded_file_data (
    id SERIAL PRIMARY KEY,
    file_table_id INTEGER NOT NULL,
    row_number INTEGER NOT NULL,
    row_data TEXT NOT NULL,
    FOREIGN KEY (file_table_id) REFERENCES uploaded_file_tables(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uploaded_file_data_table_id ON uploaded_file_data(file_table_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_file_tables_user ON uploaded_file_tables(user_id);

-- ============================================
-- Schema Drift Detection
-- ============================================
CREATE TABLE IF NOT EXISTS schema_drift_logs (
    id SERIAL PRIMARY KEY,
    vector_db_name TEXT NOT NULL,
    drift_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    entity_name TEXT NOT NULL,
    details TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_schema_drift_vector_db ON schema_drift_logs(vector_db_name);
CREATE INDEX IF NOT EXISTS idx_schema_drift_severity ON schema_drift_logs(severity);
CREATE INDEX IF NOT EXISTS idx_schema_drift_detected ON schema_drift_logs(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_schema_drift_unresolved ON schema_drift_logs(vector_db_name, resolved_at) WHERE resolved_at IS NULL;
