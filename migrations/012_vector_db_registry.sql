-- Migration to add Vector DB registry table
CREATE TABLE IF NOT EXISTS vector_db_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    data_source_id TEXT, -- Can be DB connection ID or file name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);
