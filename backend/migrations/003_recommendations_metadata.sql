-- Migration 003: Add description/impact/effort/metadata columns to director_recommendations
-- These align with the new Director API that writes recommendations programmatically.

ALTER TABLE director_recommendations
    ADD COLUMN IF NOT EXISTS description      TEXT,
    ADD COLUMN IF NOT EXISTS impact           TEXT,
    ADD COLUMN IF NOT EXISTS effort           TEXT,
    ADD COLUMN IF NOT EXISTS metadata         JSONB DEFAULT '{}'::jsonb;

-- Back-fill description from existing what+why columns
UPDATE director_recommendations
SET description = COALESCE(what, '') || ' — ' || COALESCE(why, '')
WHERE description IS NULL AND (what IS NOT NULL OR why IS NOT NULL);

-- Back-fill impact from impact_score
UPDATE director_recommendations
SET impact = CASE
    WHEN impact_score >= 0.7 THEN 'yüksek'
    WHEN impact_score >= 0.4 THEN 'orta'
    ELSE 'düşük'
END
WHERE impact IS NULL AND impact_score IS NOT NULL;
