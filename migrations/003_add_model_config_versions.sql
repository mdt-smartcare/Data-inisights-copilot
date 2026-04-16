-- Migration: 003_add_model_config_versions.sql
-- Description: Add model_config_versions table for versioned model configuration snapshots
-- Author: System
-- Date: 2026-03-27
-- Note: This table was in the SQLite migration 011 but was accidentally omitted from the PostgreSQL migration.
--       It has been added to 001_initial_schema.sql for new databases.
--       This migration adds it for existing databases that were created before the fix.

-- ============================================
-- Model Config Versions
-- ============================================
CREATE TABLE IF NOT EXISTS model_config_versions (
    id SERIAL PRIMARY KEY,
    config_type TEXT NOT NULL,              -- 'embedding', 'llm', or 'full'
    config_snapshot TEXT NOT NULL,          -- JSON blob of the entire config state
    version INTEGER NOT NULL,               -- Incrementing version number per config_type
    updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add indexes
CREATE INDEX IF NOT EXISTS idx_config_versions_type ON model_config_versions(config_type);
CREATE INDEX IF NOT EXISTS idx_config_versions_version ON model_config_versions(config_type, version);

-- Add comment
COMMENT ON TABLE model_config_versions IS 'Versioned snapshots of model configuration for rollback capability';
