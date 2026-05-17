-- Migration 012: Manual Provision / Last Editor job tracking.

CREATE TABLE IF NOT EXISTS provision_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    name TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'draft',
    variant_modes TEXT[] NOT NULL DEFAULT ARRAY['conservative', 'tight', 'loop'],
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    item_count INTEGER NOT NULL DEFAULT 0,
    completed_item_count INTEGER NOT NULL DEFAULT 0,
    selected_variant_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provision_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provision_job_id UUID NOT NULL REFERENCES provision_jobs(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    clip_id UUID REFERENCES clips(id) ON DELETE SET NULL,
    input_video_url TEXT NOT NULL,
    input_title TEXT,
    input_description TEXT,
    main_person TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    nova_transcript JSONB,
    audio_analysis JSONB,
    selected_variant_id UUID,
    edit_notes TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provision_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provision_item_id UUID NOT NULL REFERENCES provision_items(id) ON DELETE CASCADE,
    provision_job_id UUID NOT NULL REFERENCES provision_jobs(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    variant_mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    edit_plan JSONB,
    validation_report JSONB,
    output_video_url TEXT,
    duration_s DOUBLE PRECISION,
    score INTEGER,
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    feedback_note TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'provision_jobs_job_type_check'
    ) THEN
        ALTER TABLE provision_jobs
            ADD CONSTRAINT provision_jobs_job_type_check
            CHECK (job_type IN ('manual', 'stock'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'provision_jobs_status_check'
    ) THEN
        ALTER TABLE provision_jobs
            ADD CONSTRAINT provision_jobs_status_check
            CHECK (status IN ('draft', 'queued', 'processing', 'completed', 'failed', 'cancelled'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'provision_items_status_check'
    ) THEN
        ALTER TABLE provision_items
            ADD CONSTRAINT provision_items_status_check
            CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'skipped'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'provision_variants_status_check'
    ) THEN
        ALTER TABLE provision_variants
            ADD CONSTRAINT provision_variants_status_check
            CHECK (status IN ('queued', 'processing', 'completed', 'failed'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'provision_variants_review_status_check'
    ) THEN
        ALTER TABLE provision_variants
            ADD CONSTRAINT provision_variants_review_status_check
            CHECK (review_status IN ('unreviewed', 'selected', 'rejected', 'manual_fix', 'posted'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'provision_items_selected_variant_fk'
    ) THEN
        ALTER TABLE provision_items
            ADD CONSTRAINT provision_items_selected_variant_fk
            FOREIGN KEY (selected_variant_id) REFERENCES provision_variants(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_provision_jobs_channel_status
    ON provision_jobs(channel_id, user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_provision_items_job_status
    ON provision_items(provision_job_id, status, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_provision_items_clip
    ON provision_items(clip_id);

CREATE INDEX IF NOT EXISTS idx_provision_variants_item_status
    ON provision_variants(provision_item_id, status, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_provision_variants_review
    ON provision_variants(channel_id, user_id, review_status, created_at DESC);
