-- Director Module Tables
-- Run this in Supabase SQL Editor

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Event Collection
-- ============================================================
CREATE TABLE IF NOT EXISTS director_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp   TIMESTAMPTZ DEFAULT now(),
    module_name TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}',
    session_id  TEXT,
    channel_id  TEXT
);

CREATE INDEX IF NOT EXISTS idx_director_events_module   ON director_events(module_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_director_events_type     ON director_events(event_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_director_events_session  ON director_events(session_id);
CREATE INDEX IF NOT EXISTS idx_director_events_channel  ON director_events(channel_id, timestamp DESC);

-- ============================================================
-- Conversation History (Short-term memory)
-- ============================================================
CREATE TABLE IF NOT EXISTS director_conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool_result')),
    content     TEXT NOT NULL,
    tool_calls  JSONB,
    timestamp   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_director_conv_session ON director_conversations(session_id, timestamp ASC);

-- ============================================================
-- Long-term Semantic Memory
-- ============================================================
CREATE TABLE IF NOT EXISTS director_memory (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        TEXT NOT NULL CHECK (type IN ('decision', 'context', 'plan', 'note', 'learning')),
    content     TEXT NOT NULL,
    embedding   vector(768),
    tags        TEXT[] DEFAULT '{}',
    source      TEXT DEFAULT 'user_instruction' CHECK (source IN ('user_instruction', 'director_inference', 'auto')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_director_memory_embedding ON director_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
CREATE INDEX IF NOT EXISTS idx_director_memory_type ON director_memory(type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_director_memory_tags ON director_memory USING GIN(tags);

-- ============================================================
-- Analysis History
-- ============================================================
CREATE TABLE IF NOT EXISTS director_analyses (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp         TIMESTAMPTZ DEFAULT now(),
    module_name       TEXT NOT NULL,
    triggered_by      TEXT NOT NULL DEFAULT 'manual'
                          CHECK (triggered_by IN ('manual', 'scheduled', 'post_test', 'chat')),
    score             INT NOT NULL,
    subscores         JSONB NOT NULL DEFAULT '{}',
    findings          JSONB NOT NULL DEFAULT '[]',
    recommendations   JSONB NOT NULL DEFAULT '[]',
    data_period_start TIMESTAMPTZ,
    data_period_end   TIMESTAMPTZ,
    data_points_used  INT,
    context_snapshot  JSONB,
    gemini_calls      INT DEFAULT 0,
    total_tokens_used INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_director_analyses_module ON director_analyses(module_name, timestamp DESC);

-- ============================================================
-- Recommendations (actionable items)
-- ============================================================
CREATE TABLE IF NOT EXISTS director_recommendations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id      UUID REFERENCES director_analyses(id) ON DELETE SET NULL,
    module_name      TEXT NOT NULL,
    priority         INT NOT NULL DEFAULT 1,
    impact_score     FLOAT,
    effort_score     INT,
    title            TEXT NOT NULL,
    what             TEXT NOT NULL,
    why              TEXT NOT NULL,
    expected_impact  TEXT NOT NULL,
    risk             TEXT,
    alternative      TEXT,
    data_needs       TEXT,
    status           TEXT DEFAULT 'pending'
                         CHECK (status IN ('pending', 'in_progress', 'applied', 'dismissed', 'measuring')),
    dismissed_reason TEXT,
    applied_at       TIMESTAMPTZ,
    measured_impact  FLOAT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_director_recs_status    ON director_recommendations(status, priority);
CREATE INDEX IF NOT EXISTS idx_director_recs_module    ON director_recommendations(module_name, created_at DESC);

-- ============================================================
-- Cross-module Bridge Signals
-- ============================================================
CREATE TABLE IF NOT EXISTS director_cross_module_signals (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp     TIMESTAMPTZ DEFAULT now(),
    signal_type   TEXT NOT NULL,
    source_module TEXT NOT NULL,
    target_module TEXT NOT NULL,
    payload       JSONB NOT NULL DEFAULT '{}',
    channel_id    TEXT
);

CREATE INDEX IF NOT EXISTS idx_director_cms_type    ON director_cross_module_signals(signal_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_director_cms_channel ON director_cross_module_signals(channel_id, timestamp DESC);

-- ============================================================
-- Prompt Laboratory
-- ============================================================
CREATE TABLE IF NOT EXISTS director_prompt_lab (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    module_name     TEXT NOT NULL,
    step            TEXT NOT NULL,
    prompt_text     TEXT NOT NULL,
    version         INT NOT NULL DEFAULT 1,
    is_active       BOOLEAN DEFAULT false,
    notes           TEXT,
    test_results    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_director_prompts_step ON director_prompt_lab(module_name, step, version DESC);

-- ============================================================
-- Pipeline Audit Log (step-level timing for Director analytics)
-- ============================================================
CREATE TABLE IF NOT EXISTS pipeline_audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id       TEXT NOT NULL,
    step_name    TEXT NOT NULL,
    step_number  INT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms  INT,
    success      BOOLEAN DEFAULT true,
    error_message TEXT,
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_job  ON pipeline_audit_log(job_id, step_number);
CREATE INDEX IF NOT EXISTS idx_audit_log_step ON pipeline_audit_log(step_name, created_at DESC);
