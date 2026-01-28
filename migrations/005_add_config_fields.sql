-- Migration: 005_add_config_fields.sql
-- Description: Add configuration columns for embedding, retriever, and connection pooling
-- Author: UI-Driven Configuration Migration
-- Date: 2026-01-28

-- Add embedding and retriever config to rag_configurations
ALTER TABLE rag_configurations ADD COLUMN embedding_config TEXT; -- JSON: model, chunking, etc.
ALTER TABLE rag_configurations ADD COLUMN retriever_config TEXT; -- JSON: hybrid weights, top_k, etc.

-- Add pool config to db_connections
ALTER TABLE db_connections ADD COLUMN pool_config TEXT; -- JSON: pool_size, timeout, etc.
