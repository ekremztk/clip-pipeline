-- Migration 015: Admin YouTube OAuth connection and channel snapshots.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS admin_youtube_oauth_states (
    state TEXT PRIMARY KEY,
    admin_user_id UUID NOT NULL REFERENCES admin_users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_oauth_states_admin_user
    ON admin_youtube_oauth_states(admin_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS admin_youtube_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID NOT NULL REFERENCES admin_users(user_id) ON DELETE CASCADE,
    youtube_channel_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    custom_url TEXT,
    thumbnail_url TEXT,
    country TEXT,
    subscriber_count BIGINT,
    view_count BIGINT,
    video_count BIGINT,
    uploads_playlist_id TEXT,
    status TEXT NOT NULL DEFAULT 'connected',
    connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (admin_user_id, youtube_channel_id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'admin_youtube_channels_status_check'
    ) THEN
        ALTER TABLE admin_youtube_channels
            ADD CONSTRAINT admin_youtube_channels_status_check
            CHECK (status IN ('connected', 'syncing', 'error', 'revoked'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_admin_youtube_channels_admin_user
    ON admin_youtube_channels(admin_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS admin_youtube_tokens (
    channel_id UUID PRIMARY KEY REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    scope TEXT,
    token_type TEXT,
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_youtube_daily_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,
    views BIGINT,
    engaged_views BIGINT,
    estimated_minutes_watched NUMERIC,
    average_view_duration_seconds NUMERIC,
    subscribers_gained BIGINT,
    subscribers_lost BIGINT,
    estimated_revenue NUMERIC,
    currency TEXT NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_daily_metrics_channel_date
    ON admin_youtube_daily_metrics(channel_id, metric_date DESC);

CREATE TABLE IF NOT EXISTS admin_youtube_country_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    country_code TEXT NOT NULL,
    views BIGINT,
    engaged_views BIGINT,
    estimated_minutes_watched NUMERIC,
    estimated_revenue NUMERIC,
    currency TEXT NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, period_start, period_end, country_code)
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_country_metrics_channel_period
    ON admin_youtube_country_metrics(channel_id, period_end DESC);

CREATE TABLE IF NOT EXISTS admin_youtube_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID REFERENCES admin_youtube_channels(id) ON DELETE CASCADE,
    admin_user_id UUID REFERENCES admin_users(user_id) ON DELETE SET NULL,
    sync_type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_youtube_sync_logs_channel
    ON admin_youtube_sync_logs(channel_id, created_at DESC);
