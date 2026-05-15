-- Migration 008: Persistent stock source processing queue
-- Used for batch processing R2-hosted source videos without deleting the source archive.

CREATE TABLE IF NOT EXISTS stock_pipeline_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    batch_id TEXT NOT NULL,
    series TEXT,
    source_url TEXT NOT NULL,
    r2_key TEXT,
    video_title TEXT NOT NULL,
    main_person TEXT NOT NULL,
    target_guest TEXT,
    caption_template TEXT NOT NULL DEFAULT 'clean',
    reframe_content_type TEXT NOT NULL DEFAULT 'podcast',
    clip_duration_min INTEGER DEFAULT 10,
    clip_duration_max INTEGER DEFAULT 60,
    priority INTEGER NOT NULL DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'queued',
    job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    locked_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_queue_channel_batch_status
    ON stock_pipeline_queue(channel_id, batch_id, status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_stock_queue_user_channel
    ON stock_pipeline_queue(user_id, channel_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_queue_unique_source
    ON stock_pipeline_queue(channel_id, batch_id, source_url);
