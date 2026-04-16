-- Migration: Update chunking defaults to industry-standard values
-- Created: 2026-03-09
-- Purpose: Update existing databases with new chunking defaults (512/100/128/25)
--
-- Previous values (800/150/200/50) were too large for optimal RAG performance.
-- Industry best practices for medical/healthcare RAG recommend:
-- - Smaller chunks = more precise retrieval + faster processing
-- - ~20% overlap maintains context between chunks

-- ============================================================================
-- Update Chunking Settings to Industry-Standard Values
-- ============================================================================
UPDATE system_settings 
SET value = '512', 
    description = 'Parent chunk size for hierarchical chunking (industry standard)'
WHERE category = 'chunking' AND key = 'parent_chunk_size' AND value = '800';

UPDATE system_settings 
SET value = '100', 
    description = 'Overlap between parent chunks (~20% of size)'
WHERE category = 'chunking' AND key = 'parent_chunk_overlap' AND value = '150';

UPDATE system_settings 
SET value = '128', 
    description = 'Child chunk size for hierarchical chunking'
WHERE category = 'chunking' AND key = 'child_chunk_size' AND value = '200';

UPDATE system_settings 
SET value = '25', 
    description = 'Overlap between child chunks (~20% of size)'
WHERE category = 'chunking' AND key = 'child_chunk_overlap' AND value = '50';
