-- Migration 013: Step state for Provision / Last Editor processing.

ALTER TABLE provision_jobs
    ADD COLUMN IF NOT EXISTS current_step TEXT NOT NULL DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS current_step_number INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS progress_pct INTEGER NOT NULL DEFAULT 0;

ALTER TABLE provision_items
    ADD COLUMN IF NOT EXISTS current_step TEXT NOT NULL DEFAULT 'queued',
    ADD COLUMN IF NOT EXISTS current_step_number INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS progress_pct INTEGER NOT NULL DEFAULT 0;

ALTER TABLE provision_variants
    ADD COLUMN IF NOT EXISTS current_step TEXT NOT NULL DEFAULT 'queued',
    ADD COLUMN IF NOT EXISTS current_step_number INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS progress_pct INTEGER NOT NULL DEFAULT 0;

ALTER TABLE provision_items
    DROP CONSTRAINT IF EXISTS provision_items_status_check;

ALTER TABLE provision_items
    ADD CONSTRAINT provision_items_status_check
    CHECK (status IN ('queued', 'analyzing', 'planned', 'rendering', 'completed', 'failed', 'skipped'));

ALTER TABLE provision_variants
    DROP CONSTRAINT IF EXISTS provision_variants_status_check;

ALTER TABLE provision_variants
    ADD CONSTRAINT provision_variants_status_check
    CHECK (status IN ('queued', 'planning', 'planned', 'rendering', 'completed', 'failed'));
