-- Migration 017: Smart realtime tracking metadata.

ALTER TABLE admin_youtube_videos
    ADD COLUMN IF NOT EXISTS realtime_tracking_tier TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS realtime_hourly_view_rate NUMERIC,
    ADD COLUMN IF NOT EXISTS realtime_last_classified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS realtime_next_snapshot_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'admin_youtube_videos_realtime_tracking_tier_check'
    ) THEN
        ALTER TABLE admin_youtube_videos
            ADD CONSTRAINT admin_youtube_videos_realtime_tracking_tier_check
            CHECK (realtime_tracking_tier IN ('unknown', 'calibration', 'recent', 'hot', 'hourly'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_admin_youtube_videos_realtime_next_snapshot
    ON admin_youtube_videos(channel_id, realtime_next_snapshot_at ASC NULLS FIRST);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_videos_realtime_tier
    ON admin_youtube_videos(channel_id, realtime_tracking_tier, realtime_hourly_view_rate DESC NULLS LAST);
