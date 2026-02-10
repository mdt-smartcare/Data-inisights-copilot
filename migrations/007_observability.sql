-- Migration: Add extended observability settings and usage tracking
-- Created: 2026-02-10
-- Description: Adds observability configuration and usage_metrics table for cost/token tracking

-- ============================================================================
-- Extended Observability Settings
-- ============================================================================
INSERT OR IGNORE INTO system_settings (category, key, value, value_type, description) VALUES
('observability', 'log_destinations', '["console", "file"]', 'json', 'Active log output destinations'),
('observability', 'log_file_path', '"./logs/backend.log"', 'string', 'Path to log file'),
('observability', 'log_max_size_mb', '100', 'number', 'Maximum log file size in MB before rotation'),
('observability', 'log_backup_count', '5', 'number', 'Number of rotated log files to keep'),
('observability', 'langfuse_enabled', 'false', 'boolean', 'Enable Langfuse LLM tracing'),
('observability', 'opentelemetry_enabled', 'false', 'boolean', 'Enable OpenTelemetry distributed tracing'),
('observability', 'otlp_endpoint', '"http://localhost:4317"', 'string', 'OTLP exporter endpoint for traces'),
('observability', 'tracing_provider', '"none"', 'string', 'Active tracing: none, langfuse, opentelemetry, both'),
('observability', 'observability_enabled', 'false', 'boolean', 'Master toggle for all observability features');

-- ============================================================================
-- Usage Metrics Table - Tracks LLM, embedding, and vector search operations
-- ============================================================================
CREATE TABLE IF NOT EXISTS usage_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,                    -- Unique trace identifier
    session_id TEXT,                           -- User session ID (if available)
    user_id TEXT,                              -- User who triggered the operation
    operation_type TEXT NOT NULL,              -- 'llm', 'embedding', 'vector_search', 'rag_pipeline'
    model_name TEXT,                           -- Model used (e.g., 'gpt-4o', 'bge-m3')
    provider TEXT,                             -- Provider (e.g., 'openai', 'local')
    
    -- Token metrics (for LLM and embedding operations)
    input_tokens INTEGER,                      -- Tokens in input/prompt
    output_tokens INTEGER,                     -- Tokens in output/completion
    total_tokens INTEGER,                      -- Total tokens consumed
    
    -- Cost tracking
    estimated_cost_usd REAL,                   -- Estimated cost in USD
    
    -- Performance metrics
    duration_ms INTEGER,                       -- Operation duration in milliseconds
    
    -- Operation-specific metadata
    batch_size INTEGER,                        -- For embeddings: number of documents
    results_count INTEGER,                     -- For vector search: number of results
    query_text TEXT,                           -- Query/input text (truncated for privacy)
    
    -- Additional context as JSON
    metadata TEXT,                             -- JSON blob for additional data
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Indexes for efficient querying
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_usage_metrics_operation_type ON usage_metrics(operation_type);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_created_at ON usage_metrics(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_trace_id ON usage_metrics(trace_id);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_user_id ON usage_metrics(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_metrics_model ON usage_metrics(model_name);

-- ============================================================================
-- Aggregation view for quick stats (optional, for convenience)
-- ============================================================================
CREATE VIEW IF NOT EXISTS usage_stats_24h AS
SELECT 
    operation_type,
    model_name,
    COUNT(*) as call_count,
    SUM(total_tokens) as total_tokens,
    SUM(input_tokens) as input_tokens,
    SUM(output_tokens) as output_tokens,
    SUM(estimated_cost_usd) as total_cost_usd,
    AVG(duration_ms) as avg_duration_ms,
    SUM(batch_size) as total_documents,
    SUM(results_count) as total_results
FROM usage_metrics
WHERE created_at >= datetime('now', '-24 hours')
GROUP BY operation_type, model_name;
