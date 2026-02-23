-- Add agent_id to system_prompts table
ALTER TABLE system_prompts ADD COLUMN agent_id INTEGER REFERENCES agents(id);

-- Create index for faster lookups
CREATE INDEX idx_system_prompts_agent_id ON system_prompts(agent_id);
