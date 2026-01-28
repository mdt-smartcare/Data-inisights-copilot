-- Create sql_examples table for few-shot learning
CREATE TABLE IF NOT EXISTS sql_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    sql_query TEXT NOT NULL,
    description TEXT,
    embedding BLOB, -- To store vector embeddings (if we use sqlite-vss or manual cosine sim)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for description search (fallback if no vector search)
CREATE INDEX IF NOT EXISTS idx_sql_examples_desc ON sql_examples(description);

-- Initial seed examples (high quality, reliable queries)
INSERT INTO sql_examples (question, sql_query, description) VALUES 
('count patients with hypertension', 
'SELECT COUNT(DISTINCT patient_track_id) FROM v_analytics_enrollment WHERE enrolled_condition = ''Hypertension'' AND workflow_status = ''NCD'' AND patient_status = ''ENROLLED''', 
'Count enrolled hypertension patients');

INSERT INTO sql_examples (question, sql_query, description) VALUES 
('list failed screenings', 
'SELECT COUNT(DISTINCT patient_track_id) FROM v_analytics_screening WHERE workflow_status = ''NCD'' AND (has_bp_reading = FALSE AND has_bg_reading = FALSE)', 
'Count patients who started but did not complete screening');

INSERT INTO sql_examples (question, sql_query, description) VALUES 
('show me referrals by reason', 
'SELECT referred_reason, COUNT(DISTINCT patient_track_id) as count FROM v_analytics_screening WHERE workflow_status = ''NCD'' AND is_referred = TRUE GROUP BY referred_reason ORDER BY count DESC', 
'Breakdown of referrals by reason');
