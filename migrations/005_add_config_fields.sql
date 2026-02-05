-- Migration: 005_add_config_fields.sql
-- Description: Add configuration columns for embedding, retriever, and connection pooling
-- Author: UI-Driven Configuration Migration
-- Date: 2026-01-28
-- Note: These columns may already exist - migration runner handles duplicates gracefully

-- This migration has been applied. Columns already exist:
-- rag_configurations.embedding_config
-- rag_configurations.retriever_config  
-- db_connections.pool_config

-- No-op: SELECT 1;
SELECT 1;
