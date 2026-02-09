-- Migration: Add system_settings and settings_history tables for configuration management
-- Created: 2026-02-09

-- ============================================================================
-- system_settings: Stores all configurable system settings by category
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,              -- e.g., 'auth', 'embedding', 'llm', 'rag', 'ui', 'security'
    key TEXT NOT NULL,                   -- setting key within category
    value TEXT NOT NULL,                 -- JSON-encoded value
    value_type TEXT DEFAULT 'string',    -- 'string', 'number', 'boolean', 'json', 'secret'
    description TEXT,                    -- human-readable description
    is_sensitive INTEGER DEFAULT 0,      -- 1 if value should be masked in UI/logs
    version INTEGER DEFAULT 1,           -- version counter for optimistic locking
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,                     -- username who last updated
    UNIQUE(category, key)
);

-- ============================================================================
-- settings_history: Tracks all changes to settings for audit and rollback
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    previous_value TEXT,                 -- JSON-encoded previous value
    new_value TEXT NOT NULL,             -- JSON-encoded new value
    changed_by TEXT,                     -- username who made the change
    change_reason TEXT,                  -- optional reason for the change
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(setting_id) REFERENCES system_settings(id) ON DELETE CASCADE
);

-- ============================================================================
-- Indexes for efficient querying
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_settings_category ON system_settings(category);
CREATE INDEX IF NOT EXISTS idx_settings_history_setting_id ON settings_history(setting_id);
CREATE INDEX IF NOT EXISTS idx_settings_history_changed_at ON settings_history(changed_at);

-- ============================================================================
-- Insert default settings for each category
-- ============================================================================

-- Authentication defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('auth', 'provider', '"local"', 'string', 'Authentication provider: local, oauth2, ldap, saml'),
('auth', 'session_timeout_minutes', '720', 'number', 'Session timeout in minutes'),
('auth', 'require_mfa', 'false', 'boolean', 'Require multi-factor authentication'),
('auth', 'password_min_length', '8', 'number', 'Minimum password length'),
('auth', 'max_login_attempts', '5', 'number', 'Maximum failed login attempts before lockout');

-- Embedding model defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('embedding', 'provider', '"bge-m3"', 'string', 'Embedding provider: bge-m3, openai, sentence-transformers, cohere'),
('embedding', 'model_name', '"BAAI/bge-m3"', 'string', 'Model name/path'),
('embedding', 'model_path', '"./models/bge-m3"', 'string', 'Local model path'),
('embedding', 'batch_size', '128', 'number', 'Batch size for embedding'),
('embedding', 'dimensions', '1024', 'number', 'Embedding dimensions');

-- LLM defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description, is_sensitive) VALUES
('llm', 'provider', '"openai"', 'string', 'LLM provider: openai, azure, anthropic, ollama', 0),
('llm', 'model_name', '"gpt-4o"', 'string', 'Model name', 0),
('llm', 'temperature', '0.0', 'number', 'Temperature for generation', 0),
('llm', 'max_tokens', '4096', 'number', 'Maximum tokens in response', 0),
('llm', 'api_key', '""', 'secret', 'API key (loaded from env if empty)', 1);

-- RAG pipeline defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('rag', 'top_k_initial', '50', 'number', 'Initial documents to fetch'),
('rag', 'top_k_final', '10', 'number', 'Final documents after reranking'),
('rag', 'hybrid_weights', '[0.75, 0.25]', 'json', 'Weights for hybrid search [semantic, keyword]'),
('rag', 'rerank_enabled', 'true', 'boolean', 'Enable reranking'),
('rag', 'reranker_model', '"BAAI/bge-reranker-base"', 'string', 'Reranker model name'),
('rag', 'chunk_size', '800', 'number', 'Parent chunk size'),
('rag', 'chunk_overlap', '150', 'number', 'Chunk overlap');

-- UI/Theming defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('ui', 'app_name', '"Data Insights AI-Copilot"', 'string', 'Application name'),
('ui', 'theme', '"light"', 'string', 'Theme: light, dark, system'),
('ui', 'primary_color', '"#3B82F6"', 'string', 'Primary brand color'),
('ui', 'logo_url', '""', 'string', 'Custom logo URL');

-- Security defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('security', 'rate_limit_enabled', 'true', 'boolean', 'Enable rate limiting'),
('security', 'rate_limit_per_minute', '60', 'number', 'Requests per minute limit'),
('security', 'cors_origins', '"http://localhost:3000,http://localhost:5173"', 'string', 'Allowed CORS origins'),
('security', 'audit_retention_days', '90', 'number', 'Days to retain audit logs');

-- Observability defaults
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('observability', 'log_level', '"INFO"', 'string', 'Log level: DEBUG, INFO, WARNING, ERROR'),
('observability', 'enable_tracing', 'false', 'boolean', 'Enable Langfuse/OpenTelemetry tracing'),
('observability', 'trace_sample_rate', '0.1', 'number', 'Trace sampling rate 0.0-1.0');
