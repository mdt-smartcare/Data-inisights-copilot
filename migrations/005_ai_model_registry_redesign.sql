-- ============================================================================
-- AI Model Registry - Flexible Design (No Hardcoding)
-- ============================================================================
-- This design allows:
-- 1. Adding any model provider without code changes (OpenAI, Anthropic, etc.)
-- 2. Adding any model from any source (HuggingFace, Ollama, Cloud APIs)
-- 3. Local models downloaded to configurable paths
-- 4. Cloud models with API keys (ENCRYPTED at rest)
-- 5. Per-agent model selection
-- 6. Model version tracking
-- 7. Background downloads with progress polling
-- ============================================================================

-- Drop old table if exists (we're redesigning)
DROP TABLE IF EXISTS ai_model_providers CASCADE;
DROP TABLE IF EXISTS ai_model_downloads CASCADE;
DROP TABLE IF EXISTS ai_model_defaults CASCADE;
DROP TABLE IF EXISTS ai_models CASCADE;
DROP TABLE IF EXISTS ai_providers CASCADE;
DROP VIEW IF EXISTS v_available_models CASCADE;

-- ============================================================================
-- Table 1: ai_providers - Cloud/Local Providers (manually added)
-- ============================================================================
-- Examples: openai, anthropic, huggingface, ollama, azure, cohere
-- NOT hardcoded - admin adds them via UI

CREATE TABLE ai_providers (
    id SERIAL PRIMARY KEY,
    
    -- Provider identification
    name VARCHAR(100) NOT NULL UNIQUE,           -- e.g., 'openai', 'anthropic', 'huggingface-local'
    display_name VARCHAR(200) NOT NULL,          -- e.g., 'OpenAI', 'Anthropic Claude', 'HuggingFace (Local)'
    provider_type VARCHAR(50) NOT NULL,          -- 'cloud' or 'local'
    
    -- For cloud providers
    api_base_url TEXT,                           -- e.g., 'https://api.openai.com/v1'
    api_key_env_var VARCHAR(100),                -- e.g., 'OPENAI_API_KEY' (reads from env)
    api_key_encrypted TEXT,                      -- Encrypted API key (Fernet encryption)
    auth_type VARCHAR(50) DEFAULT 'bearer',      -- 'bearer', 'header', 'query_param'
    auth_header_name VARCHAR(100),               -- Custom header name if auth_type='header'
    
    -- For local providers
    download_base_path TEXT,                     -- e.g., './data/models/huggingface'
    requires_gpu BOOLEAN DEFAULT false,
    
    -- Model capabilities this provider supports
    supports_llm BOOLEAN DEFAULT false,
    supports_embedding BOOLEAN DEFAULT false,
    supports_reranker BOOLEAN DEFAULT false,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    -- Metadata
    description TEXT,
    documentation_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

CREATE INDEX idx_ai_providers_type ON ai_providers(provider_type);
CREATE INDEX idx_ai_providers_active ON ai_providers(is_active);

COMMENT ON TABLE ai_providers IS 'AI providers (cloud or local) that can serve models. Manually configured, not hardcoded. API keys are encrypted.';

-- ============================================================================
-- Table 2: ai_models - Individual Models (manually added)
-- ============================================================================
-- Examples: gpt-4o, BAAI/bge-m3, claude-3-opus
-- NOT hardcoded - admin adds them via UI or HuggingFace search

CREATE TABLE ai_models (
    id SERIAL PRIMARY KEY,
    
    -- Model identification
    provider_id INTEGER NOT NULL REFERENCES ai_providers(id) ON DELETE CASCADE,
    model_identifier VARCHAR(500) NOT NULL,       -- e.g., 'gpt-4o', 'BAAI/bge-m3', 'mistral:7b'
    display_name VARCHAR(200) NOT NULL,
    model_type VARCHAR(50) NOT NULL,              -- 'llm', 'embedding', 'reranker'
    
    -- Version tracking
    version VARCHAR(100),                         -- e.g., '1.0', 'v2.1', 'latest'
    revision VARCHAR(100),                        -- Git commit sha or HuggingFace revision
    parent_model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,  -- Link to previous version
    
    -- Model details (can be fetched from HuggingFace or entered manually)
    dimensions INTEGER,                           -- For embedding models
    context_length INTEGER,                       -- Max context window for LLMs
    max_input_tokens INTEGER,                     -- Max input per document (rerankers/embeddings)
    languages TEXT[],                             -- Supported languages
    
    -- RAG compatibility guidance
    compatibility_notes TEXT,                     -- e.g., 'Pairs well with bge-m3 embeddings'
    recommended_chunk_size INTEGER,               -- Optimal chunk size for this model
    
    -- Local model storage
    is_local BOOLEAN DEFAULT false,               -- Downloaded locally vs API
    local_path TEXT,                              -- e.g., './data/models/huggingface/BAAI/bge-m3'
    download_status VARCHAR(50) DEFAULT 'not_downloaded',  -- 'not_downloaded', 'pending', 'downloading', 'ready', 'error'
    download_size_mb INTEGER,                     -- Approximate size
    
    -- Model settings/parameters
    default_settings JSONB DEFAULT '{}',          -- temperature, max_tokens, etc.
    
    -- HuggingFace metadata (fetched from API)
    hf_model_id VARCHAR(500),                     -- HuggingFace model ID (e.g., 'BAAI/bge-m3')
    hf_pipeline_tag VARCHAR(100),                 -- HuggingFace pipeline (e.g., 'sentence-similarity')
    hf_library_name VARCHAR(100),                 -- Library (e.g., 'sentence-transformers')
    hf_downloads INTEGER,                         -- Download count from HuggingFace
    hf_likes INTEGER,                             -- Likes from HuggingFace
    hf_last_synced_at TIMESTAMP,                  -- Last sync with HuggingFace API
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,            -- Admin verified it works
    
    -- Metadata
    source_url TEXT,                              -- HuggingFace URL, etc.
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    
    UNIQUE(provider_id, model_identifier, version)
);

CREATE INDEX idx_ai_models_type ON ai_models(model_type);
CREATE INDEX idx_ai_models_provider ON ai_models(provider_id);
CREATE INDEX idx_ai_models_active ON ai_models(is_active);
CREATE INDEX idx_ai_models_local ON ai_models(is_local);
CREATE INDEX idx_ai_models_download_status ON ai_models(download_status);
CREATE INDEX idx_ai_models_hf_model_id ON ai_models(hf_model_id);

COMMENT ON TABLE ai_models IS 'Individual AI models available in the system. Manually added via UI or HuggingFace search. Supports versioning.';

-- ============================================================================
-- Table 3: ai_model_defaults - System-wide defaults per model type
-- ============================================================================

CREATE TABLE ai_model_defaults (
    id SERIAL PRIMARY KEY,
    model_type VARCHAR(50) NOT NULL UNIQUE,      -- 'llm', 'embedding', 'reranker'
    default_model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100)
);

INSERT INTO ai_model_defaults (model_type) VALUES ('llm'), ('embedding'), ('reranker');

COMMENT ON TABLE ai_model_defaults IS 'System-wide default model for each type. Used when agent has no specific selection.';

-- ============================================================================
-- Table 4: ai_model_downloads - Track download jobs for local models
-- ============================================================================

CREATE TABLE ai_model_downloads (
    id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES ai_models(id) ON DELETE CASCADE,
    
    -- Download status
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, downloading, completed, failed
    progress_percent INTEGER DEFAULT 0,
    error_message TEXT,
    
    -- Download details
    download_url TEXT,
    total_size_bytes BIGINT,
    downloaded_bytes BIGINT DEFAULT 0,
    
    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    requested_by VARCHAR(100)
);

CREATE INDEX idx_ai_model_downloads_model ON ai_model_downloads(model_id);
CREATE INDEX idx_ai_model_downloads_status ON ai_model_downloads(status);

COMMENT ON TABLE ai_model_downloads IS 'Tracks download progress for local models from HuggingFace Hub or other sources.';

-- ============================================================================
-- View: Available models for selection
-- ============================================================================

CREATE OR REPLACE VIEW v_available_models AS
SELECT 
    m.id,
    m.model_identifier,
    m.display_name,
    m.model_type,
    m.version,
    m.revision,
    m.dimensions,
    m.context_length,
    m.is_local,
    m.local_path,
    m.download_status,
    m.hf_model_id,
    m.hf_downloads,
    m.hf_likes,
    p.id as provider_id,
    p.name as provider_name,
    p.display_name as provider_display_name,
    p.provider_type,
    CASE 
        WHEN m.is_local AND m.download_status = 'ready' THEN true
        WHEN NOT m.is_local AND (p.api_key_env_var IS NOT NULL OR p.api_key_encrypted IS NOT NULL) THEN true
        ELSE false
    END as is_ready
FROM ai_models m
JOIN ai_providers p ON m.provider_id = p.id
WHERE m.is_active = true AND p.is_active = true;

COMMENT ON VIEW v_available_models IS 'Models available for agent selection (active and ready to use).';
