-- Migration 013: Add document_index table for incremental embeddings
CREATE TABLE IF NOT EXISTS document_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector_db_name TEXT NOT NULL,
    source_id TEXT NOT NULL,
    checksum TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vector_db_name, source_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_index_vdbname ON document_index(vector_db_name);
