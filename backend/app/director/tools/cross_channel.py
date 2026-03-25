"""
Director Multi-Channel Cross Analysis — compare all channels and find patterns.
Identifies best/worst performers and generates cross-pollination suggestions.
"""

from app.director.tools.database import _run_sql


def cross_channel_analysis(days: int = 30) -> dict:
    """
    Compare all channels on key metrics: pass rate, cost, volume, content type distribution.
    Returns rankings and cross-pollination suggestions.
    """
    try:
        rows = _run_sql("""
            SELECT
                c.id AS channel_id,
                c.display_name AS channel_name,
                COUNT(DISTINCT j.id) AS job_count,
                COUNT(cl.id) AS total_clips,
                COUNT(cl.id) FILTER (WHERE cl.quality_verdict IN ('pass','fixable')) AS pass_clips,
                ROUND(AVG(cl.overall_confidence)::NUMERIC, 2) AS avg_confidence,
                ROUND(AVG(cl.duration_s)::NUMERIC, 1) AS avg_duration_s
            FROM channels c
            LEFT JOIN jobs j ON j.channel_id = c.id
                AND j.created_at > now() - interval '%s days'
            LEFT JOIN clips cl ON cl.job_id = j.id
            GROUP BY c.id, c.display_name
            HAVING COUNT(DISTINCT j.id) > 0
            ORDER BY COUNT(cl.id) DESC
        """, (days,))

        if not rows:
            return {"error": "No channel data found"}

        channels = []
        for r in rows:
            total = int(r.get("total_clips") or 0)
            passed = int(r.get("pass_clips") or 0)
            channels.append({
                "channel_id": r.get("channel_id"),
                "channel_name": r.get("channel_name"),
                "job_count": int(r.get("job_count") or 0),
                "total_clips": total,
                "pass_clips": passed,
                "pass_rate": round(passed / max(total, 1) * 100, 1),
                "avg_confidence": float(r.get("avg_confidence") or 0),
                "avg_duration_s": float(r.get("avg_duration_s") or 0),
            })

        # Cost per channel
        cost_rows = _run_sql("""
            SELECT
                j.channel_id,
                ROUND(SUM(COALESCE((p.token_usage->>'cost_usd')::FLOAT, 0))::NUMERIC, 4) AS total_cost,
                COUNT(DISTINCT j.id) AS jobs
            FROM jobs j
            JOIN pipeline_audit_log p ON p.job_id = j.id
            WHERE j.created_at > now() - interval '%s days'
              AND p.token_usage IS NOT NULL
            GROUP BY j.channel_id
        """, (days,))
        cost_map = {r["channel_id"]: {
            "total_cost": float(r.get("total_cost") or 0),
            "cost_per_job": round(float(r.get("total_cost") or 0) / max(int(r.get("jobs") or 1), 1), 4),
        } for r in cost_rows}

        for ch in channels:
            cost_info = cost_map.get(ch["channel_id"], {})
            ch["total_cost_usd"] = cost_info.get("total_cost", 0)
            ch["cost_per_job_usd"] = cost_info.get("cost_per_job", 0)

        # Content type distribution per channel
        ct_rows = _run_sql("""
            SELECT
                j.channel_id,
                cl.content_type,
                COUNT(*) AS cnt,
                COUNT(*) FILTER (WHERE cl.quality_verdict IN ('pass','fixable')) AS passed
            FROM clips cl
            JOIN jobs j ON j.id = cl.job_id
            WHERE j.created_at > now() - interval '%s days'
              AND cl.content_type IS NOT NULL
            GROUP BY j.channel_id, cl.content_type
            ORDER BY cnt DESC
        """, (days,))

        ct_map = {}
        for r in ct_rows:
            cid = r.get("channel_id")
            if cid not in ct_map:
                ct_map[cid] = []
            total = int(r.get("cnt") or 0)
            passed = int(r.get("passed") or 0)
            ct_map[cid].append({
                "content_type": r.get("content_type"),
                "count": total,
                "pass_rate": round(passed / max(total, 1) * 100, 1),
            })

        for ch in channels:
            ch["content_types"] = ct_map.get(ch["channel_id"], [])

        # Rankings
        by_pass_rate = sorted(channels, key=lambda x: x["pass_rate"], reverse=True)
        by_volume = sorted(channels, key=lambda x: x["total_clips"], reverse=True)
        by_efficiency = sorted(channels, key=lambda x: x["cost_per_job_usd"])

        # Generate suggestions
        suggestions = _generate_suggestions(channels, ct_map)

        return {
            "period_days": days,
            "total_channels": len(channels),
            "channels": channels,
            "rankings": {
                "by_pass_rate": [{"channel": c["channel_name"], "pass_rate": c["pass_rate"]} for c in by_pass_rate],
                "by_volume": [{"channel": c["channel_name"], "clips": c["total_clips"]} for c in by_volume],
                "by_cost_efficiency": [{"channel": c["channel_name"], "cost_per_job": c["cost_per_job_usd"]} for c in by_efficiency],
            },
            "suggestions": suggestions,
        }

    except Exception as e:
        return {"error": str(e)}


def _generate_suggestions(channels: list[dict], ct_map: dict) -> list[str]:
    """Generate cross-pollination suggestions based on channel comparison."""
    suggestions = []

    if len(channels) < 2:
        return ["Tek kanal var — karşılaştırma yapılamıyor."]

    # Find best and worst performers
    best = max(channels, key=lambda x: x["pass_rate"])
    worst = min(channels, key=lambda x: x["pass_rate"])

    if best["pass_rate"] - worst["pass_rate"] > 15:
        suggestions.append(
            f"'{best['channel_name']}' (%{best['pass_rate']} pass rate) en iyi performans gösteren kanal. "
            f"'{worst['channel_name']}' (%{worst['pass_rate']}) kanalının DNA'sı incelenmeli — "
            f"en iyi kanalın DNA pattern'leri referans alınabilir."
        )

    # Content type cross-pollination
    all_types = set()
    channel_types = {}
    for ch in channels:
        types = set(ct.get("content_type") for ct in ch.get("content_types", []))
        channel_types[ch["channel_id"]] = types
        all_types.update(types)

    for ch in channels:
        missing = all_types - channel_types.get(ch["channel_id"], set())
        if missing and len(missing) <= 3:
            suggestions.append(
                f"'{ch['channel_name']}' kanalında {', '.join(missing)} content type'ları yok — "
                f"diğer kanallarda başarılı, denemek faydalı olabilir."
            )

    # Cost outlier
    costs = [c["cost_per_job_usd"] for c in channels if c["cost_per_job_usd"] > 0]
    if costs:
        avg_cost = sum(costs) / len(costs)
        expensive = [c for c in channels if c["cost_per_job_usd"] > avg_cost * 1.5]
        for ch in expensive:
            suggestions.append(
                f"'{ch['channel_name']}' job başına ${ch['cost_per_job_usd']:.4f} harcıyor "
                f"(ortalama: ${avg_cost:.4f}). Video süresi veya retry sayısı kontrol edilmeli."
            )

    return suggestions
