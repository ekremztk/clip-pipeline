"""
Director Prompt Lab Tools — analyze prompt performance and suggest improvements.
Works with the director_prompt_lab table and pipeline results.
"""

from app.director.tools.database import _run_sql
from app.services.supabase_client import get_client


def analyze_prompt_performance(step: str = "s05", days: int = 30) -> dict:
    """
    Analyze how different prompt versions perform for a pipeline step.
    Compares pass rate, confidence, and cost across prompt versions.
    """
    try:
        client = get_client()

        # Get prompt lab entries for this step
        prompts = (client.table("director_prompt_lab")
                   .select("id,name,version,is_active,created_at")
                   .eq("step", step)
                   .order("version", desc=True)
                   .execute())

        if not prompts.data:
            return {"error": f"No prompt variants found for step {step}"}

        # Get pipeline performance for this step
        perf_rows = _run_sql("""
            SELECT
                DATE_TRUNC('week', p.created_at)::DATE AS week,
                COUNT(DISTINCT p.job_id) AS jobs,
                ROUND(AVG(COALESCE((p.token_usage->>'cost_usd')::FLOAT, 0))::NUMERIC, 4) AS avg_cost,
                ROUND(AVG(p.duration_ms)::NUMERIC, 0) AS avg_duration_ms
            FROM pipeline_audit_log p
            WHERE p.step_name ILIKE %s
              AND p.created_at > now() - interval '%s days'
            GROUP BY 1
            ORDER BY 1 DESC
        """, (f"%{step}%", days))

        # Get clip quality metrics per week (downstream effect of prompts)
        quality_rows = _run_sql("""
            SELECT
                DATE_TRUNC('week', c.created_at)::DATE AS week,
                COUNT(*) AS total_clips,
                COUNT(*) FILTER (WHERE c.quality_verdict IN ('pass','fixable')) AS pass_clips,
                ROUND(AVG(c.overall_confidence)::NUMERIC, 2) AS avg_confidence
            FROM clips c
            WHERE c.created_at > now() - interval '%s days'
            GROUP BY 1
            ORDER BY 1 DESC
        """, (days,))

        active_prompt = next((p for p in prompts.data if p.get("is_active")), None)

        return {
            "step": step,
            "prompt_versions": len(prompts.data),
            "active_prompt": active_prompt.get("name") if active_prompt else "default",
            "weekly_performance": perf_rows,
            "weekly_quality": quality_rows,
            "prompts": [
                {"name": p.get("name"), "version": p.get("version"),
                 "is_active": p.get("is_active"), "created_at": p.get("created_at")}
                for p in prompts.data[:10]
            ],
        }

    except Exception as e:
        return {"error": str(e)}


def suggest_prompt_improvement(step: str = "s05") -> dict:
    """
    Analyze current prompt performance and suggest specific improvements.
    Uses pass rate trends, common failure patterns, and content type analysis.
    """
    try:
        suggestions = []

        # Check pass rate by content type
        ct_rows = _run_sql("""
            SELECT
                content_type,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE quality_verdict IN ('pass','fixable')) AS passed,
                ROUND(AVG(overall_confidence)::NUMERIC, 2) AS avg_conf
            FROM clips
            WHERE created_at > now() - interval '30 days'
              AND content_type IS NOT NULL
            GROUP BY content_type
            HAVING COUNT(*) >= 3
            ORDER BY COUNT(*) FILTER (WHERE quality_verdict IN ('pass','fixable'))::FLOAT / COUNT(*) ASC
        """)

        weak_types = []
        strong_types = []
        for r in ct_rows:
            total = int(r.get("total") or 0)
            passed = int(r.get("passed") or 0)
            rate = passed / max(total, 1) * 100
            ct = r.get("content_type")
            if rate < 30:
                weak_types.append({"type": ct, "pass_rate": round(rate, 1), "count": total})
            elif rate > 60:
                strong_types.append({"type": ct, "pass_rate": round(rate, 1), "count": total})

        if weak_types:
            types_str = ", ".join(t["type"] for t in weak_types)
            suggestions.append({
                "area": "content_type_weakness",
                "suggestion": (
                    f"Zayif content type'lar: {types_str}. "
                    f"{'S05' if step == 's05' else 'S06'} prompt'unda bu tur iceriklerin "
                    f"tanimlanma/degerlendirme kriterlerini guclendir."
                ),
                "impact": "high",
                "weak_types": weak_types,
            })

        if strong_types:
            types_str = ", ".join(t["type"] for t in strong_types)
            suggestions.append({
                "area": "content_type_strength",
                "suggestion": (
                    f"Guclu content type'lar: {types_str}. "
                    f"Bu tur iceriklerin basarili pattern'leri prompt'a referans olarak eklenebilir."
                ),
                "impact": "medium",
                "strong_types": strong_types,
            })

        # Check confidence distribution
        conf_rows = _run_sql("""
            SELECT
                CASE
                    WHEN overall_confidence >= 8 THEN 'high'
                    WHEN overall_confidence >= 6 THEN 'medium'
                    ELSE 'low'
                END AS conf_bucket,
                COUNT(*) AS cnt,
                COUNT(*) FILTER (WHERE quality_verdict IN ('pass','fixable')) AS passed
            FROM clips
            WHERE created_at > now() - interval '30 days'
              AND overall_confidence IS NOT NULL
            GROUP BY 1
        """)

        for r in conf_rows:
            bucket = r.get("conf_bucket")
            cnt = int(r.get("cnt") or 0)
            passed = int(r.get("passed") or 0)
            if bucket == "medium" and cnt > 5:
                rate = passed / max(cnt, 1) * 100
                if rate < 50:
                    suggestions.append({
                        "area": "confidence_calibration",
                        "suggestion": (
                            f"Orta confidence (6-8) araligi %{rate:.0f} pass rate gosteriyor. "
                            f"S06 confidence skorlamasi daha katı/hassas olabilir — "
                            f"6-8 araligindaki kliplerin degerlendirme kriterleri daraltilmali."
                        ),
                        "impact": "medium",
                    })

        # Check average clip count per job
        avg_rows = _run_sql("""
            SELECT ROUND(AVG(clip_count)::NUMERIC, 1) AS avg_clips
            FROM (
                SELECT job_id, COUNT(*) AS clip_count
                FROM clips
                WHERE created_at > now() - interval '30 days'
                GROUP BY job_id
            ) sub
        """)
        avg_clips = float(avg_rows[0].get("avg_clips") or 0) if avg_rows else 0

        if avg_clips < 3:
            suggestions.append({
                "area": "discovery_volume",
                "suggestion": (
                    f"Job basina ortalama {avg_clips:.1f} klip — hedef 4-6. "
                    f"S05 prompt'unda minimum klip sayisi beklentisi arttirilmali "
                    f"veya daha genis zaman araliklari taranmali."
                ),
                "impact": "high",
            })
        elif avg_clips > 8:
            suggestions.append({
                "area": "discovery_precision",
                "suggestion": (
                    f"Job basina ortalama {avg_clips:.1f} klip — fazla olabilir. "
                    f"S05 kalite esigi yukseltilerek daha az ama daha kaliteli aday secimi yapilabilir."
                ),
                "impact": "medium",
            })

        if not suggestions:
            suggestions.append({
                "area": "general",
                "suggestion": "Belirgin bir zayiflik tespit edilemedi. Mevcut prompt performansi stabil gorunuyor.",
                "impact": "low",
            })

        return {
            "step": step,
            "suggestion_count": len(suggestions),
            "suggestions": suggestions,
            "avg_clips_per_job": avg_clips,
            "weak_content_types": weak_types,
            "strong_content_types": strong_types,
        }

    except Exception as e:
        return {"error": str(e)}
