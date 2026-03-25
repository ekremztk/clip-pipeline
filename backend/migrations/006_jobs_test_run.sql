-- Migration 006: Add is_test_run column to jobs table
-- Required for Director test pipeline functionality

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_test_run BOOLEAN DEFAULT false;

-- Index for filtering test runs
CREATE INDEX IF NOT EXISTS idx_jobs_is_test_run ON jobs(is_test_run) WHERE is_test_run = true;
