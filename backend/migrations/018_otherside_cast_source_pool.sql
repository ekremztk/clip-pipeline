-- Migration 018: OtherSide Cast source discovery pool.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS otherside_cast_guests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_name TEXT NOT NULL UNIQUE,
    score INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    clips_published INTEGER NOT NULL DEFAULT 0,
    total_views BIGINT NOT NULL DEFAULT 0,
    avg_views BIGINT NOT NULL DEFAULT 0,
    category TEXT,
    CONSTRAINT otherside_cast_guests_score_check CHECK (score >= 0 AND score <= 100),
    CONSTRAINT otherside_cast_guests_category_check CHECK (
        category IS NULL OR category IN ('evergreen', 'experimental', 'trending')
    )
);

CREATE INDEX IF NOT EXISTS otherside_cast_guests_score_idx
    ON otherside_cast_guests(score DESC);

CREATE TABLE IF NOT EXISTS otherside_cast_source_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_name TEXT NOT NULL,
    handle TEXT NOT NULL UNIQUE,
    youtube_channel_id TEXT,
    active BOOLEAN NOT NULL DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS otherside_cast_source_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id UUID NOT NULL REFERENCES otherside_cast_guests(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source_channel TEXT NOT NULL,
    source_handle TEXT NOT NULL,
    view_count BIGINT NOT NULL DEFAULT 0,
    duration_seconds INTEGER,
    upload_date DATE,
    thumbnail_url TEXT,
    clipped BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS otherside_cast_source_videos_guest_id_idx
    ON otherside_cast_source_videos(guest_id);

CREATE INDEX IF NOT EXISTS otherside_cast_source_videos_source_channel_idx
    ON otherside_cast_source_videos(source_channel);

CREATE INDEX IF NOT EXISTS otherside_cast_source_videos_clipped_idx
    ON otherside_cast_source_videos(clipped);

UPDATE channels
SET id = 'otherside_cast',
    display_name = 'OtherSide Cast',
    pool_prefix = 'otherside_cast',
    updated_at = now()
WHERE id = 'theclips_viral'
  AND NOT EXISTS (
      SELECT 1 FROM channels existing WHERE existing.id = 'otherside_cast'
  );

UPDATE channels
SET display_name = 'OtherSide Cast',
    pool_prefix = 'otherside_cast',
    updated_at = now()
WHERE id = 'otherside_cast';
