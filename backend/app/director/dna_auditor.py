"""
Director Channel DNA Auditor — 6-point health check.

Checks: freshness, consistency, performance reflection,
specificity, hook style, duration fit.
"""

from datetime import datetime, timezone
from app.services.supabase_client import get_client
from app.director.tools.database import _run_sql


def audit_channel_dna(channel_id: str) -> dict:
    """
    Run a 6-point health audit on channel DNA.
    Returns: score (0-100), checks list, issues list, suggestions list.
    """
    try:
        client = get_client()
        res = client.table("channels").select(
            "id,name,updated_at,channel_dna"
        ).eq("id", channel_id).single().execute()

        if not res.data:
            return {"error": f"Channel {channel_id} not found"}

        ch = res.data
        dna = ch.get("channel_dna") or {}
        name = ch.get("name", channel_id)

        checks = []
        issues = []
        suggestions = []
        total_score = 0
        max_score = 0

        # ─────────────────────────────────────
        # CHECK 1: Freshness (20 pts)
        # ─────────────────────────────────────
        max_score += 20
        updated_str = ch.get("updated_at")
        days_old = None
        if updated_str:
            try:
                updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                days_old = (datetime.now(timezone.utc) - updated_at).days
            except Exception:
                pass

        ref_clips = len(dna.get("reference_clips", []))

        if days_old is not None and days_old <= 30 and ref_clips >= 5:
            pts = 20
        elif days_old is not None and days_old <= 90 and ref_clips >= 3:
            pts = 12
        elif days_old is not None and days_old <= 90:
            pts = 8
        else:
            pts = 0

        total_score += pts
        checks.append({
            "name": "freshness",
            "score": pts,
            "max": 20,
            "detail": f"DNA last updated {days_old} days ago, {ref_clips} reference clips",
        })
        if pts < 12:
            issues.append(f"DNA is stale ({days_old} days old, {ref_clips} reference clips)")
            suggestions.append("Regenerate DNA from recent successful clips (last 30 days)")

        # ─────────────────────────────────────
        # CHECK 2: Consistency — do/dont conflict (20 pts)
        # ─────────────────────────────────────
        max_score += 20
        do_list = dna.get("do_list") or []
        dont_list = dna.get("dont_list") or []

        # Look for obvious keyword overlaps
        do_words = set(w.lower() for item in do_list for w in str(item).split())
        dont_words = set(w.lower() for item in dont_list for w in str(item).split())
        # Meaningful overlap = shared non-stopwords
        stopwords = {"the", "a", "an", "and", "or", "in", "of", "to", "is", "be", "with", "for"}
        overlap = (do_words & dont_words) - stopwords

        if len(do_list) >= 3 and len(dont_list) >= 3 and len(overlap) <= 2:
            pts = 20
        elif len(do_list) >= 2 and len(dont_list) >= 2:
            pts = 12
        else:
            pts = 4

        total_score += pts
        checks.append({
            "name": "consistency",
            "score": pts,
            "max": 20,
            "detail": f"{len(do_list)} do rules, {len(dont_list)} dont rules, {len(overlap)} conflicting keywords",
        })
        if pts < 12:
            issues.append(f"DNA do/dont lists are sparse or conflicting")
            suggestions.append("Add at least 3 specific do rules and 3 dont rules with no contradictions")

        # ─────────────────────────────────────
        # CHECK 3: Performance reflection (20 pts)
        # ─────────────────────────────────────
        max_score += 20
        try:
            sql = f"""
                SELECT
                    quality_verdict,
                    COUNT(*) AS cnt
                FROM clips
                WHERE channel_id = '{channel_id}'
                  AND created_at > now() - interval '30 days'
                GROUP BY quality_verdict
            """
            rows = _run_sql(sql)
            verdict_map = {r["quality_verdict"]: int(r["cnt"]) for r in rows if r.get("quality_verdict")}
            total_clips = sum(verdict_map.values())
            passed = verdict_map.get("pass", 0) + verdict_map.get("fixable", 0)
            pass_rate = (passed / total_clips * 100) if total_clips >= 5 else None
        except Exception:
            pass_rate = None
            total_clips = 0

        if pass_rate is not None and pass_rate >= 50:
            pts = 20
        elif pass_rate is not None and pass_rate >= 30:
            pts = 12
        elif total_clips >= 5:
            pts = 4
        else:
            pts = 10  # neutral — not enough data

        total_score += pts
        checks.append({
            "name": "performance_reflection",
            "score": pts,
            "max": 20,
            "detail": f"Last 30d: {total_clips} clips, {pass_rate:.1f}% pass rate" if pass_rate is not None else "Not enough data",
        })
        if pass_rate is not None and pass_rate < 30:
            issues.append(f"Low pass rate ({pass_rate:.1f}%) suggests DNA doesn't match actual content well")
            suggestions.append("Review DNA criteria against recent failed clips — loosen or update no_go_zones")

        # ─────────────────────────────────────
        # CHECK 4: Specificity (15 pts)
        # ─────────────────────────────────────
        max_score += 15
        content_types = dna.get("content_types") or dna.get("preferred_content_types") or []
        tone = dna.get("tone") or ""
        target_audience = dna.get("target_audience") or ""

        specificity_score = 0
        if len(content_types) >= 2:
            specificity_score += 5
        if len(str(tone)) > 20:
            specificity_score += 5
        if len(str(target_audience)) > 20:
            specificity_score += 5

        pts = specificity_score
        total_score += pts
        checks.append({
            "name": "specificity",
            "score": pts,
            "max": 15,
            "detail": f"{len(content_types)} content types, tone len={len(str(tone))}, audience len={len(str(target_audience))}",
        })
        if pts < 10:
            issues.append("DNA lacks specificity: missing content_types, tone, or target_audience")
            suggestions.append("Add specific content_types list, describe tone in detail, define target_audience")

        # ─────────────────────────────────────
        # CHECK 5: Hook style guidance (15 pts)
        # ─────────────────────────────────────
        max_score += 15
        hook_style = dna.get("hook_style") or dna.get("hook_patterns") or []
        hook_examples = dna.get("hook_examples") or []

        if (len(hook_style) >= 2 or len(str(hook_style)) > 30) and len(hook_examples) >= 1:
            pts = 15
        elif len(hook_style) >= 1 or len(str(hook_style)) > 10:
            pts = 8
        else:
            pts = 0

        total_score += pts
        checks.append({
            "name": "hook_style",
            "score": pts,
            "max": 15,
            "detail": f"hook_style={bool(hook_style)}, hook_examples count={len(hook_examples)}",
        })
        if pts < 8:
            issues.append("No hook style guidance in DNA")
            suggestions.append("Add hook_style with 2+ patterns and at least 1 hook_example from a successful clip")

        # ─────────────────────────────────────
        # CHECK 6: Duration fit (10 pts)
        # ─────────────────────────────────────
        max_score += 10
        min_duration = dna.get("min_duration") or dna.get("min_clip_duration")
        max_duration = dna.get("max_duration") or dna.get("max_clip_duration")

        if min_duration is not None and max_duration is not None:
            try:
                mn, mx = float(min_duration), float(max_duration)
                if 15 <= mn <= 120 and mn < mx <= 600:
                    pts = 10
                else:
                    pts = 5
                    issues.append(f"Duration range seems unusual: {mn}s - {mx}s")
                    suggestions.append("Set min_duration 30-60s and max_duration 90-300s for typical short-form clips")
            except Exception:
                pts = 5
        else:
            pts = 0
            issues.append("No duration guidance in DNA")
            suggestions.append("Add min_duration and max_duration to focus clip discovery")

        total_score += pts
        checks.append({
            "name": "duration_fit",
            "score": pts,
            "max": 10,
            "detail": f"min={min_duration}, max={max_duration}",
        })

        # ─────────────────────────────────────
        # Final
        # ─────────────────────────────────────
        health_pct = round(total_score / max_score * 100) if max_score > 0 else 0
        health_label = "healthy" if health_pct >= 75 else "needs_attention" if health_pct >= 50 else "critical"

        return {
            "channel_id": channel_id,
            "channel_name": name,
            "health_score": health_pct,
            "health_label": health_label,
            "total_points": total_score,
            "max_points": max_score,
            "checks": checks,
            "issues": issues,
            "suggestions": suggestions,
            "days_since_update": days_old,
            "reference_clips": ref_clips,
        }
    except Exception as e:
        print(f"[DNAAuditor] audit_channel_dna error: {e}")
        return {"error": str(e)}
