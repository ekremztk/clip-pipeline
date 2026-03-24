"""Director database tools — read-only queries against Supabase."""

import psycopg2
from typing import Any
from app.config import settings
from app.services.supabase_client import get_client


def _run_sql(sql: str) -> list[dict]:
    """Execute a raw SQL SELECT query via psycopg2 (port 6543)."""
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def query_database(sql: str) -> list[dict]:
    """
    Run a SELECT query on Supabase. Only SELECT is allowed.
    Returns list of row dicts, max 200 rows.
    """
    try:
        sql = sql.strip()
        if not sql.upper().startswith("SELECT"):
            return [{"error": "Only SELECT queries are allowed"}]

        # Inject LIMIT safety
        if "LIMIT" not in sql.upper():
            sql = sql.rstrip(";") + " LIMIT 200"

        return _run_sql(sql)
    except Exception as e:
        print(f"[DirectorDB] query_database error: {e}")
        return [{"error": str(e)}]


def get_pipeline_stats(days: int = 7, channel_id: str | None = None) -> dict:
    """Pass rate, avg duration, error count, step-level breakdown."""
    try:
        channel_filter = f"AND channel_id = '{channel_id}'" if channel_id else ""
        sql = f"""
            SELECT
                COUNT(*) AS total_jobs,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                ROUND(AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/60)::NUMERIC, 1) AS avg_duration_min
            FROM jobs
            WHERE created_at > now() - interval '{days} days'
            {channel_filter}
        """
        rows = _run_sql(sql)
        stats = rows[0] if rows else {}

        # Step-level timings from audit log
        audit_sql = f"""
            SELECT step_name,
                   COUNT(*) AS runs,
                   ROUND(AVG(duration_ms)::NUMERIC/1000, 1) AS avg_duration_s,
                   COUNT(*) FILTER (WHERE success = false) AS errors
            FROM pipeline_audit_log
            WHERE created_at > now() - interval '{days} days'
            GROUP BY step_name
            ORDER BY step_name
        """
        try:
            step_rows = _run_sql(audit_sql)
        except Exception:
            step_rows = []

        return {
            "period_days": days,
            "channel_id": channel_id,
            "summary": stats,
            "steps": step_rows,
        }
    except Exception as e:
        print(f"[DirectorDB] get_pipeline_stats error: {e}")
        return {"error": str(e)}


def get_clip_analysis(job_id: str | None = None, days: int = 7) -> dict:
    """Score distribution, verdict breakdown, content type stats."""
    try:
        job_filter = f"AND job_id = '{job_id}'" if job_id else ""
        sql = f"""
            SELECT
                COUNT(*) AS total_clips,
                ROUND(AVG(overall_confidence)::NUMERIC, 2) AS avg_confidence,
                MIN(overall_confidence) AS min_confidence,
                MAX(overall_confidence) AS max_confidence,
                COUNT(*) FILTER (WHERE quality_verdict = 'pass') AS pass_count,
                COUNT(*) FILTER (WHERE quality_verdict = 'fixable') AS fixable_count,
                COUNT(*) FILTER (WHERE quality_verdict = 'fail') AS fail_count
            FROM clips
            WHERE created_at > now() - interval '{days} days'
            {job_filter}
        """
        rows = _run_sql(sql)
        return {"period_days": days, "job_id": job_id, "analysis": rows[0] if rows else {}}
    except Exception as e:
        print(f"[DirectorDB] get_clip_analysis error: {e}")
        return {"error": str(e)}


def get_channel_dna(channel_id: str) -> dict:
    """Retrieve channel DNA JSON for the given channel."""
    try:
        client = get_client()
        res = client.table("channels").select("*").eq("id", channel_id).single().execute()
        return res.data or {}
    except Exception as e:
        print(f"[DirectorDB] get_channel_dna error: {e}")
        return {"error": str(e)}


def get_recent_events(module: str | None = None, days: int = 7, limit: int = 50) -> list[dict]:
    """Fetch recent director events for a module."""
    try:
        mod_filter = f"AND module_name = '{module}'" if module else ""
        sql = f"""
            SELECT module_name, event_type, payload, session_id, channel_id, timestamp
            FROM director_events
            WHERE timestamp > now() - interval '{days} days'
            {mod_filter}
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        return _run_sql(sql)
    except Exception as e:
        print(f"[DirectorDB] get_recent_events error: {e}")
        return [{"error": str(e)}]
