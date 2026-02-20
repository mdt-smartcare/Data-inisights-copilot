-- Migration: Add external_id for OIDC/Keycloak integration
-- Adds external_id column to users table to store OIDC subject (sub) claim
-- This allows linking local user records to Keycloak identities

-- Add external_id column to users table
-- Note: UNIQUE constraint added via index since SQLite doesn't support UNIQUE in ALTER TABLE
ALTER TABLE users ADD COLUMN external_id TEXT;

-- Create UNIQUE index for OIDC user lookup (enforces uniqueness)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_external_id ON users(external_id) WHERE external_id IS NOT NULL;

-- Make password_hash nullable for OIDC-only users
-- Note: SQLite doesn't support ALTER COLUMN, so we need to recreate the table
-- For now, we'll just document that password_hash can be empty for OIDC users
-- The application code will handle this appropriately
