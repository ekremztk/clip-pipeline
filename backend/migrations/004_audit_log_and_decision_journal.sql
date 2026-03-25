-- Migration 004: Fix pipeline_audit_log schema mismatch + add director_decision_journal

-- ============================================================
-- Fix pipeline_audit_log: add columns that audit_logger.py actually writes
-- ============================================================

ALTER TABLE pipeline_audit_log
    ADD COLUMN IF NOT EXISTS status         TEXT,
    ADD COLUMN IF NOT EXISTS input_summary  JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS output_summary JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS token_usage    JSONB DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS error_stack    TEXT,
    ADD COLUMN IF NOT EXISTS success        BOOLEAN DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_audit_log_status ON pipeline_audit_log(step_name, status, created_at DESC);

-- ============================================================
-- Director Decision Journal (tracks user decisions + outcomes)
-- ============================================================

CREATE TABLE IF NOT EXISTS director_decision_journal (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ DEFAULT now(),
    decision        TEXT NOT NULL,
    context         TEXT,
    alternatives    TEXT,
    expected_impact TEXT,
    actual_impact   TEXT,
    status          TEXT DEFAULT 'open' CHECK (status IN ('open', 'measured', 'archived')),
    channel_id      TEXT,
    related_rec_id  UUID REFERENCES director_recommendations(id) ON DELETE SET NULL,
    measured_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_decision_journal_status ON director_decision_journal(status, timestamp DESC);
