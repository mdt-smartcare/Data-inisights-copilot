-- Migration 016: Add schema snapshot to vector_db_registry for drift detection
-- This allows the system to detect when the underlying database schema changes
-- before running embedding jobs, preventing crashes from missing columns/tables

ALTER TABLE vector_db_registry ADD COLUMN schema_snapshot TEXT;
ALTER TABLE vector_db_registry ADD COLUMN schema_snapshot_at TIMESTAMP;

-- Schema drift detection logs
CREATE TABLE IF NOT EXISTS schema_drift_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector_db_name TEXT NOT NULL,
    drift_type TEXT NOT NULL,  -- 'table_removed', 'column_removed', 'column_type_changed', 'table_added', 'column_added'
    severity TEXT NOT NULL DEFAULT 'warning',  -- 'critical', 'warning', 'info'
    entity_name TEXT NOT NULL,  -- table or column name
    details TEXT,  -- JSON with additional details
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by TEXT,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_schema_drift_vector_db ON schema_drift_logs(vector_db_name);
CREATE INDEX IF NOT EXISTS idx_schema_drift_severity ON schema_drift_logs(severity);
CREATE INDEX IF NOT EXISTS idx_schema_drift_detected ON schema_drift_logs(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_schema_drift_unresolved ON schema_drift_logs(resolved_at) WHERE resolved_at IS NULL;
