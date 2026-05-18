-- Migration 016: Admin YouTube analytics sync and realtime view snapshots.

ALTER TABLE admin_youtube_daily_metrics
    ADD COLUMN IF NOT EXISTS average_view_percentage NUMERIC,
    ADD COLUMN IF NOT EXISTS estimated_ad_revenue NUMERIC,
    ADD COLUMN IF NOT EXISTS cpm NUMERIC,
    ADD COLUMN IF NOT EXISTS playback_based_cpm NUMERIC;

CREATE TABLE IF NOT EXISTS admin_youtube_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    youtube_video_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    thumbnail_url TEXT,
    published_at TIMESTAMPTZ,
    duration TEXT,
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT,
    privacy_status TEXT,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, youtube_video_id)
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_videos_channel_published
    ON admin_youtube_videos(channel_id, published_at DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS admin_youtube_realtime_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    youtube_video_id TEXT NOT NULL,
    view_count BIGINT NOT NULL DEFAULT 0,
    like_count BIGINT,
    comment_count BIGINT,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_realtime_snapshots_channel_time
    ON admin_youtube_realtime_snapshots(channel_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_realtime_snapshots_video_time
    ON admin_youtube_realtime_snapshots(channel_id, youtube_video_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS admin_youtube_video_daily_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    youtube_video_id TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    views BIGINT,
    estimated_minutes_watched NUMERIC,
    average_view_duration_seconds NUMERIC,
    average_view_percentage NUMERIC,
    subscribers_gained BIGINT,
    subscribers_lost BIGINT,
    estimated_revenue NUMERIC,
    estimated_ad_revenue NUMERIC,
    cpm NUMERIC,
    playback_based_cpm NUMERIC,
    currency TEXT NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, youtube_video_id, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_video_daily_metrics_channel_period
    ON admin_youtube_video_daily_metrics(channel_id, period_end DESC);
