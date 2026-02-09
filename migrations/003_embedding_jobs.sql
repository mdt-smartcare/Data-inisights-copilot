-- Migration: 003_embedding_jobs.sql
-- Description: Create embedding jobs table for real-time progress tracking
-- Author: Schema-Driven RAG Architecture
-- Date: 2026-01-28

-- ============================================
-- Embedding Jobs Table
-- Real-time progress tracking for embedding generation
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,               -- External ID (e.g., "emb-job-abc123")
    
    -- References
    config_id INTEGER,                         -- RAG configuration being processed
    embedding_version_id INTEGER,              -- Resulting embedding version
    
    -- Job Status (State Machine)
    -- QUEUED -> PREPARING -> EMBEDDING -> VALIDATING -> STORING -> COMPLETED
    -- Any state can transition to FAILED or CANCELLED
    status TEXT NOT NULL DEFAULT 'QUEUED',
    phase TEXT,                                -- Current phase description
    
    -- Document Processing Progress
    total_documents INTEGER NOT NULL,
    processed_documents INTEGER DEFAULT 0,
    failed_documents INTEGER DEFAULT 0,
    progress_percentage REAL DEFAULT 0.0,
    
    -- Batch Processing Progress
    current_batch INTEGER DEFAULT 0,
    total_batches INTEGER NOT NULL,
    batch_size INTEGER NOT NULL DEFAULT 50,
    
    -- Performance Metrics
    documents_per_second REAL,
    estimated_completion_at TIMESTAMP,
    
    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- User Context
    started_by INTEGER NOT NULL,
    cancelled_by INTEGER,
    
    -- Error Information
    error_message TEXT,
    error_details TEXT,                        -- JSON: Full error context with stack trace
    
    -- Retry Information
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Configuration
    config_metadata TEXT,                      -- JSON: Batch size, concurrency, etc.
    
    FOREIGN KEY (config_id) REFERENCES rag_configurations(id) ON DELETE SET NULL,
    FOREIGN KEY (embedding_version_id) REFERENCES embedding_versions(id) ON DELETE SET NULL,
    FOREIGN KEY (started_by) REFERENCES users(id),
    FOREIGN KEY (cancelled_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_embedding_jobs_status ON embedding_jobs(status);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_job_id ON embedding_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_started_by ON embedding_jobs(started_by);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_created ON embedding_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_config ON embedding_jobs(config_id);

-- ============================================
-- Embedding Job Batches Table
-- Track individual batch progress for detailed monitoring
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_job_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    
    -- Batch Identification
    batch_number INTEGER NOT NULL,
    
    -- Batch Contents
    document_ids TEXT NOT NULL,                -- JSON array of document IDs in this batch
    document_count INTEGER NOT NULL,
    
    -- Status
    status TEXT NOT NULL DEFAULT 'pending',    -- pending, processing, completed, failed
    
    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    processing_time_ms INTEGER,
    
    -- Retry Tracking
    attempt_count INTEGER DEFAULT 0,
    last_error TEXT,
    
    FOREIGN KEY (job_id) REFERENCES embedding_jobs(id) ON DELETE CASCADE,
    UNIQUE(job_id, batch_number)
);

CREATE INDEX IF NOT EXISTS idx_job_batches_job ON embedding_job_batches(job_id);
CREATE INDEX IF NOT EXISTS idx_job_batches_status ON embedding_job_batches(status);

-- ============================================
-- Embedding Job Events Table
-- Timeline of events for detailed job history
-- ============================================
CREATE TABLE IF NOT EXISTS embedding_job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    
    -- Event Details
    event_type TEXT NOT NULL,                  -- status_change, batch_complete, error, retry, etc.
    event_data TEXT,                           -- JSON: Event-specific data
    
    -- Timing
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (job_id) REFERENCES embedding_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_job_events_job ON embedding_job_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_events_timestamp ON embedding_job_events(timestamp DESC);
