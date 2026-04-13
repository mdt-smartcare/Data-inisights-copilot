-- Migration: 007_per_agent_sql_examples.sql
-- Description: Add agent_id to sql_examples for per-agent few-shot learning
-- Author: Data Insights Copilot
-- Date: 2026-04-13

-- ============================================
-- Per-Agent SQL Examples
-- ============================================
-- Previously, sql_examples were global (shared across all agents).
-- This migration adds agent_id to scope examples per-agent for better accuracy.
-- Global examples (agent_id IS NULL) serve as fallback for all agents.

-- Add agent_id column if sql_examples table exists
DO $$
BEGIN
    -- First check if sql_examples table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sql_examples' AND table_schema = 'public') THEN
        -- Add agent_id column if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'sql_examples' AND column_name = 'agent_id'
        ) THEN
            ALTER TABLE sql_examples 
            ADD COLUMN agent_id UUID REFERENCES agents(id) ON DELETE CASCADE;
            
            -- Create index for faster lookups
            CREATE INDEX IF NOT EXISTS idx_sql_examples_agent_id ON sql_examples(agent_id);
            
            RAISE NOTICE 'Added agent_id column to sql_examples table';
        END IF;
    ELSE
        -- Create sql_examples table with agent_id from the start
        CREATE TABLE IF NOT EXISTS sql_examples (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            sql_query TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            tags TEXT,
            description TEXT,
            agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by UUID REFERENCES users(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_sql_examples_agent_id ON sql_examples(agent_id);
        CREATE INDEX IF NOT EXISTS idx_sql_examples_category ON sql_examples(category);
        
        RAISE NOTICE 'Created sql_examples table with agent_id support';
    END IF;
END $$;

-- ============================================
-- Comments
-- ============================================
COMMENT ON COLUMN sql_examples.agent_id IS 'Agent ID for scoping examples. NULL = global (fallback for all agents)';
