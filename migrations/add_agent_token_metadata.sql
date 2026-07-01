-- Migration: add_agent_token_metadata
-- Adds token_name (optional friendly label) and last_used_at (auth tracking)
-- to the agents table.  Both columns are nullable so existing rows need no backfill.

ALTER TABLE agents ADD COLUMN token_name TEXT;
ALTER TABLE agents ADD COLUMN last_used_at DATETIME;
