-- Migration: Add agent_id to system_prompts
-- Created: 2026-02-13
-- Description: Adds agent_id column to system_prompts table to support agent-specific prompts

-- Add agent_id column to system_prompts
ALTER TABLE system_prompts ADD COLUMN agent_id INTEGER REFERENCES agents(id);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_system_prompts_agent_id ON system_prompts(agent_id);
