-- Add data source configuration fields to prompt_configs

-- 1. Add data_source_type text field (e.g., 'database' or 'file')
ALTER TABLE prompt_configs ADD COLUMN data_source_type TEXT DEFAULT 'database';

-- 2. Add fields related to file ingestion
ALTER TABLE prompt_configs ADD COLUMN ingestion_documents TEXT;
ALTER TABLE prompt_configs ADD COLUMN ingestion_file_name TEXT;
ALTER TABLE prompt_configs ADD COLUMN ingestion_file_type TEXT;
