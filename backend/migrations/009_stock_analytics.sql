-- Migration 009: Stock batch analytics and manual clip review fields.

CREATE TABLE IF NOT EXISTS stock_source_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_item_id UUID UNIQUE REFERENCES stock_pipeline_queue(id) ON DELETE SET NULL,
    job_id UUID UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    batch_id TEXT NOT NULL,
    series TEXT,
    source_url TEXT NOT NULL,
    r2_key TEXT,
    source_title TEXT NOT NULL,
    main_person TEXT NOT NULL,
    source_duration_s DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'processing',
    failed_step TEXT,
    error_message TEXT,
    s05_raw_candidates_count INTEGER NOT NULL DEFAULT 0,
    s05_valid_candidates_count INTEGER NOT NULL DEFAULT 0,
    s06_sent_candidates_count INTEGER NOT NULL DEFAULT 0,
    s06_returned_candidates_count INTEGER NOT NULL DEFAULT 0,
    s06_omitted_count INTEGER NOT NULL DEFAULT 0,
    s06_passed_count INTEGER NOT NULL DEFAULT 0,
    s07_cut_count INTEGER NOT NULL DEFAULT 0,
    final_clip_count INTEGER NOT NULL DEFAULT 0,
    max_score DOUBLE PRECISION,
    avg_score DOUBLE PRECISION,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_source_runs_channel_batch
    ON stock_source_runs(channel_id, batch_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_stock_source_runs_user_channel
    ON stock_source_runs(user_id, channel_id, created_at DESC);

CREATE TABLE IF NOT EXISTS stock_clip_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_run_id UUID REFERENCES stock_source_runs(id) ON DELETE CASCADE,
    queue_item_id UUID REFERENCES stock_pipeline_queue(id) ON DELETE SET NULL,
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    batch_id TEXT NOT NULL,
    main_person TEXT NOT NULL,
    candidate_id INTEGER NOT NULL,
    s05_start DOUBLE PRECISION,
    s05_end DOUBLE PRECISION,
    s05_estimated_duration DOUBLE PRECISION,
    s05_hook_text TEXT,
    s05_end_text TEXT,
    s05_reason TEXT,
    s05_loop_potential TEXT,
    s05_primary_signal TEXT,
    s05_content_type TEXT,
    s05_needs_context BOOLEAN,
    s05_target_guest_dominance DOUBLE PRECISION,
    s06_start DOUBLE PRECISION,
    s06_end DOUBLE PRECISION,
    s06_hook_text TEXT,
    s06_score INTEGER,
    s06_quality_verdict TEXT,
    s06_quality_notes TEXT,
    s06_omit_reason TEXT,
    s06_content_type TEXT,
    s06_clip_strategy_role TEXT,
    s06_posting_order INTEGER,
    s06_suggested_title TEXT,
    s06_suggested_description TEXT,
    s06_hallucination_flag BOOLEAN,
    passed_to_s07 BOOLEAN NOT NULL DEFAULT FALSE,
    s07_final_start DOUBLE PRECISION,
    s07_final_end DOUBLE PRECISION,
    s07_final_duration_s DOUBLE PRECISION,
    final_clip_id UUID REFERENCES clips(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(job_id, candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_clip_candidates_source_run
    ON stock_clip_candidates(source_run_id, candidate_id);

CREATE INDEX IF NOT EXISTS idx_stock_clip_candidates_job
    ON stock_clip_candidates(job_id, candidate_id);

CREATE INDEX IF NOT EXISTS idx_stock_clip_candidates_channel_batch
    ON stock_clip_candidates(channel_id, batch_id, s06_quality_verdict, s06_score DESC);

ALTER TABLE clips
    ADD COLUMN IF NOT EXISTS stock_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS stock_queue_item_id UUID REFERENCES stock_pipeline_queue(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS stock_source_run_id UUID REFERENCES stock_source_runs(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS stock_candidate_id UUID REFERENCES stock_clip_candidates(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS main_person TEXT,
    ADD COLUMN IF NOT EXISTS stock_review_status TEXT NOT NULL DEFAULT 'unreviewed',
    ADD COLUMN IF NOT EXISTS stock_review_note TEXT,
    ADD COLUMN IF NOT EXISTS stock_reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS stock_review_updated_by UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'clips_stock_review_status_check'
    ) THEN
        ALTER TABLE clips
            ADD CONSTRAINT clips_stock_review_status_check
            CHECK (stock_review_status IN ('unreviewed', 'selected', 'rejected', 'posted'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_clips_stock_batch
    ON clips(channel_id, stock_batch_id, stock_review_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_clips_stock_queue_item
    ON clips(stock_queue_item_id);

CREATE INDEX IF NOT EXISTS idx_clips_stock_candidate
    ON clips(stock_candidate_id);
