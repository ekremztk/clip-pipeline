"""
Director Editor Intelligence — analyzes clip engagement in the editor.
Tracks which clips get opened, which get published, and patterns.
"""

from app.director.tools.database import _run_sql


def get_editor_engagement_stats(channel_id: str) -> dict:
    """Which clip types are most opened in the editor?"""
    try:
        rows = _run_sql("""
            SELECT payload->>'quality_verdict' AS verdict,
                   COUNT(*) AS open_count,
                   ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
            FROM director_cross_module_signals
            WHERE channel_id = %s AND event_type = 'clip_opened_in_editor'
              AND created_at > now() - interval '30 days'
            GROUP BY 1
        """, (channel_id,))
        return {"channel_id": channel_id, "period_days": 30, "engagement": rows}
    except Exception as e:
        return {"error": str(e)}


def get_clips_opened_but_not_published(channel_id: str) -> dict:
    """Clips opened in editor but never published — potential waste."""
    try:
        rows = _run_sql("""
            SELECT c.id, c.suggested_title, c.quality_verdict,
                   c.overall_confidence, c.content_type, c.created_at
            FROM clips c
            JOIN director_cross_module_signals s
              ON s.payload->>'clip_id' = c.id::text
            WHERE c.channel_id = %s
              AND s.event_type = 'clip_opened_in_editor'
              AND c.is_published IS NULL
              AND c.created_at > now() - interval '14 days'
            ORDER BY c.created_at DESC
        """, (channel_id,))
        return {
            "channel_id": channel_id,
            "count": len(rows),
            "clips": rows,
        }
    except Exception as e:
        return {"error": str(e)}


def get_editor_conversion_rate(channel_id: str) -> dict:
    """What percentage of opened clips get published?"""
    try:
        rows = _run_sql("""
            SELECT
                COUNT(DISTINCT s.payload->>'clip_id') AS opened,
                COUNT(DISTINCT CASE WHEN c.is_published = true
                    THEN s.payload->>'clip_id' END) AS published
            FROM director_cross_module_signals s
            LEFT JOIN clips c ON c.id::text = s.payload->>'clip_id'
            WHERE s.channel_id = %s
              AND s.event_type = 'clip_opened_in_editor'
              AND s.created_at > now() - interval '30 days'
        """, (channel_id,))
        if not rows:
            return {"error": "No data"}
        r = rows[0]
        opened = int(r.get("opened") or 0)
        published = int(r.get("published") or 0)
        rate = round(published / max(opened, 1) * 100, 1)
        return {
            "channel_id": channel_id,
            "opened": opened,
            "published": published,
            "conversion_rate_pct": rate,
            "period_days": 30,
        }
    except Exception as e:
        return {"error": str(e)}
