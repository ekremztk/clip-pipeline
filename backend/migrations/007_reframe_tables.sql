-- Migration 007: Reframe system tables
-- reframe_jobs: replaces the in-memory _jobs dict in the old reframe route
-- reframe_metadata: pipeline-to-editor bridge (pipeline stores, editor reads)

-- ─── reframe_jobs ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS reframe_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,

    status          TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued', 'processing', 'done', 'error')),
    step            TEXT NOT NULL DEFAULT 'Starting...',
    percent         INT  NOT NULL DEFAULT 0
                        CHECK (percent >= 0 AND percent <= 100),

    -- Input parameters (enables re-run)
    clip_url        TEXT,
    clip_local_path TEXT,
    clip_id         TEXT,
    job_id          TEXT,           -- pipeline jobs.id → diarization lookup
    clip_start      FLOAT NOT NULL DEFAULT 0.0,
    clip_end        FLOAT,

    -- Processing config
    strategy        TEXT NOT NULL DEFAULT 'podcast'
                        CHECK (strategy IN ('podcast')),
    aspect_ratio    TEXT NOT NULL DEFAULT '9:16'
                        CHECK (aspect_ratio IN ('9:16', '1:1', '4:5', '16:9')),
    tracking_mode   TEXT NOT NULL DEFAULT 'x_only'
                        CHECK (tracking_mode IN ('x_only', 'dynamic_xy')),

    -- Results (populated when status = 'done')
    keyframes       JSONB,      -- [{time_s, offset_x, interpolation}]
    scene_cuts      JSONB,      -- [float, ...]  timestamps in seconds
    src_w           INT,
    src_h           INT,
    fps             FLOAT,
    duration_s      FLOAT,

    -- Error info
    error           TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reframe_jobs_user
    ON reframe_jobs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reframe_jobs_status
    ON reframe_jobs(status, created_at DESC);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION update_reframe_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reframe_jobs_updated_at ON reframe_jobs;
CREATE TRIGGER trg_reframe_jobs_updated_at
    BEFORE UPDATE ON reframe_jobs
    FOR EACH ROW EXECUTE FUNCTION update_reframe_jobs_updated_at();

-- ─── reframe_metadata ─────────────────────────────────────────────────────────
-- Populated by pipeline after clip export.
-- Read by editor via GET /reframe/metadata/{job_id}/{clip_id}

CREATE TABLE IF NOT EXISTS reframe_metadata (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           TEXT NOT NULL,   -- pipeline jobs.id
    clip_id          TEXT NOT NULL,   -- pipeline clip_id / UUID

    scene_cuts       JSONB NOT NULL DEFAULT '[]',   -- [float, ...]
    speaker_segments JSONB NOT NULL DEFAULT '[]',   -- [{speaker, start, end}]
    face_positions   JSONB NOT NULL DEFAULT '[]',   -- [{scene_start_s, scene_end_s, persons:[...]}]
    keyframes        JSONB NOT NULL DEFAULT '[]',   -- [{time_s, offset_x, interpolation}]

    src_w            INT   NOT NULL,
    src_h            INT   NOT NULL,
    fps              FLOAT NOT NULL,
    duration_s       FLOAT NOT NULL,

    strategy         TEXT NOT NULL DEFAULT 'podcast',
    aspect_ratio     TEXT NOT NULL DEFAULT '9:16',

    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reframe_meta_clip
    ON reframe_metadata(job_id, clip_id);

CREATE INDEX IF NOT EXISTS idx_reframe_meta_job
    ON reframe_metadata(job_id);
