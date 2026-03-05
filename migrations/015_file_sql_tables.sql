-- Migration: 015_file_sql_tables.sql
-- Description: Add tables for storing uploaded file data for SQL querying
-- This enables persistent SQL queries on uploaded CSV/Excel files

-- Table to track uploaded files and their SQL table metadata
CREATE TABLE IF NOT EXISTS uploaded_file_tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    table_name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,  -- 'csv' or 'xlsx'
    columns TEXT NOT NULL,    -- JSON array of column names
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, table_name)
);

-- Table to store the actual data rows as JSON
-- This allows us to reconstruct the data for SQL queries
CREATE TABLE IF NOT EXISTS uploaded_file_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_table_id INTEGER NOT NULL,
    row_number INTEGER NOT NULL,
    row_data TEXT NOT NULL,  -- JSON object of column:value pairs
    FOREIGN KEY (file_table_id) REFERENCES uploaded_file_tables(id) ON DELETE CASCADE
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_uploaded_file_data_table_id ON uploaded_file_data(file_table_id);
CREATE INDEX IF NOT EXISTS idx_uploaded_file_tables_user ON uploaded_file_tables(user_id);
