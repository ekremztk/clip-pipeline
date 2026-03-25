"""Director database tools — read-only queries against Supabase."""

import psycopg2
from psycopg2 import pool as pg_pool
import statistics
from typing import Any
from app.config import settings
from app.services.supabase_client import get_client

_connection_pool: pg_pool.SimpleConnectionPool | None = None


def _get_pool() -> pg_pool.SimpleConnectionPool:
    """Get or create the connection pool."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        _connection_pool = pg_pool.SimpleConnectionPool(
            minconn=1, maxconn=5,
            dsn=settings.DATABASE_URL,
            connect_timeout=5,
        )
    return _connection_pool


def _run_sql(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a raw SQL SELECT query via connection pool (port 6543)."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '10s'")
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return [dict(zip(cols, row)) for row in rows]
    finally:
        pool.putconn(conn)


DANGEROUS_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "TRUNCATE", "EXEC", "EXECUTE", "UNION",
]


def query_database(sql: str) -> list[dict]:
    """
    Run a SELECT query on Supabase. Only SELECT is allowed.
    Returns list of row dicts, max 200 rows.
    """
    try:
        sql = sql.strip()
        if not sql.upper().startswith("SELECT"):
            return [{"error": "Only SELECT queries are allowed"}]

        # SQL injection protection
        sql_upper = sql.upper()
        for kw in DANGEROUS_KEYWORDS:
            if kw in sql_upper:
                return [{"error": f"Forbidden keyword: {kw}"}]
        if "--" in sql:
            return [{"error": "SQL comments not allowed"}]
        if sql.count(";") > 0:
            return [{"error": "Multiple statements not allowed"}]

        # Inject LIMIT safety
        if "LIMIT" not in sql_upper:
            sql = sql.rstrip(";") + " LIMIT 200"

        return _run_sql(sql)
    except Exception as e:
        print(f"[DirectorDB] query_database error: {e}")
        return [{"error": str(e)}]


def get_pipeline_stats(days: int = 7, channel_id: str | None = None) -> dict:
    """Pass rate, avg duration, error count, step-level breakdown."""
    try:
        params = []
        channel_filter = ""
        if channel_id:
            channel_filter = "AND channel_id = %s"
            params.append(channel_id)
        sql = f"""
            SELECT
                COUNT(*) AS total_jobs,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                ROUND(AVG(
                    EXTRACT(EPOCH FROM (completed_at - started_at)) / 60
                ) FILTER (
                    WHERE status = 'completed'
                      AND started_at IS NOT NULL
                      AND completed_at IS NOT NULL
                )::NUMERIC, 1) AS avg_duration_min
            FROM jobs
            WHERE created_at > now() - interval '{days} days'
            {channel_filter}
        """
        rows = _run_sql(sql, tuple(params))
        stats = rows[0] if rows else {}

        # Step-level timings — new pipeline only (s01-s08)
        audit_sql = f"""
            SELECT step_name,
                   COUNT(*) AS runs,
                   ROUND(AVG(duration_ms)::NUMERIC/1000, 1) AS avg_duration_s,
                   COUNT(*) FILTER (WHERE status = 'failed' OR success = false) AS errors
            FROM pipeline_audit_log
            WHERE created_at > now() - interval '{days} days'
              AND step_name IN (
                's01_audio_extract','s02_transcribe','s03_speaker_id',
                's04_labeled_transcript','s05_unified_discovery',
                's06_batch_evaluation','s07_precision_cut','s08_export'
              )
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
        params = []
        job_filter = ""
        if job_id:
            job_filter = "AND job_id = %s"
            params.append(job_id)
        sql = f"""
            SELECT
                COUNT(*) AS total_clips,
                ROUND((AVG(confidence) * 10)::NUMERIC, 2) AS avg_confidence,
                ROUND((MIN(confidence) * 10)::NUMERIC, 2) AS min_confidence,
                ROUND((MAX(confidence) * 10)::NUMERIC, 2) AS max_confidence,
                ROUND(AVG(standalone_score)::NUMERIC, 2) AS avg_standalone_score,
                ROUND(AVG(hook_score)::NUMERIC, 2) AS avg_hook_score,
                COUNT(*) FILTER (WHERE quality_status = 'passed') AS pass_count,
                COUNT(*) FILTER (WHERE quality_status = 'fixable') AS fixable_count,
                COUNT(*) FILTER (WHERE quality_status NOT IN ('passed','fixable') AND quality_status IS NOT NULL) AS fail_count,
                COUNT(*) FILTER (WHERE quality_status IS NULL) AS pending_count
            FROM clips
            WHERE created_at > now() - interval '{days} days'
            {job_filter}
        """
        rows = _run_sql(sql, tuple(params))
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


def create_recommendation(
    module_name: str,
    title: str,
    description: str,
    priority: int = 3,
    impact: str = "orta",
    effort: str = "",
    what_it_solves: str = "",
    how_to_integrate: str = "",
    why_recommended: str = "",
) -> dict:
    """Write a new improvement recommendation to the director_recommendations table."""
    try:
        client = get_client()
        metadata = {}
        if what_it_solves:
            metadata["what_it_solves"] = what_it_solves
        if how_to_integrate:
            metadata["how_to_integrate"] = how_to_integrate
        if why_recommended:
            metadata["why_recommended"] = why_recommended

        res = client.table("director_recommendations").insert({
            "module_name": module_name,
            "title": title,
            "description": description,
            "priority": priority,
            "impact": impact,
            "effort": effort,
            "status": "pending",
            "metadata": metadata if metadata else None,
        }).execute()
        created = res.data[0] if res.data else {}
        return {"ok": True, "id": created.get("id"), "title": title}
    except Exception as e:
        print(f"[DirectorDB] create_recommendation error: {e}")
        return {"error": str(e)}


def get_cost_per_job(days: int = 30) -> list[dict]:
    """Per-job cost aggregation from pipeline_audit_log.token_usage."""
    try:
        sql = f"""
            SELECT
                job_id,
                SUM(COALESCE((token_usage->>'cost_usd')::FLOAT, 0))      AS total_cost_usd,
                SUM(COALESCE((token_usage->>'input_tokens')::INT, 0))     AS input_tokens,
                SUM(COALESCE((token_usage->>'output_tokens')::INT, 0))    AS output_tokens,
                MAX(created_at)                                            AS last_step_at
            FROM pipeline_audit_log
            WHERE created_at > now() - interval '{days} days'
              AND token_usage IS NOT NULL
              AND token_usage::text != '{{}}'
            GROUP BY job_id
            ORDER BY last_step_at DESC
        """
        return _run_sql(sql)
    except Exception as e:
        print(f"[DirectorDB] get_cost_per_job error: {e}")
        return []


def get_cost_breakdown(days: int = 30, per: str = "day") -> dict:
    """Aggregated cost breakdown. per: 'day' | 'step' | 'job'."""
    try:
        if per == "day":
            sql = f"""
                SELECT
                    DATE_TRUNC('day', created_at)::DATE AS date,
                    SUM(COALESCE((token_usage->>'cost_usd')::FLOAT, 0)) AS cost_usd,
                    SUM(COALESCE((token_usage->>'input_tokens')::INT, 0)) AS input_tokens,
                    SUM(COALESCE((token_usage->>'output_tokens')::INT, 0)) AS output_tokens
                FROM pipeline_audit_log
                WHERE created_at > now() - interval '{days} days'
                  AND token_usage IS NOT NULL AND token_usage::text != '{{}}'
                GROUP BY 1 ORDER BY 1 DESC
            """
        elif per == "step":
            sql = f"""
                SELECT
                    step_name,
                    COUNT(DISTINCT job_id)                                  AS job_count,
                    SUM(COALESCE((token_usage->>'cost_usd')::FLOAT, 0))     AS total_cost_usd,
                    ROUND(AVG(COALESCE((token_usage->>'cost_usd')::FLOAT, 0))::NUMERIC, 6) AS avg_cost_usd
                FROM pipeline_audit_log
                WHERE created_at > now() - interval '{days} days'
                  AND token_usage IS NOT NULL AND token_usage::text != '{{}}'
                GROUP BY step_name ORDER BY total_cost_usd DESC
            """
        else:  # per == "job"
            sql = f"""
                SELECT
                    job_id,
                    SUM(COALESCE((token_usage->>'cost_usd')::FLOAT, 0)) AS total_cost_usd,
                    SUM(COALESCE((token_usage->>'input_tokens')::INT, 0)) AS input_tokens,
                    SUM(COALESCE((token_usage->>'output_tokens')::INT, 0)) AS output_tokens,
                    MAX(created_at) AS last_step_at
                FROM pipeline_audit_log
                WHERE created_at > now() - interval '{days} days'
                  AND token_usage IS NOT NULL AND token_usage::text != '{{}}'
                GROUP BY job_id ORDER BY last_step_at DESC LIMIT 50
            """
        rows = _run_sql(sql)
        total = sum(float(r.get("total_cost_usd") or r.get("cost_usd") or 0) for r in rows)
        return {"period_days": days, "per": per, "total_cost_usd": round(total, 4), "rows": rows}
    except Exception as e:
        print(f"[DirectorDB] get_cost_breakdown error: {e}")
        return {"error": str(e)}


def detect_cost_anomalies(threshold_sigma: float = 2.0) -> list[dict]:
    """2σ anomaly detection on per-job costs over last 30 days."""
    try:
        rows = get_cost_per_job(30)
        costs = [float(r.get("total_cost_usd") or 0) for r in rows if r.get("total_cost_usd")]
        if len(costs) < 3:
            return []
        mean = statistics.mean(costs)
        std = statistics.stdev(costs)
        if std == 0:
            return []
        anomalies = []
        for r in rows:
            cost = float(r.get("total_cost_usd") or 0)
            z = (cost - mean) / std
            if abs(z) > threshold_sigma:
                anomalies.append({
                    **r,
                    "z_score": round(z, 2),
                    "anomaly_type": "spike" if z > 0 else "drop",
                    "mean_usd": round(mean, 4),
                    "std_usd": round(std, 4),
                })
        return anomalies
    except Exception as e:
        print(f"[DirectorDB] detect_cost_anomalies error: {e}")
        return []


def get_pass_rate_trend(channel_id: str | None = None) -> dict:
    """Compare pass rate: last 30 days vs previous 30 days. Used for B4 scoring."""
    try:
        params = []
        channel_filter = ""
        if channel_id:
            channel_filter = "AND channel_id = %s"
            params.append(channel_id)
        sql = f"""
            SELECT
                COUNT(*) FILTER (WHERE created_at > now() - interval '30 days') AS total_current,
                COUNT(*) FILTER (WHERE created_at > now() - interval '30 days'
                                   AND quality_verdict IN ('pass','fixable'))    AS pass_current,
                COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '60 days'
                                                        AND now() - interval '30 days') AS total_prev,
                COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '60 days'
                                                        AND now() - interval '30 days'
                                   AND quality_verdict IN ('pass','fixable'))    AS pass_prev
            FROM clips
            WHERE 1=1 {channel_filter}
        """
        rows = _run_sql(sql, tuple(params))
        if not rows:
            return {}
        r = rows[0]
        tc, pc = int(r.get("total_current") or 0), int(r.get("pass_current") or 0)
        tp, pp = int(r.get("total_prev") or 0), int(r.get("pass_prev") or 0)
        rate_current = (pc / tc * 100) if tc > 0 else None
        rate_prev = (pp / tp * 100) if tp > 0 else None
        delta = round(rate_current - rate_prev, 1) if (rate_current is not None and rate_prev is not None) else None
        return {
            "rate_current": round(rate_current, 1) if rate_current is not None else None,
            "rate_prev": round(rate_prev, 1) if rate_prev is not None else None,
            "delta": delta,
            "trend": "improving" if (delta and delta > 3) else "declining" if (delta and delta < -3) else "stable",
        }
    except Exception as e:
        print(f"[DirectorDB] get_pass_rate_trend error: {e}")
        return {}


def get_b4_b5_data() -> dict:
    """Fetch real data for Boyut 4 (Learning) and Boyut 5 (Strategic) scoring."""
    try:
        client = get_client()

        # B4-1: Pass rate trend (6p)
        trend = get_pass_rate_trend()
        trend_dir = trend.get("trend", "stable")
        trend_score = 6 if trend_dir == "improving" else 2 if trend_dir == "declining" else 4

        # B4-2: Channel DNA freshness (4p)
        try:
            channels_res = client.table("channels").select("updated_at").execute()
            dna_score = 0
            if channels_res.data:
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                # Score based on most recently updated channel
                for ch in channels_res.data:
                    updated_str = ch.get("updated_at")
                    if updated_str:
                        try:
                            updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                            days_old = (now - updated_at).days
                            ch_score = 4 if days_old <= 30 else 2 if days_old <= 90 else 0
                            dna_score = max(dna_score, ch_score)
                        except Exception:
                            pass
        except Exception:
            dna_score = 2  # neutral

        b4 = trend_score + dna_score + 2  # +2 base (feedback signal exists)
        b4 = min(15, b4)

        # B5-1: Open critical recommendations (3p)
        try:
            crit_res = (client.table("director_recommendations")
                        .select("id", count="exact")
                        .eq("status", "pending")
                        .lte("priority", 2)
                        .execute())
            open_criticals = crit_res.count or 0
            crit_score = 3 if open_criticals == 0 else 2 if open_criticals <= 2 else 0
        except Exception:
            crit_score = 2

        # B5-2: Recommendation application rate (2p)
        try:
            total_res = (client.table("director_recommendations")
                         .select("status", count="exact").execute())
            applied_res = (client.table("director_recommendations")
                           .select("id", count="exact")
                           .in_("status", ["applied", "dismissed"]).execute())
            total_recs = total_res.count or 0
            applied_recs = applied_res.count or 0
            apply_rate = (applied_recs / total_recs * 100) if total_recs > 0 else None
            apply_score = 2 if (apply_rate and apply_rate >= 60) else 1 if (apply_rate and apply_rate >= 30) else 0
        except Exception:
            apply_score = 1

        b5 = crit_score + apply_score

        return {
            "b4": b4, "b5": b5,
            "b4_detail": {"trend": trend_score, "dna_freshness": dna_score, "trend_direction": trend_dir},
            "b5_detail": {"open_criticals": open_criticals if "open_criticals" in dir() else 0,
                          "crit_score": crit_score, "apply_score": apply_score},
        }
    except Exception as e:
        print(f"[DirectorDB] get_b4_b5_data error: {e}")
        return {"b4": 8, "b5": 3, "b4_detail": {}, "b5_detail": {}}  # neutral fallback


def compare_channels(channel_a: str, channel_b: str, metric: str = "pass_rate") -> dict:
    """
    Compare two channels on a given metric.
    metric: 'pass_rate' | 'avg_confidence' | 'clip_count' | 'cost'
    Returns side-by-side comparison plus a suggestion.
    """
    try:
        allowed = {"pass_rate", "avg_confidence", "clip_count", "cost"}
        if metric not in allowed:
            return {"error": f"Unknown metric '{metric}'. Allowed: {', '.join(allowed)}"}

        if metric in ("pass_rate", "avg_confidence", "clip_count"):
            sql = f"""
                SELECT
                    channel_id,
                    COUNT(*)                                                         AS total_clips,
                    COUNT(*) FILTER (WHERE quality_verdict IN ('pass','fixable'))    AS passed,
                    ROUND(AVG(overall_confidence)::NUMERIC, 2)                       AS avg_confidence
                FROM clips
                WHERE channel_id IN (%s, %s)
                  AND created_at > now() - interval '30 days'
                GROUP BY channel_id
            """
            rows = _run_sql(sql, (channel_a, channel_b))
            data: dict = {}
            for r in rows:
                cid = r.get("channel_id")
                total = int(r.get("total_clips") or 0)
                passed = int(r.get("passed") or 0)
                data[cid] = {
                    "total_clips": total,
                    "passed": passed,
                    "pass_rate": round(passed / total * 100, 1) if total > 0 else None,
                    "avg_confidence": float(r.get("avg_confidence") or 0),
                }
        else:  # cost
            sql = f"""
                SELECT
                    j.channel_id,
                    ROUND(SUM(COALESCE((pal.token_usage->>'cost_usd')::FLOAT, 0))::NUMERIC, 4) AS total_cost_usd,
                    COUNT(DISTINCT j.id) AS job_count
                FROM pipeline_audit_log pal
                JOIN jobs j ON j.id = pal.job_id
                WHERE j.channel_id IN (%s, %s)
                  AND pal.created_at > now() - interval '30 days'
                GROUP BY j.channel_id
            """
            rows = _run_sql(sql, (channel_a, channel_b))
            data = {}
            for r in rows:
                cid = r.get("channel_id")
                data[cid] = {
                    "total_cost_usd": float(r.get("total_cost_usd") or 0),
                    "job_count": int(r.get("job_count") or 0),
                }

        a_data = data.get(channel_a, {})
        b_data = data.get(channel_b, {})

        # Build suggestion
        suggestion = None
        if metric == "pass_rate":
            a_rate = a_data.get("pass_rate")
            b_rate = b_data.get("pass_rate")
            if a_rate is not None and b_rate is not None:
                winner = channel_a if a_rate >= b_rate else channel_b
                loser = channel_b if winner == channel_a else channel_a
                diff = abs(a_rate - b_rate)
                if diff >= 10:
                    suggestion = (
                        f"Channel '{winner}' has {diff:.1f}pp higher pass rate. "
                        f"Inspect '{loser}' channel DNA for patterns used by '{winner}'."
                    )

        return {
            "metric": metric,
            "period_days": 30,
            channel_a: a_data,
            channel_b: b_data,
            "suggestion": suggestion,
        }
    except Exception as e:
        print(f"[DirectorDB] compare_channels error: {e}")
        return {"error": str(e)}


def get_recent_events(module: str | None = None, days: int = 7, limit: int = 50) -> list[dict]:
    """Fetch recent director events for a module."""
    try:
        params = []
        mod_filter = ""
        if module:
            mod_filter = "AND module_name = %s"
            params.append(module)
        sql = f"""
            SELECT module_name, event_type, payload, session_id, channel_id, timestamp
            FROM director_events
            WHERE timestamp > now() - interval '{days} days'
            {mod_filter}
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        return _run_sql(sql, tuple(params))
    except Exception as e:
        print(f"[DirectorDB] get_recent_events error: {e}")
        return [{"error": str(e)}]
