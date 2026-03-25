"""
Director 5-Dimension Scorer — comprehensive system health scoring.

Dimensions:
1. Technical Health (20p) — pipeline success rate + duration
2. AI Decision Quality (35p) — pass rate + confidence
3. Output Structural Quality (25p) — clips per job + content diversity
4. Learning & Adaptation (15p) — trend direction + feedback integration
5. Strategic Maturity (5p) — memory usage + proactive trigger coverage
"""

from app.director.tools.database import (
    get_pipeline_stats, get_clip_analysis, get_pass_rate_trend, _run_sql,
)


def calculate_scores(days: int = 30, channel_id: str | None = None) -> dict:
    """
    Calculate full 5-dimension score.
    Returns overall score (0-100) and per-dimension breakdown.
    """
    pipeline = get_pipeline_stats(days, channel_id)
    clips = get_clip_analysis(None, days)

    s = pipeline.get("summary") or {}
    total = int(s.get("total_jobs", 0) or 0)
    completed = int(s.get("completed", 0) or 0)
    ca = clips.get("analysis") or {}
    total_clips = int(ca.get("total_clips", 0) or 0)
    pass_count = int(ca.get("pass_count", 0) or 0)
    avg_conf = float(ca.get("avg_confidence", 0) or 0)

    if total == 0:
        return {
            "overall_score": None,
            "reason": "No pipeline data available",
            "dimensions": {},
        }

    d1 = _dim_technical_health(total, completed, s)
    d2 = _dim_ai_decision_quality(total_clips, pass_count, avg_conf)
    d3 = _dim_output_quality(total_clips, total, clips)
    d4 = _dim_learning_adaptation(total)
    d5 = _dim_strategic_maturity()

    overall = min(100, round(d1["score"] + d2["score"] + d3["score"] + d4["score"] + d5["score"]))

    return {
        "overall_score": overall,
        "dimensions": {
            "technical_health": d1,
            "ai_decision_quality": d2,
            "output_quality": d3,
            "learning_adaptation": d4,
            "strategic_maturity": d5,
        },
        "data_points": total,
        "period_days": days,
    }


def _dim_technical_health(total: int, completed: int, summary: dict) -> dict:
    """Dimension 1: Technical Health (max 20 points)."""
    success_rate = (completed / total * 100) if total > 0 else 0
    avg_dur = float(summary.get("avg_duration_min", 0) or 0)
    error_count = int(summary.get("failed", 0) or 0)

    # Success rate subscore (0-6)
    if success_rate >= 100:
        sr_score = 6
    elif success_rate >= 95:
        sr_score = 5
    elif success_rate >= 90:
        sr_score = 4
    elif success_rate >= 80:
        sr_score = 2
    else:
        sr_score = 0

    # Duration subscore (0-4)
    if avg_dur < 6:
        dur_score = 4
    elif avg_dur < 8:
        dur_score = 3
    elif avg_dur < 12:
        dur_score = 2
    else:
        dur_score = 0

    # Error penalty subscore (0-5)
    error_rate = error_count / max(total, 1) * 100
    if error_rate < 2:
        err_score = 5
    elif error_rate < 5:
        err_score = 4
    elif error_rate < 10:
        err_score = 2
    else:
        err_score = 0

    # Uptime bonus (fixed 5 — Railway is always up or all down)
    uptime_score = 5

    score = sr_score + dur_score + err_score + uptime_score
    return {
        "score": min(20, score),
        "max": 20,
        "breakdown": {
            "success_rate": {"value": round(success_rate, 1), "score": sr_score, "max": 6},
            "avg_duration_min": {"value": round(avg_dur, 1), "score": dur_score, "max": 4},
            "error_rate": {"value": round(error_rate, 1), "score": err_score, "max": 5},
            "uptime": {"score": uptime_score, "max": 5},
        },
    }


def _dim_ai_decision_quality(total_clips: int, pass_count: int, avg_conf: float) -> dict:
    """Dimension 2: AI Decision Quality (max 35 points).
    avg_conf is already on 0-10 scale (confidence*10 from DB).
    pass_count based on quality_status='passed'.
    Note: many clips don't have quality_status yet — treat as neutral, not fail.
    """
    pass_rate = (pass_count / total_clips * 100) if total_clips > 0 else 0

    # Pass rate subscore (0-15)
    if pass_rate > 50:
        pr_score = 15
    elif pass_rate > 40:
        pr_score = 12
    elif pass_rate > 35:
        pr_score = 10
    elif pass_rate > 25:
        pr_score = 6
    elif pass_rate > 15:
        pr_score = 3
    else:
        pr_score = 0

    # Confidence subscore (0-10)
    if avg_conf >= 8.0:
        cf_score = 10
    elif avg_conf >= 7.5:
        cf_score = 8
    elif avg_conf >= 7.0:
        cf_score = 6
    elif avg_conf >= 6.0:
        cf_score = 3
    else:
        cf_score = 0

    # User alignment subscore (0-10) — based on approval vs rejection ratio
    alignment_score = _get_user_alignment_score()

    score = pr_score + cf_score + alignment_score
    return {
        "score": min(35, score),
        "max": 35,
        "breakdown": {
            "pass_rate": {"value": round(pass_rate, 1), "score": pr_score, "max": 15},
            "avg_confidence": {"value": round(avg_conf, 2), "score": cf_score, "max": 10},
            "user_alignment": {"score": alignment_score, "max": 10},
        },
    }


def _dim_output_quality(total_clips: int, total_jobs: int, clips: dict) -> dict:
    """Dimension 3: Output Structural Quality (max 25 points)."""
    clips_per_job = total_clips / max(total_jobs, 1)

    # Clips per job subscore (0-10)
    if clips_per_job >= 5:
        cj_score = 10
    elif clips_per_job >= 4:
        cj_score = 8
    elif clips_per_job >= 3:
        cj_score = 6
    elif clips_per_job >= 2:
        cj_score = 4
    elif clips_per_job >= 1:
        cj_score = 2
    else:
        cj_score = 0

    # Content diversity subscore (0-8)
    diversity = _get_content_diversity()

    # Duration range subscore (0-7) — clips should be 30s-180s
    duration_score = _get_duration_range_score()

    score = cj_score + diversity + duration_score
    return {
        "score": min(25, score),
        "max": 25,
        "breakdown": {
            "clips_per_job": {"value": round(clips_per_job, 1), "score": cj_score, "max": 10},
            "content_diversity": {"score": diversity, "max": 8},
            "duration_range": {"score": duration_score, "max": 7},
        },
    }


def _dim_learning_adaptation(total_jobs: int) -> dict:
    """Dimension 4: Learning & Adaptation (max 15 points)."""
    if total_jobs < 20:
        return {
            "score": 7,
            "max": 15,
            "breakdown": {"note": "Not enough data (need 20+ jobs)", "trend": "neutral"},
        }

    # Trend direction subscore (0-8)
    try:
        trend = get_pass_rate_trend()
        trend_dir = trend.get("trend", "stable")
        if trend_dir == "improving":
            trend_score = 8
        elif trend_dir == "stable":
            trend_score = 5
        else:
            trend_score = 2
    except Exception:
        trend_dir = "unknown"
        trend_score = 4

    # Memory usage subscore (0-4) — Director is using memory to learn
    memory_score = _get_memory_learning_score()

    # Feedback loop subscore (0-3) — are recommendations being applied
    feedback_score = _get_feedback_loop_score()

    score = trend_score + memory_score + feedback_score
    return {
        "score": min(15, score),
        "max": 15,
        "breakdown": {
            "trend": {"direction": trend_dir, "score": trend_score, "max": 8},
            "memory_usage": {"score": memory_score, "max": 4},
            "feedback_loop": {"score": feedback_score, "max": 3},
        },
    }


def _dim_strategic_maturity(  ) -> dict:
    """Dimension 5: Strategic Maturity (max 5 points)."""
    score = 0

    # Has proactive triggers fired? (0-2)
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS cnt FROM director_events
            WHERE event_type = 'proactive_trigger'
              AND timestamp > now() - interval '30 days'
        """)
        trigger_count = int(rows[0].get("cnt", 0)) if rows else 0
        score += 2 if trigger_count > 0 else 0
    except Exception:
        pass

    # Has analysis been run recently? (0-2)
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS cnt FROM director_analyses
            WHERE timestamp > now() - interval '7 days'
        """)
        analysis_count = int(rows[0].get("cnt", 0)) if rows else 0
        score += 2 if analysis_count > 0 else 1
    except Exception:
        pass

    # Has decision journal entries? (0-1)
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS cnt FROM director_decision_journal
            WHERE created_at > now() - interval '30 days'
        """)
        journal_count = int(rows[0].get("cnt", 0)) if rows else 0
        score += 1 if journal_count > 0 else 0
    except Exception:
        pass

    return {
        "score": min(5, score),
        "max": 5,
        "breakdown": {"proactive_active": score >= 2, "analysis_recent": score >= 3},
    }


# ──── Helper subscores ────

def _get_user_alignment_score() -> int:
    """Score based on user approval/rejection ratio of clips (user_approved column)."""
    try:
        rows = _run_sql("""
            SELECT
                COUNT(*) FILTER (WHERE user_approved = true) AS approved,
                COUNT(*) FILTER (WHERE user_approved = false) AS rejected,
                COUNT(*) AS total
            FROM clips
            WHERE user_approved IS NOT NULL
              AND created_at > now() - interval '30 days'
        """)
        if not rows or not rows[0].get("total"):
            return 5  # neutral
        r = rows[0]
        total = int(r["total"])
        approved = int(r.get("approved") or 0)
        if total < 5:
            return 5
        approval_rate = approved / total * 100
        if approval_rate >= 80:
            return 10
        elif approval_rate >= 60:
            return 7
        elif approval_rate >= 40:
            return 5
        return 2
    except Exception:
        return 5


def _get_content_diversity() -> int:
    """Score based on how many content types are being produced."""
    try:
        rows = _run_sql("""
            SELECT COUNT(DISTINCT content_type) AS types
            FROM clips
            WHERE content_type IS NOT NULL
              AND created_at > now() - interval '30 days'
        """)
        types = int(rows[0].get("types", 0)) if rows else 0
        if types >= 5:
            return 8
        elif types >= 4:
            return 6
        elif types >= 3:
            return 4
        elif types >= 2:
            return 2
        return 0
    except Exception:
        return 3


def _get_duration_range_score() -> int:
    """Score based on clip durations falling in the ideal range."""
    try:
        rows = _run_sql("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE duration_s BETWEEN 30 AND 180) AS ideal_range
            FROM clips
            WHERE duration_s IS NOT NULL
              AND created_at > now() - interval '30 days'
        """)
        if not rows:
            return 3
        total = int(rows[0].get("total") or 0)
        ideal = int(rows[0].get("ideal_range") or 0)
        if total == 0:
            return 3
        pct = ideal / total * 100
        if pct >= 80:
            return 7
        elif pct >= 60:
            return 5
        elif pct >= 40:
            return 3
        return 1
    except Exception:
        return 3


def _get_memory_learning_score() -> int:
    """Score based on Director's memory usage for learning."""
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS cnt FROM director_memory
            WHERE type = 'learning'
              AND created_at > now() - interval '30 days'
        """)
        cnt = int(rows[0].get("cnt", 0)) if rows else 0
        if cnt >= 10:
            return 4
        elif cnt >= 5:
            return 3
        elif cnt >= 1:
            return 2
        return 0
    except Exception:
        return 1


def _get_feedback_loop_score() -> int:
    """Score based on recommendations being applied."""
    try:
        rows = _run_sql("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'applied') AS applied,
                COUNT(*) AS total
            FROM director_recommendations
            WHERE created_at > now() - interval '30 days'
        """)
        if not rows:
            return 1
        total = int(rows[0].get("total") or 0)
        applied = int(rows[0].get("applied") or 0)
        if total == 0:
            return 1
        rate = applied / total
        if rate >= 0.5:
            return 3
        elif rate >= 0.2:
            return 2
        return 1
    except Exception:
        return 1
