-- Migration: Add model registry, compatibility, and versioned config tables
-- Created: 2026-02-24

-- ============================================================================
-- embedding_models: Registry of available embedding models (built-in + custom)
-- ============================================================================
CREATE TABLE IF NOT EXISTS embedding_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,                -- e.g., 'bge-m3', 'openai', 'sentence-transformers', 'cohere'
    model_name TEXT NOT NULL UNIQUE,       -- e.g., 'BAAI/bge-m3', 'text-embedding-3-small'
    display_name TEXT NOT NULL,            -- Human-readable label for UI
    dimensions INTEGER NOT NULL,           -- Embedding vector dimension
    max_tokens INTEGER DEFAULT 512,        -- Max input token length
    is_custom INTEGER DEFAULT 0,           -- 1 if user-registered, 0 if built-in
    is_active INTEGER DEFAULT 0,           -- 1 if currently active
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);

-- ============================================================================
-- llm_models: Registry of available LLM models (built-in + custom)
-- ============================================================================
CREATE TABLE IF NOT EXISTS llm_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,                -- e.g., 'openai', 'azure', 'anthropic', 'ollama'
    model_name TEXT NOT NULL UNIQUE,       -- e.g., 'gpt-4o', 'claude-3.5-sonnet'
    display_name TEXT NOT NULL,            -- Human-readable label for UI
    context_length INTEGER NOT NULL,       -- Max context window (tokens)
    max_output_tokens INTEGER DEFAULT 4096,-- Max output tokens
    parameters TEXT DEFAULT '{}',          -- JSON blob for extra params (temperature defaults, etc.)
    is_custom INTEGER DEFAULT 0,           -- 1 if user-registered, 0 if built-in
    is_active INTEGER DEFAULT 0,           -- 1 if currently active
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT
);

-- ============================================================================
-- embedding_llm_compatibility: Which LLMs are allowed with which embeddings
-- ============================================================================
CREATE TABLE IF NOT EXISTS embedding_llm_compatibility (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    embedding_model_id INTEGER NOT NULL,
    llm_model_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(embedding_model_id) REFERENCES embedding_models(id) ON DELETE CASCADE,
    FOREIGN KEY(llm_model_id) REFERENCES llm_models(id) ON DELETE CASCADE,
    UNIQUE(embedding_model_id, llm_model_id)
);

-- ============================================================================
-- model_config_versions: Versioned snapshots of full model configuration
-- ============================================================================
CREATE TABLE IF NOT EXISTS model_config_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_type TEXT NOT NULL,             -- 'embedding', 'llm', or 'full'
    config_snapshot TEXT NOT NULL,          -- JSON blob of the entire config state
    version INTEGER NOT NULL,              -- Incrementing version number per config_type
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_embedding_models_provider ON embedding_models(provider);
CREATE INDEX IF NOT EXISTS idx_embedding_models_active ON embedding_models(is_active);
CREATE INDEX IF NOT EXISTS idx_llm_models_provider ON llm_models(provider);
CREATE INDEX IF NOT EXISTS idx_llm_models_active ON llm_models(is_active);
CREATE INDEX IF NOT EXISTS idx_compat_embedding ON embedding_llm_compatibility(embedding_model_id);
CREATE INDEX IF NOT EXISTS idx_compat_llm ON embedding_llm_compatibility(llm_model_id);
CREATE INDEX IF NOT EXISTS idx_config_versions_type ON model_config_versions(config_type);

-- ============================================================================
-- Seed: Default embedding models
-- ============================================================================
INSERT OR IGNORE INTO embedding_models (provider, model_name, display_name, dimensions, max_tokens, is_custom, is_active) VALUES
    ('bge-m3', 'BAAI/bge-m3', 'BGE-M3 (Local)', 1024, 8192, 0, 1),
    ('openai', 'text-embedding-3-small', 'OpenAI Embedding 3 Small', 1536, 8191, 0, 0),
    ('openai', 'text-embedding-3-large', 'OpenAI Embedding 3 Large', 3072, 8191, 0, 0),
    ('sentence-transformers', 'all-MiniLM-L6-v2', 'MiniLM-L6-v2 (Local)', 384, 512, 0, 0);

-- ============================================================================
-- Seed: Default LLM models
-- ============================================================================
INSERT OR IGNORE INTO llm_models (provider, model_name, display_name, context_length, max_output_tokens, parameters, is_custom, is_active) VALUES
    ('openai', 'gpt-4o', 'GPT-4o', 128000, 16384, '{"temperature": 0.0}', 0, 1),
    ('openai', 'gpt-4o-mini', 'GPT-4o Mini', 128000, 16384, '{"temperature": 0.0}', 0, 0),
    ('anthropic', 'claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet', 200000, 8192, '{"temperature": 0.0}', 0, 0),
    ('ollama', 'llama3.1:latest', 'Llama 3.1 (Local)', 131072, 4096, '{"temperature": 0.0}', 0, 0);

-- ============================================================================
-- Seed: Default compatibility mappings (permissive: all embeddings × all LLMs)
-- ============================================================================
INSERT OR IGNORE INTO embedding_llm_compatibility (embedding_model_id, llm_model_id)
SELECT e.id, l.id
FROM embedding_models e
CROSS JOIN llm_models l;
