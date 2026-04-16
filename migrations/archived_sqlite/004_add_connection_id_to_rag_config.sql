-- Migration: 004_add_connection_id_to_rag_config.sql
-- Description: Add connection_id and is_active columns to rag_configurations table
-- Author: Schema-Driven RAG Architecture
-- Date: 2026-01-28

ALTER TABLE rag_configurations ADD COLUMN connection_id INTEGER REFERENCES db_connections(id);
ALTER TABLE rag_configurations ADD COLUMN is_active INTEGER DEFAULT 0; -- Boolean: 1 if this is the currently serving config

CREATE INDEX IF NOT EXISTS idx_rag_config_connection ON rag_configurations(connection_id);
CREATE INDEX IF NOT EXISTS idx_rag_config_active ON rag_configurations(is_active);
