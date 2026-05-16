-- Migration 010: Gemini post-S10 review records for stock clips.

CREATE TABLE IF NOT EXISTS stock_clip_ai_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clip_id UUID NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    stock_batch_id TEXT,
    stock_queue_item_id UUID REFERENCES stock_pipeline_queue(id) ON DELETE SET NULL,
    stock_source_run_id UUID REFERENCES stock_source_runs(id) ON DELETE SET NULL,
    stock_candidate_id UUID REFERENCES stock_clip_candidates(id) ON DELETE SET NULL,
    main_person TEXT,
    reviewer TEXT NOT NULL DEFAULT 'gemini',
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    attempt_count INTEGER NOT NULL DEFAULT 1,
    source_title TEXT,
    clip_title TEXT,
    clip_description TEXT,
    video_url TEXT,
    transcript_chars INTEGER NOT NULL DEFAULT 0,
    claude_score INTEGER,
    gemini_score INTEGER,
    viral_score INTEGER,
    channel_fit_score INTEGER,
    publish_priority_score INTEGER,
    hook_score INTEGER,
    retention_score INTEGER,
    opening_score INTEGER,
    ending_score INTEGER,
    boundary_score INTEGER,
    clip_integrity_score INTEGER,
    context_clarity_score INTEGER,
    visual_reaction_score INTEGER,
    audio_energy_score INTEGER,
    titleability_score INTEGER,
    thumbnail_score INTEGER,
    loop_score INTEGER,
    risk_score INTEGER,
    has_half_word_start BOOLEAN,
    has_half_word_end BOOLEAN,
    starts_too_early BOOLEAN,
    starts_too_late BOOLEAN,
    ends_too_early BOOLEAN,
    ends_too_late BOOLEAN,
    has_unclear_reference BOOLEAN,
    needs_context BOOLEAN,
    final_verdict TEXT,
    opening_assessment TEXT,
    ending_assessment TEXT,
    story_integrity_assessment TEXT,
    viewer_effect TEXT,
    title_feedback TEXT,
    recommended_title TEXT,
    recommended_description TEXT,
    why_good TEXT,
    why_bad TEXT,
    reason_tags TEXT[] NOT NULL DEFAULT '{}',
    risk_flags TEXT[] NOT NULL DEFAULT '{}',
    raw_response JSONB,
    token_usage JSONB,
    cost_usd DOUBLE PRECISION,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (clip_id, reviewer)
);

CREATE INDEX IF NOT EXISTS idx_stock_clip_ai_reviews_batch_status
    ON stock_clip_ai_reviews(channel_id, stock_batch_id, status, publish_priority_score DESC);

CREATE INDEX IF NOT EXISTS idx_stock_clip_ai_reviews_clip
    ON stock_clip_ai_reviews(clip_id);

CREATE INDEX IF NOT EXISTS idx_stock_clip_ai_reviews_scores
    ON stock_clip_ai_reviews(channel_id, stock_batch_id, publish_priority_score DESC, viral_score DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'stock_clip_ai_reviews_status_check'
    ) THEN
        ALTER TABLE stock_clip_ai_reviews
            ADD CONSTRAINT stock_clip_ai_reviews_status_check
            CHECK (status IN ('processing', 'completed', 'failed'));
    END IF;
END $$;
