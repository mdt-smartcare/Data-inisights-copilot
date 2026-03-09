-- Migration: 021_update_embedding_defaults_bge_base.sql
-- Description: Change default embedding model from bge-m3 to bge-base-en-v1.5 for faster performance
-- Author: Schema-Driven RAG Architecture
-- Date: 2026-03-09
--
-- This migration updates the default embedding model to bge-base-en-v1.5 which is:
-- - ~2-3x faster than bge-m3
-- - 768 dimensions (vs 1024) = less storage and faster similarity search
-- - Excellent quality for English-language data
--
-- Note: Uses UPDATE with WHERE clause to only change if still using old defaults

-- Update embedding provider
UPDATE system_settings 
SET value = '"sentence-transformers"',
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'migration_021'
WHERE category = 'embedding' 
  AND key = 'provider' 
  AND value = '"bge-m3"';

-- Update model name
UPDATE system_settings 
SET value = '"BAAI/bge-base-en-v1.5"',
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'migration_021'
WHERE category = 'embedding' 
  AND key = 'model_name' 
  AND value = '"BAAI/bge-m3"';

-- Update model path
UPDATE system_settings 
SET value = '"./models/bge-base-en-v1.5"',
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'migration_021'
WHERE category = 'embedding' 
  AND key = 'model_path' 
  AND value = '"./models/bge-m3"';

-- Update dimensions (768 for bge-base-en-v1.5 vs 1024 for bge-m3)
UPDATE system_settings 
SET value = '768',
    updated_at = CURRENT_TIMESTAMP,
    updated_by = 'migration_021'
WHERE category = 'embedding' 
  AND key = 'dimensions' 
  AND value = '1024';

-- Record changes in settings_history for audit trail
INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
SELECT id, 'embedding', 'provider', '"bge-m3"', '"sentence-transformers"', 'migration_021', 'Switched to faster bge-base-en-v1.5 model'
FROM system_settings 
WHERE category = 'embedding' AND key = 'provider' AND value = '"sentence-transformers"';

INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
SELECT id, 'embedding', 'model_name', '"BAAI/bge-m3"', '"BAAI/bge-base-en-v1.5"', 'migration_021', 'Switched to faster bge-base-en-v1.5 model'
FROM system_settings 
WHERE category = 'embedding' AND key = 'model_name' AND value = '"BAAI/bge-base-en-v1.5"';

INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
SELECT id, 'embedding', 'model_path', '"./models/bge-m3"', '"./models/bge-base-en-v1.5"', 'migration_021', 'Switched to faster bge-base-en-v1.5 model'
FROM system_settings 
WHERE category = 'embedding' AND key = 'model_path' AND value = '"./models/bge-base-en-v1.5"';

INSERT INTO settings_history (setting_id, category, key, previous_value, new_value, changed_by, change_reason)
SELECT id, 'embedding', 'dimensions', '1024', '768', 'migration_021', 'Switched to faster bge-base-en-v1.5 model (768 dims)'
FROM system_settings 
WHERE category = 'embedding' AND key = 'dimensions' AND value = '768';
