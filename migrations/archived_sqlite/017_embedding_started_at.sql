-- Migration: 017_embedding_started_at.sql
-- Description: Add embedding_started_at column for accurate speed/ETA calculation
-- Author: System
-- Date: 2026-03-09

-- Add embedding_started_at to track when the actual embedding phase starts
-- This allows accurate speed calculation by excluding data loading and chunking time
ALTER TABLE embedding_jobs ADD COLUMN embedding_started_at TIMESTAMP;

-- Create index for potential queries on this field
CREATE INDEX IF NOT EXISTS idx_embedding_jobs_embedding_started ON embedding_jobs(embedding_started_at);
