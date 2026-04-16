-- Migration to add Vector DB scheduler settings
CREATE TABLE IF NOT EXISTS vector_db_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector_db_name TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 0,
    schedule_type TEXT DEFAULT 'daily',  -- 'daily', 'hourly', 'weekly', 'custom'
    schedule_hour INTEGER DEFAULT 2,      -- Hour of day (0-23) for daily/weekly
    schedule_minute INTEGER DEFAULT 0,    -- Minute (0-59)
    schedule_day_of_week INTEGER,         -- 0=Monday, 6=Sunday (for weekly)
    schedule_cron TEXT,                   -- Custom cron expression (for custom type)
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status TEXT,                 -- 'success', 'failed', 'running'
    last_run_job_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_vector_db_schedules_enabled ON vector_db_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_vector_db_schedules_next_run ON vector_db_schedules(next_run_at);
