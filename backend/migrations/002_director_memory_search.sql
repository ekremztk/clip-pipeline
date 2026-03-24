-- Vector similarity search for Director memory
-- Run this in Supabase SQL Editor after 001_director_tables.sql

CREATE OR REPLACE FUNCTION match_director_memory(
    query_embedding vector(768),
    match_count      int DEFAULT 5,
    filter_type      text DEFAULT NULL
)
RETURNS TABLE (
    id         uuid,
    type       text,
    content    text,
    tags       text[],
    source     text,
    created_at timestamptz,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        id,
        type,
        content,
        tags,
        source,
        created_at,
        1 - (embedding <=> query_embedding) AS similarity
    FROM director_memory
    WHERE
        (filter_type IS NULL OR type = filter_type)
        AND embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
