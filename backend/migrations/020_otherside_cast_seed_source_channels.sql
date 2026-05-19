-- Migration 020: Seed OtherSide Cast source channels for the first stock bench.

INSERT INTO otherside_cast_source_channels (
    channel_name,
    handle,
    active,
    notes
)
VALUES
    (
        'The Tonight Show Starring Jimmy Fallon',
        '@fallontonight',
        true,
        'Primary US source for celebrity interview clips.'
    ),
    (
        'Jimmy Kimmel Live',
        '@JimmyKimmelLive',
        true,
        'Primary US source with strong female celebrity inventory; 720p clips rely on the S08.5 upscale gate before reframe.'
    ),
    (
        'The Late Show with Stephen Colbert',
        '@ColbertLateShow',
        true,
        'Primary US source for polished A-list interview clips.'
    ),
    (
        'Late Night with Seth Meyers',
        '@LateNightSeth',
        true,
        'Primary US source for clean interview clips and recent celebrity inventory.'
    )
ON CONFLICT (handle) DO UPDATE
SET channel_name = EXCLUDED.channel_name,
    active = EXCLUDED.active,
    notes = EXCLUDED.notes;
