-- ============================================================================
-- AI Models - Simplified Single-Table Design
-- ============================================================================
-- Replaces the complex provider/model split with a simple flat structure
-- Inspired by LiteLLM's "provider/model" format
-- 
-- Key simplifications:
-- 1. Single table - no provider setup step
-- 2. API key per model (different keys for different accounts)
-- 3. Clear cloud vs local distinction
-- 4. Direct HuggingFace integration for local downloads
-- ============================================================================

-- Drop old complex tables
DROP TABLE IF EXISTS ai_model_downloads CASCADE;
DROP TABLE IF EXISTS ai_model_defaults CASCADE;
DROP TABLE IF EXISTS ai_models CASCADE;
DROP TABLE IF EXISTS ai_providers CASCADE;
DROP VIEW IF EXISTS v_available_models CASCADE;

-- ============================================================================
-- Main Table: ai_models - Everything in one place
-- ============================================================================
CREATE TABLE ai_models (
    id SERIAL PRIMARY KEY,
    
    -- Model identification
    model_id VARCHAR(500) NOT NULL UNIQUE,       -- Unique ID: "openai/gpt-4o", "huggingface/BAAI/bge-m3"
    display_name VARCHAR(200) NOT NULL,          -- Human-readable: "GPT-4o", "BGE-M3 Embedding"
    model_type VARCHAR(50) NOT NULL,             -- 'llm', 'embedding', 'reranker'
    
    -- Provider info (denormalized for simplicity)
    provider_name VARCHAR(100) NOT NULL,         -- 'openai', 'anthropic', 'huggingface', 'ollama', etc.
    deployment_type VARCHAR(50) NOT NULL,        -- 'cloud' or 'local'
    
    -- Cloud configuration (when deployment_type = 'cloud')
    api_base_url TEXT,                           -- e.g., 'https://api.openai.com/v1'
    api_key_encrypted TEXT,                      -- Fernet encrypted API key
    api_key_env_var VARCHAR(100),                -- OR use env var: 'OPENAI_API_KEY'
    
    -- Local configuration (when deployment_type = 'local')
    local_path TEXT,                             -- e.g., './data/models/BAAI/bge-m3'
    download_status VARCHAR(50) DEFAULT 'not_downloaded',  -- 'not_downloaded', 'downloading', 'ready', 'error'
    download_progress INTEGER DEFAULT 0,         -- 0-100 percentage
    download_error TEXT,                         -- Error message if failed
    
    -- Model specifications
    context_length INTEGER,                      -- Max tokens for LLMs
    max_input_tokens INTEGER,                    -- Max input for embeddings/rerankers
    dimensions INTEGER,                          -- Embedding dimensions
    
    -- RAG compatibility hints
    recommended_chunk_size INTEGER,              -- Optimal chunk size
    compatibility_notes TEXT,                    -- e.g., "Pairs well with bge-reranker"
    
    -- HuggingFace metadata (for local models)
    hf_model_id VARCHAR(500),                    -- e.g., 'BAAI/bge-m3'
    hf_revision VARCHAR(100),                    -- Git commit/tag
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,            -- One default per model_type
    
    -- Metadata
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    
    -- Constraints
    CONSTRAINT ck_ai_models_model_type CHECK (model_type IN ('llm', 'embedding', 'reranker')),
    CONSTRAINT ck_ai_models_deployment_type CHECK (deployment_type IN ('cloud', 'local')),
    CONSTRAINT ck_ai_models_download_status CHECK (
        download_status IN ('not_downloaded', 'pending', 'downloading', 'ready', 'error')
    )
);

-- Indexes for common queries
CREATE INDEX idx_ai_models_model_type ON ai_models(model_type);
CREATE INDEX idx_ai_models_provider ON ai_models(provider_name);
CREATE INDEX idx_ai_models_deployment ON ai_models(deployment_type);
CREATE INDEX idx_ai_models_active ON ai_models(is_active);
CREATE INDEX idx_ai_models_default ON ai_models(model_type, is_default) WHERE is_default = true;

-- ============================================================================
-- View: Available models for agent configuration
-- ============================================================================
CREATE VIEW v_available_models AS
SELECT 
    id,
    model_id,
    display_name,
    model_type,
    provider_name,
    deployment_type,
    -- Ready status: cloud models are always ready, local need download_status = 'ready'
    CASE 
        WHEN deployment_type = 'cloud' THEN true
        WHEN deployment_type = 'local' AND download_status = 'ready' THEN true
        ELSE false
    END AS is_ready,
    is_default,
    context_length,
    max_input_tokens,
    dimensions,
    recommended_chunk_size,
    compatibility_notes
FROM ai_models
WHERE is_active = true;

-- ============================================================================
-- Function: Ensure only one default per model_type
-- ============================================================================
CREATE OR REPLACE FUNCTION ensure_single_default_model()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_default = true THEN
        UPDATE ai_models 
        SET is_default = false 
        WHERE model_type = NEW.model_type 
          AND id != NEW.id 
          AND is_default = true;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_single_default_model
BEFORE INSERT OR UPDATE ON ai_models
FOR EACH ROW
EXECUTE FUNCTION ensure_single_default_model();

-- ============================================================================
-- Function: Auto-update updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_ai_models_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ai_models_updated
BEFORE UPDATE ON ai_models
FOR EACH ROW
EXECUTE FUNCTION update_ai_models_timestamp();

-- ============================================================================
-- Common provider presets (optional - admin can skip these)
-- ============================================================================
COMMENT ON TABLE ai_models IS 'Single table for all AI models (cloud and local). No provider setup needed.';
COMMENT ON COLUMN ai_models.model_id IS 'Unique identifier in format: provider/model-name';
COMMENT ON COLUMN ai_models.deployment_type IS 'cloud = API-based, local = downloaded model';
COMMENT ON COLUMN ai_models.api_key_encrypted IS 'Fernet-encrypted API key for cloud models';
COMMENT ON COLUMN ai_models.download_status IS 'Download state for local models';

-- ============================================
-- Seed Data - Common models to get started
-- ============================================
-- These are the models actually used in the system.
-- Users can add more via the UI.

-- LLM: OpenAI GPT-4o (default)
INSERT INTO ai_models (
    model_id, display_name, model_type, provider_name, deployment_type,
    api_base_url, api_key_env_var, context_length,
    recommended_chunk_size, compatibility_notes, description,
    is_default, download_status
) VALUES (
    'openai/gpt-4o', 'GPT-4o', 'llm', 'openai', 'cloud',
    'https://api.openai.com/v1', 'OPENAI_API_KEY', 128000,
    1500, 'Works well with any embedding model. Supports function calling.',
    'OpenAI''s flagship model. Fast, smart, supports vision. Good for RAG.',
    true, 'ready'
);

-- LLM: OpenAI GPT-4o-mini
INSERT INTO ai_models (
    model_id, display_name, model_type, provider_name, deployment_type,
    api_base_url, api_key_env_var, context_length,
    recommended_chunk_size, compatibility_notes, description,
    is_default, download_status
) VALUES (
    'openai/gpt-4o-mini', 'GPT-4o Mini', 'llm', 'openai', 'cloud',
    'https://api.openai.com/v1', 'OPENAI_API_KEY', 128000,
    1500, 'Cost-effective option. Same capabilities as GPT-4o but faster.',
    'Smaller, faster, cheaper GPT-4o. Good for high-volume use cases.',
    false, 'ready'
);

-- Embedding: BGE-M3 (default, local)
INSERT INTO ai_models (
    model_id, display_name, model_type, provider_name, deployment_type,
    hf_model_id, local_path, dimensions, max_input_tokens,
    recommended_chunk_size, compatibility_notes, description,
    is_default, download_status
) VALUES (
    'huggingface/BAAI/bge-m3', 'BGE-M3 (Local)', 'embedding', 'huggingface', 'local',
    'BAAI/bge-m3', './data/models/BAAI/bge-m3', 1024, 8192,
    512, 'Best paired with bge-reranker-v2-m3. Excellent for medical text.',
    'Best multilingual embedding model. Supports 100+ languages. Runs locally.',
    true, 'not_downloaded'
);

-- Embedding: OpenAI text-embedding-3-small (cloud)
INSERT INTO ai_models (
    model_id, display_name, model_type, provider_name, deployment_type,
    api_base_url, api_key_env_var, dimensions, max_input_tokens,
    recommended_chunk_size, compatibility_notes, description,
    is_default, download_status
) VALUES (
    'openai/text-embedding-3-small', 'OpenAI Embedding 3 Small', 'embedding', 'openai', 'cloud',
    'https://api.openai.com/v1', 'OPENAI_API_KEY', 1536, 8191,
    512, 'Use with OpenAI LLMs for best results. Fast API response.',
    'OpenAI''s efficient embedding model. Good balance of cost and quality.',
    false, 'ready'
);

-- Reranker: BGE Reranker v2 M3 (default, local)
INSERT INTO ai_models (
    model_id, display_name, model_type, provider_name, deployment_type,
    hf_model_id, local_path, max_input_tokens,
    compatibility_notes, description,
    is_default, download_status
) VALUES (
    'huggingface/BAAI/bge-reranker-v2-m3', 'BGE Reranker v2 M3 (Local)', 'reranker', 'huggingface', 'local',
    'BAAI/bge-reranker-v2-m3', './data/models/BAAI/bge-reranker-v2-m3', 8192,
    'Use with bge-m3 embeddings for best results. Improves retrieval accuracy.',
    'Best multilingual reranker. Pairs perfectly with bge-m3 embeddings.',
    true, 'not_downloaded'
);
