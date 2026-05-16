-- Migration 011: Track S08/S09/S10 completion on stock clip candidates.

ALTER TABLE stock_clip_candidates
    ADD COLUMN IF NOT EXISTS s08_completed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS s08_export_status TEXT,
    ADD COLUMN IF NOT EXISTS s08_landscape_url TEXT,
    ADD COLUMN IF NOT EXISTS s08_completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS s09_completed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS s09_reframe_status TEXT,
    ADD COLUMN IF NOT EXISTS s09_reframed_url TEXT,
    ADD COLUMN IF NOT EXISTS s09_completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS s09_error_message TEXT,
    ADD COLUMN IF NOT EXISTS s10_completed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS s10_caption_status TEXT,
    ADD COLUMN IF NOT EXISTS s10_captioned_url TEXT,
    ADD COLUMN IF NOT EXISTS s10_completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS s10_error_message TEXT;

UPDATE stock_clip_candidates scc
SET
    s08_export_status = CASE
        WHEN c.video_landscape_path IS NOT NULL THEN 'completed'
        ELSE scc.s08_export_status
    END,
    s08_completed = CASE
        WHEN c.video_landscape_path IS NOT NULL THEN TRUE
        ELSE scc.s08_completed
    END,
    s08_landscape_url = COALESCE(scc.s08_landscape_url, c.video_landscape_path, c.file_url),
    s08_completed_at = CASE
        WHEN c.video_landscape_path IS NOT NULL THEN COALESCE(scc.s08_completed_at, c.created_at, now())
        ELSE scc.s08_completed_at
    END,
    s09_reframe_status = CASE
        WHEN c.video_reframed_path IS NOT NULL THEN 'completed'
        ELSE scc.s09_reframe_status
    END,
    s09_completed = CASE
        WHEN c.video_reframed_path IS NOT NULL THEN TRUE
        ELSE scc.s09_completed
    END,
    s09_reframed_url = COALESCE(scc.s09_reframed_url, c.video_reframed_path),
    s09_completed_at = CASE
        WHEN c.video_reframed_path IS NOT NULL THEN COALESCE(scc.s09_completed_at, c.updated_at, c.created_at, now())
        ELSE scc.s09_completed_at
    END,
    s10_caption_status = CASE
        WHEN c.video_captioned_path IS NOT NULL THEN 'completed'
        ELSE scc.s10_caption_status
    END,
    s10_completed = CASE
        WHEN c.video_captioned_path IS NOT NULL THEN TRUE
        ELSE scc.s10_completed
    END,
    s10_captioned_url = COALESCE(scc.s10_captioned_url, c.video_captioned_path),
    s10_completed_at = CASE
        WHEN c.video_captioned_path IS NOT NULL THEN COALESCE(scc.s10_completed_at, c.updated_at, c.created_at, now())
        ELSE scc.s10_completed_at
    END,
    updated_at = now()
FROM clips c
WHERE c.stock_candidate_id = scc.id;

CREATE INDEX IF NOT EXISTS idx_stock_clip_candidates_stage_status
    ON stock_clip_candidates(channel_id, batch_id, s10_completed, s06_score DESC);
