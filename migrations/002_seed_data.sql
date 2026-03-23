-- Migration: 002_seed_data.sql
-- Description: PostgreSQL seed data for default models and settings
-- Author: PostgreSQL Migration
-- Date: 2026-03-19
-- Note: Consolidates all INSERT statements from migrations 011, 018-021

-- ============================================================================
-- Seed: Default embedding models
-- ============================================================================
INSERT INTO embedding_models (provider, model_name, display_name, dimensions, max_tokens, is_custom, is_active) VALUES
    ('bge-m3', 'BAAI/bge-m3', 'BGE-M3 (Local)', 1024, 8192, 0, 0),
    ('openai', 'text-embedding-3-small', 'OpenAI Embedding 3 Small', 1536, 8191, 0, 0),
    ('openai', 'text-embedding-3-large', 'OpenAI Embedding 3 Large', 3072, 8191, 0, 0),
    ('sentence-transformers', 'all-MiniLM-L6-v2', 'MiniLM-L6-v2 (Local)', 384, 512, 0, 0),
    ('sentence-transformers', 'BAAI/bge-base-en-v1.5', 'BGE-Base-EN-v1.5 (Local, Recommended)', 768, 512, 0, 1)
ON CONFLICT (model_name) DO NOTHING;

-- ============================================================================
-- Seed: Default LLM models
-- ============================================================================
INSERT INTO llm_models (provider, model_name, display_name, context_length, max_output_tokens, parameters, is_custom, is_active) VALUES
    ('openai', 'gpt-4o', 'GPT-4o', 128000, 16384, '{"temperature": 0.0}', 0, 1),
    ('openai', 'gpt-4o-mini', 'GPT-4o Mini', 128000, 16384, '{"temperature": 0.0}', 0, 0),
    ('anthropic', 'claude-3-5-sonnet-20241022', 'Claude 3.5 Sonnet', 200000, 8192, '{"temperature": 0.0}', 0, 0),
    ('ollama', 'llama3.1:latest', 'Llama 3.1 (Local)', 131072, 4096, '{"temperature": 0.0}', 0, 0)
ON CONFLICT (model_name) DO NOTHING;

-- ============================================================================
-- Seed: Default compatibility mappings (all embeddings × all LLMs)
-- ============================================================================
INSERT INTO embedding_llm_compatibility (embedding_model_id, llm_model_id)
SELECT e.id, l.id
FROM embedding_models e
CROSS JOIN llm_models l
ON CONFLICT (embedding_model_id, llm_model_id) DO NOTHING;

-- ============================================================================
-- Seed: Default system settings (from migrations 018, 020, 021)
-- ============================================================================
INSERT INTO system_settings (category, key, value, description) VALUES
    ('embedding', 'provider', '"sentence-transformers"', 'Default embedding model provider'),
    ('embedding', 'model_name', '"BAAI/bge-base-en-v1.5"', 'Default embedding model name'),
    ('embedding', 'model_path', '"./models/bge-base-en-v1.5"', 'Path to local embedding model'),
    ('embedding', 'dimensions', '768', 'Embedding vector dimensions'),
    ('embedding', 'chunk_size', '512', 'Default chunk size for text splitting'),
    ('embedding', 'chunk_overlap', '50', 'Default chunk overlap for text splitting'),
    ('rag', 'strategy', '"semantic_search"', 'Default RAG retrieval strategy'),
    ('rag', 'top_k', '5', 'Default number of results to retrieve'),
    ('rag', 'similarity_threshold', '0.7', 'Default similarity threshold for retrieval')
ON CONFLICT (category, key) DO NOTHING;
