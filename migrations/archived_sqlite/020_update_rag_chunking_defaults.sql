-- Migration: 020_update_rag_chunking_defaults.sql
-- Description: Update RAG category chunk_size and chunk_overlap to industry-standard defaults
-- Author: Schema-Driven RAG Architecture
-- Date: 2026-03-09
--
-- This migration updates the RAG settings to use smaller, more precise chunks
-- which are better suited for medical/healthcare RAG applications.
-- 
-- Previous values: chunk_size=800, chunk_overlap=150
-- New values: chunk_size=512, chunk_overlap=100 (~20% overlap)

-- Update chunk_size in RAG category from 800 to 512
UPDATE system_settings 
SET value = '512', 
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'migration_020'
WHERE category = 'rag' 
  AND key = 'chunk_size' 
  AND value = '800';

-- Update chunk_overlap in RAG category from 150 to 100
UPDATE system_settings 
SET value = '100', 
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'migration_020'
WHERE category = 'rag' 
  AND key = 'chunk_overlap' 
  AND value = '150';

-- Record the changes in settings_history for audit trail
INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
SELECT id, 'rag', 'chunk_size', '800', '512', 'migration_020', 'Update to industry-standard defaults for medical RAG'
FROM system_settings 
WHERE category = 'rag' AND key = 'chunk_size' AND value = '512';

INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
SELECT id, 'rag', 'chunk_overlap', '150', '100', 'migration_020', 'Update to industry-standard defaults for medical RAG'
FROM system_settings 
WHERE category = 'rag' AND key = 'chunk_overlap' AND value = '100';
