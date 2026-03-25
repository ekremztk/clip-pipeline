-- Migration 005: director_test_runs table

CREATE TABLE IF NOT EXISTS director_test_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   TIMESTAMPTZ DEFAULT now(),
    test_name    TEXT NOT NULL,
    channel_id   TEXT,
    params       JSONB NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL DEFAULT 'created',
    result       JSONB,
    is_test_run  BOOLEAN DEFAULT true,
    notes        TEXT
);

CREATE INDEX IF NOT EXISTS idx_director_test_runs_channel ON director_test_runs(channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_director_test_runs_status ON director_test_runs(status);
