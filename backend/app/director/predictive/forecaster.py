"""
Director Forecasting Engine — statistical projections.
No GPU required. Uses simple statistics for cost and volume predictions.
"""

import statistics
from datetime import datetime, timezone
from app.director.tools.database import _run_sql


def forecast_monthly_cost() -> dict:
    """Project end-of-month cost based on last 14 days spend rate."""
    try:
        rows = _run_sql("""
            SELECT
                DATE_TRUNC('day', created_at)::DATE AS date,
                SUM(COALESCE((token_usage->>'cost_usd')::FLOAT, 0)) AS daily_cost
            FROM pipeline_audit_log
            WHERE created_at > now() - interval '14 days'
              AND token_usage IS NOT NULL AND token_usage::text != '{}'
            GROUP BY 1
            ORDER BY 1
        """)

        if len(rows) < 3:
            return {"error": "Yeterli veri yok (minimum 3 gün gerekli)"}

        daily_costs = [float(r.get("daily_cost") or 0) for r in rows]
        avg_daily = statistics.mean(daily_costs)
        std_daily = statistics.stdev(daily_costs) if len(daily_costs) > 1 else 0

        now = datetime.now(timezone.utc)
        days_elapsed = min(now.day, len(rows))
        days_remaining = 30 - days_elapsed
        current_month_total = sum(daily_costs[-days_elapsed:]) if days_elapsed > 0 else 0
        projected_total = current_month_total + avg_daily * days_remaining

        railway_monthly = 5.0

        return {
            "gemini_cost": {
                "current_month_so_far": round(current_month_total, 2),
                "avg_daily": round(avg_daily, 4),
                "projected_month_end": round(projected_total, 2),
                "confidence_range": {
                    "low": round(projected_total - std_daily * days_remaining * 0.5, 2),
                    "high": round(projected_total + std_daily * days_remaining * 0.5, 2),
                },
            },
            "railway_cost": railway_monthly,
            "grand_total_projected": round(projected_total + railway_monthly, 2),
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
        }

    except Exception as e:
        return {"error": str(e)}


def forecast_pipeline_volume() -> dict:
    """Pipeline usage trend and next 30-day projection."""
    try:
        rows = _run_sql("""
            SELECT
                COUNT(*) FILTER (WHERE created_at > now() - interval '30 days') AS current_30,
                COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '60 days'
                                 AND now() - interval '30 days') AS previous_30,
                COUNT(*) FILTER (WHERE created_at > now() - interval '7 days') AS current_7
            FROM jobs
        """)
        if not rows:
            return {"error": "Veri yok"}

        r = rows[0]
        current_30 = int(r.get("current_30") or 0)
        previous_30 = int(r.get("previous_30") or 0)
        current_7 = int(r.get("current_7") or 0)
        growth_rate = ((current_30 - previous_30) / max(previous_30, 1)) * 100
        projected_next_30 = round(current_7 * 4.3)

        return {
            "last_30_days": current_30,
            "previous_30_days": previous_30,
            "last_7_days": current_7,
            "growth_rate_pct": round(growth_rate, 1),
            "trend": "artış" if growth_rate > 10 else "düşüş" if growth_rate < -10 else "stabil",
            "projected_next_30_days": projected_next_30,
            "projected_clips_next_30": round(projected_next_30 * 3.5),
        }

    except Exception as e:
        return {"error": str(e)}


def predict_failure_risk(video_duration_s: float | None = None,
                          channel_id: str | None = None) -> dict:
    """Predict pipeline failure risk for a new job."""
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'failed') AS failed
            FROM jobs WHERE created_at > now() - interval '90 days'
        """)
        if not rows:
            return {"risk": "bilinmiyor", "reason": "Yeterli veri yok"}

        r = rows[0]
        total = int(r.get("total") or 0)
        failed = int(r.get("failed") or 0)
        base_fail_rate = (failed / max(total, 1)) * 100
        risk_score = base_fail_rate
        risk_factors = []

        if video_duration_s and video_duration_s > 5400:
            risk_score += 30
            risk_factors.append(f"Video {video_duration_s/60:.0f} dakika — çok uzun, S05 timeout riski yüksek")
        elif video_duration_s and video_duration_s > 3600:
            risk_score += 15
            risk_factors.append(f"Video {video_duration_s/60:.0f} dakika — uzun videolarda timeout riski artıyor")

        if channel_id:
            ch_rows = _run_sql("""
                SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM jobs WHERE channel_id = %s AND created_at > now() - interval '30 days'
            """, (channel_id,))
            if ch_rows:
                ch_total = int(ch_rows[0].get("total") or 0)
                ch_failed = int(ch_rows[0].get("failed") or 0)
                if ch_total >= 3 and (ch_failed / ch_total * 100) > base_fail_rate + 10:
                    risk_score += 10
                    risk_factors.append(f"Bu kanal son 30 günde %{ch_failed/ch_total*100:.0f} fail rate")

        risk_level = (
            "düşük" if risk_score < 15 else "orta" if risk_score < 30
            else "yüksek" if risk_score < 50 else "çok yüksek"
        )
        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 1),
            "base_fail_rate": round(base_fail_rate, 1),
            "risk_factors": risk_factors,
            "recommendation": (
                "Normal şartlarda çalıştırılabilir." if risk_score < 15
                else "Dikkatli ol, logları takip et." if risk_score < 30
                else "Riskli — gece saatlerinde dene." if risk_score < 50
                else "Çok riskli — video'yu trim et veya farklı saatte dene."
            ),
        }

    except Exception as e:
        return {"error": str(e)}


def forecast_capacity() -> dict:
    """System capacity projection — DB table sizes and growth warnings."""
    try:
        rows = _run_sql("""
            SELECT
                (SELECT COUNT(*) FROM director_events) AS event_count,
                (SELECT COUNT(*) FROM director_memory) AS memory_count,
                (SELECT COUNT(*) FROM director_conversations) AS conversation_count,
                (SELECT COUNT(*) FROM director_recommendations) AS recommendation_count,
                (SELECT COUNT(*) FROM clips) AS total_clips,
                (SELECT COUNT(*) FROM jobs) AS total_jobs,
                (SELECT COUNT(*) FROM pipeline_audit_log) AS audit_log_count
        """)
        if not rows:
            return {"error": "Veri okunamadı"}

        r = rows[0]
        warnings = []
        if int(r.get("memory_count") or 0) > 500:
            warnings.append(f"director_memory {r['memory_count']} kayıt — temizlik düşünülmeli")
        if int(r.get("event_count") or 0) > 10000:
            warnings.append(f"director_events {r['event_count']} kayıt — arşivleme düşünülmeli")
        if int(r.get("audit_log_count") or 0) > 50000:
            warnings.append(f"pipeline_audit_log {r['audit_log_count']} kayıt — cleanup gerekli")

        return {
            "table_sizes": {k: int(v or 0) for k, v in r.items()},
            "warnings": warnings,
            "status": "healthy" if not warnings else "attention_needed",
        }

    except Exception as e:
        return {"error": str(e)}
