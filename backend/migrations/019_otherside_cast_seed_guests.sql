-- Migration 019: Seed OtherSide Cast female celebrity guest pool.

INSERT INTO otherside_cast_guests (guest_name, score, category, notes)
VALUES
    ('Nicole Kidman', 100, 'evergreen', 'Proven OtherSide performer; weird personal stories and celebrity comedy moments.'),
    ('Taylor Swift', 99, 'evergreen', 'Proven OtherSide performer; high recognition and strong pop culture pull.'),
    ('Mila Kunis', 98, 'evergreen', 'Proven OtherSide performer; short funny stories and language/family bits.'),
    ('Jennifer Lawrence', 97, 'evergreen', 'High-energy interview style with strong awkward/funny story potential.'),
    ('Zendaya', 96, 'evergreen', 'High recognition; strong US audience pull and Spider-Man/fashion stories.'),
    ('Margaret Qualley', 95, 'evergreen', 'Proven OtherSide performer; quirky Hollywood story fit.'),
    ('Ariana Grande', 94, 'evergreen', 'High recognition and strong talk show clip demand.'),
    ('Selena Gomez', 93, 'evergreen', 'High recognition; personal/funny interview moments work well.'),
    ('Billie Eilish', 92, 'evergreen', 'High recognition; awkward/funny celebrity moments and fan stories.'),
    ('Margot Robbie', 91, 'evergreen', 'High recognition; talk show stories and co-star dynamics.')
ON CONFLICT (guest_name) DO UPDATE
SET score = EXCLUDED.score,
    category = EXCLUDED.category,
    notes = EXCLUDED.notes,
    active = true,
    updated_at = now();

DELETE FROM otherside_cast_guests
WHERE guest_name NOT IN (
    'Nicole Kidman',
    'Taylor Swift',
    'Mila Kunis',
    'Jennifer Lawrence',
    'Zendaya',
    'Margaret Qualley',
    'Ariana Grande',
    'Selena Gomez',
    'Billie Eilish',
    'Margot Robbie'
);
