-- Migration: 019_per_agent_embedding_model.sql
-- Description: Add per-agent embedding model support
-- Author: Per-Agent Embedding Architecture
-- Date: 2026-03-09
-- 
-- This migration enables each agent to have its own embedding model configuration,
-- allowing different agents to use different embedding models (e.g., bge-m3, OpenAI).
-- Each agent gets its own vector collection to prevent dimension/semantic mismatches.

-- ============================================
-- Add embedding model fields to agents table
-- ============================================
ALTER TABLE agents ADD COLUMN embedding_model TEXT DEFAULT 'bge-m3';
ALTER TABLE agents ADD COLUMN embedding_dimension INTEGER DEFAULT 1024;
ALTER TABLE agents ADD COLUMN embedding_provider TEXT DEFAULT 'sentence-transformers';

-- ============================================
-- Add agent_id to vector_db_registry for per-agent collections
-- ============================================
ALTER TABLE vector_db_registry ADD COLUMN agent_id INTEGER REFERENCES agents(id) ON DELETE CASCADE;

-- Create index for faster lookups by agent
CREATE INDEX IF NOT EXISTS idx_vector_db_registry_agent_id ON vector_db_registry(agent_id);

-- ============================================
-- Add embedding model tracking to embedding_jobs
-- ============================================
ALTER TABLE embedding_jobs ADD COLUMN agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL;
ALTER TABLE embedding_jobs ADD COLUMN embedding_model TEXT;
ALTER TABLE embedding_jobs ADD COLUMN embedding_dimension INTEGER;

CREATE INDEX IF NOT EXISTS idx_embedding_jobs_agent_id ON embedding_jobs(agent_id);

-- ============================================
-- Create agent_embedding_configs table for detailed config
-- ============================================
CREATE TABLE IF NOT EXISTS agent_embedding_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'sentence-transformers',
    model_name TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
    model_path TEXT,
    dimension INTEGER NOT NULL DEFAULT 1024,
    batch_size INTEGER DEFAULT 128,
    collection_name TEXT,  -- Computed: agent_{id}_{model_hash}
    last_embedded_at TIMESTAMP,
    document_count INTEGER DEFAULT 0,
    requires_reindex INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT,
    FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_agent_embedding_configs_agent ON agent_embedding_configs(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_embedding_configs_provider ON agent_embedding_configs(provider);

-- ============================================
-- Create embedding model change history for audit
-- ============================================
CREATE TABLE IF NOT EXISTS agent_embedding_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    previous_provider TEXT,
    previous_model TEXT,
    previous_dimension INTEGER,
    new_provider TEXT NOT NULL,
    new_model TEXT NOT NULL,
    new_dimension INTEGER NOT NULL,
    change_reason TEXT,
    changed_by TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reindex_triggered INTEGER DEFAULT 0,
    reindex_job_id TEXT,
    FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_agent_embedding_history_agent ON agent_embedding_history(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_embedding_history_changed_at ON agent_embedding_history(changed_at DESC);
