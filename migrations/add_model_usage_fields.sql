-- Migration: Add usage tracking fields to model_connections table
-- Description: Adds last_used_at, total_tokens_consumed, and total_cost fields

-- Add new columns to model_connections table
ALTER TABLE model_connections ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP;
ALTER TABLE model_connections ADD COLUMN IF NOT EXISTS total_tokens_consumed INTEGER DEFAULT 0;
ALTER TABLE model_connections ADD COLUMN IF NOT EXISTS total_cost REAL DEFAULT 0.0;

-- Update existing rows to have default values
UPDATE model_connections 
SET 
    total_tokens_consumed = 0,
    total_cost = 0.0
WHERE total_tokens_consumed IS NULL OR total_cost IS NULL;
