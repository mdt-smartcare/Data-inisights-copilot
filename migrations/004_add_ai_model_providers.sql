-- Migration: Add AI Model Providers table
-- Date: 2026-04-04
-- Description: Creates table for storing AI model provider configurations (LLM, embedding, reranker)
--              Supports both cloud (API-based) and local models with env var or stored API keys

-- Create ai_model_providers table
CREATE TABLE IF NOT EXISTS ai_model_providers (
    id SERIAL PRIMARY KEY,
    
    -- Provider identification
    name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(50) NOT NULL,
    model_type VARCHAR(50) NOT NULL,
    
    -- Model details
    model_name VARCHAR(200) NOT NULL,
    display_name VARCHAR(200),
    
    -- API Key Configuration
    -- use_env_api_key=true: Get key from os.environ[env_var_name]
    -- use_env_api_key=false: Use stored api_key
    use_env_api_key BOOLEAN NOT NULL DEFAULT false,
    env_var_name VARCHAR(100),
    api_key TEXT,
    
    -- Additional Configuration
    api_base_url TEXT,
    organization_id VARCHAR(200),
    
    -- Additional settings (JSON)
    settings JSONB,
    
    -- Status flags
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_default BOOLEAN NOT NULL DEFAULT false,
    is_system BOOLEAN NOT NULL DEFAULT false,   -- System-seeded (can't delete)
    is_local BOOLEAN NOT NULL DEFAULT false,    -- Runs locally (no API key needed)
    
    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    
    -- Constraints
    CONSTRAINT ck_ai_model_providers_provider_type CHECK (provider_type IN ('openai', 'anthropic', 'azure', 'ollama', 'huggingface', 'cohere', 'local')),
    CONSTRAINT ck_ai_model_providers_model_type CHECK (model_type IN ('llm', 'embedding', 'reranker')),
    CONSTRAINT uq_ai_model_providers_name UNIQUE (name)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_ai_model_providers_model_type ON ai_model_providers(model_type);
CREATE INDEX IF NOT EXISTS idx_ai_model_providers_provider_type ON ai_model_providers(provider_type);
CREATE INDEX IF NOT EXISTS idx_ai_model_providers_is_active ON ai_model_providers(is_active);
CREATE INDEX IF NOT EXISTS idx_ai_model_providers_is_default ON ai_model_providers(is_default);
CREATE INDEX IF NOT EXISTS idx_ai_model_providers_is_system ON ai_model_providers(is_system);

-- Partial unique index: Only one default per model_type
-- This ensures business rule: each model_type can have at most ONE default provider
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_model_providers_one_default_per_type 
    ON ai_model_providers (model_type) 
    WHERE is_default = true;

-- Add comment
COMMENT ON TABLE ai_model_providers IS 'Stores AI model provider configurations for LLM, embedding, and reranker models. Supports cloud (API) and local models.';

-- ============================================
-- SEED DEFAULT MODELS
-- ============================================
-- These are the default models bootstrapped on deployment.
-- Local models work out of the box. Cloud models use env vars.

-- Default LLM: OpenAI GPT-4o (uses OPENAI_API_KEY from environment)
INSERT INTO ai_model_providers (
    name, provider_type, model_type, model_name, display_name,
    use_env_api_key, env_var_name,
    is_active, is_default, is_system, is_local, created_by
) VALUES (
    'system-llm-openai', 'openai', 'llm', 'gpt-4o', 'GPT-4o (OpenAI) - System Default',
    true, 'OPENAI_API_KEY',
    true, true, true, false, 'system'
) ON CONFLICT (name) DO NOTHING;

-- Default Embedding: BGE-M3 (local, no API key needed)
INSERT INTO ai_model_providers (
    name, provider_type, model_type, model_name, display_name,
    use_env_api_key, env_var_name,
    is_active, is_default, is_system, is_local, created_by
) VALUES (
    'system-embedding-bge', 'huggingface', 'embedding', 'BAAI/bge-m3', 'BGE-M3 (Local) - System Default',
    false, null,
    true, true, true, true, 'system'
) ON CONFLICT (name) DO NOTHING;

-- Default Reranker: BGE-reranker-base (local, no API key needed)
INSERT INTO ai_model_providers (
    name, provider_type, model_type, model_name, display_name,
    use_env_api_key, env_var_name,
    is_active, is_default, is_system, is_local, created_by
) VALUES (
    'system-reranker-bge', 'huggingface', 'reranker', 'BAAI/bge-reranker-base', 'BGE Reranker Base (Local) - System Default',
    false, null,
    true, true, true, true, 'system'
) ON CONFLICT (name) DO NOTHING;

-- ============================================
-- ADDITIONAL LOCAL MODELS (pre-configured but not default)
-- ============================================

-- Ollama LLMs (for users who prefer local)
INSERT INTO ai_model_providers (
    name, provider_type, model_type, model_name, display_name,
    api_base_url,
    is_active, is_default, is_system, is_local, created_by
) VALUES (
    'system-llm-ollama-llama', 'ollama', 'llm', 'llama3.2', 'Llama 3.2 (Ollama) - Local',
    'http://localhost:11434',
    true, false, true, true, 'system'
) ON CONFLICT (name) DO NOTHING;

INSERT INTO ai_model_providers (
    name, provider_type, model_type, model_name, display_name,
    api_base_url,
    is_active, is_default, is_system, is_local, created_by
) VALUES (
    'system-llm-ollama-mistral', 'ollama', 'llm', 'mistral', 'Mistral (Ollama) - Local',
    'http://localhost:11434',
    true, false, true, true, 'system'
) ON CONFLICT (name) DO NOTHING;

-- Ollama Embedding
INSERT INTO ai_model_providers (
    name, provider_type, model_type, model_name, display_name,
    api_base_url,
    is_active, is_default, is_system, is_local, created_by
) VALUES (
    'system-embedding-ollama', 'ollama', 'embedding', 'nomic-embed-text', 'Nomic Embed Text (Ollama) - Local',
    'http://localhost:11434',
    true, false, true, true, 'system'
) ON CONFLICT (name) DO NOTHING;
