-- Migration: 001_rag_versioning.sql
-- Description: Create tables for RAG configuration versioning and embedding storage
-- Author: Schema-Driven RAG Architecture
-- Date: 2026-01-28

-- ============================================
-- RAG Configurations Table
-- Stores complete configuration snapshots for versioning
-- ============================================
CREATE TABLE IF NOT EXISTS rag_configurations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,              -- Semantic version (e.g., "1.0.0")
    version_number INTEGER NOT NULL,           -- Auto-incrementing version number
    
    -- Configuration Data
    schema_snapshot TEXT NOT NULL,             -- JSON: Complete database schema at time of config
    data_dictionary TEXT,                      -- Full data dictionary content
    prompt_template TEXT NOT NULL,             -- Generated system prompt
    
    -- Metadata
    status TEXT NOT NULL DEFAULT 'draft',      -- draft, published, archived, rollback
    created_by INTEGER NOT NULL,               -- User ID who created this config
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    published_by INTEGER,
    
    -- Lineage tracking
    parent_version_id INTEGER,                 -- Previous version this was based on
    change_summary TEXT,                       -- Description of changes from parent
    
    -- Hash for reproducibility
    config_hash TEXT NOT NULL,                 -- SHA-256 hash of schema + dictionary + prompt
    
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (published_by) REFERENCES users(id),
    FOREIGN KEY (parent_version_id) REFERENCES rag_configurations(id)
);

CREATE INDEX IF NOT EXISTS idx_rag_config_status ON rag_configurations(status);
CREATE INDEX IF NOT EXISTS idx_rag_config_version ON rag_configurations(version_number DESC);
CREATE INDEX IF NOT EXISTS idx_rag_config_created ON rag_configurations(created_at DESC);

-- ============================================
-- Embedding Versions Table
-- Links embedding sets to specific configuration versions
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL,
    
    -- Version Identification
    version_hash TEXT NOT NULL UNIQUE,         -- Hash of config + embedding model + timestamp
    embedding_model TEXT NOT NULL,             -- Model name (e.g., "BAAI/bge-m3")
    embedding_dimension INTEGER NOT NULL,      -- Vector dimension (e.g., 1024)
    
    -- Document Statistics
    total_documents INTEGER NOT NULL DEFAULT 0,
    table_documents INTEGER NOT NULL DEFAULT 0,
    column_documents INTEGER NOT NULL DEFAULT 0,
    relationship_documents INTEGER NOT NULL DEFAULT 0,
    
    -- Status and Timing
    status TEXT NOT NULL DEFAULT 'pending',    -- pending, generating, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    generation_time_seconds REAL,
    
    -- Validation Results
    validation_passed INTEGER DEFAULT 0,       -- Boolean: 1 = passed, 0 = failed/not run
    validation_details TEXT,                   -- JSON: Detailed validation results
    
    -- Error Tracking
    error_message TEXT,
    error_details TEXT,                        -- JSON: Full error context
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER NOT NULL,
    
    FOREIGN KEY (config_id) REFERENCES rag_configurations(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_versions_config ON embedding_versions(config_id);
CREATE INDEX IF NOT EXISTS idx_embedding_versions_status ON embedding_versions(status);

-- ============================================
-- Embedding Documents Table
-- Stores individual embedded documents with vectors
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    
    -- Document Identification
    document_id TEXT NOT NULL,                 -- Unique within version (e.g., "table:patients")
    document_type TEXT NOT NULL,               -- table, column, relationship
    
    -- Content
    source_table TEXT,                         -- Source table name
    source_column TEXT,                        -- Source column name (for column docs)
    content TEXT NOT NULL,                     -- Full text content that was embedded
    
    -- Vector Storage (stored as JSON array for SQLite compatibility)
    embedding TEXT NOT NULL,                   -- JSON array of floats [0.1, 0.2, ...]
    
    -- Metadata
    metadata TEXT,                             -- JSON: Additional metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (version_id) REFERENCES embedding_versions(id) ON DELETE CASCADE,
    UNIQUE(version_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_docs_version ON embedding_documents(version_id);
CREATE INDEX IF NOT EXISTS idx_embedding_docs_type ON embedding_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_embedding_docs_table ON embedding_documents(source_table);

-- ============================================
-- Enhanced RAG Audit Log Table
-- Tracks all RAG-related privileged actions
-- ============================================
CREATE TABLE IF NOT EXISTS rag_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER,
    
    -- Action Details
    action TEXT NOT NULL,                      -- wizard_accessed, embedding_started, config_published, etc.
    
    -- Actor Information
    performed_by INTEGER NOT NULL,
    performed_by_email TEXT NOT NULL,
    performed_by_role TEXT NOT NULL,
    
    -- Request Context
    ip_address TEXT,
    user_agent TEXT,
    
    -- Timing
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Change Details
    changes TEXT,                              -- JSON: What changed
    reason TEXT,                               -- Optional justification
    
    -- Outcome
    success INTEGER DEFAULT 1,                 -- Boolean: 1 = success, 0 = failure
    error_message TEXT,
    
    FOREIGN KEY (config_id) REFERENCES rag_configurations(id) ON DELETE SET NULL,
    FOREIGN KEY (performed_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_rag_audit_user ON rag_audit_log(performed_by);
CREATE INDEX IF NOT EXISTS idx_rag_audit_action ON rag_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_rag_audit_timestamp ON rag_audit_log(performed_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_audit_config ON rag_audit_log(config_id);
