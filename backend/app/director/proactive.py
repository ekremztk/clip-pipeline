"""
Director Proactive Triggers — rule-based system health checks.

Called after every pipeline completion and hourly by the scheduler.
Each trigger writes a director_recommendation and/or a director_event
when its condition is met. Never raises — all errors are caught silently.
"""

import statistics
from datetime import datetime, timezone, timedelta
from app.services.supabase_client import get_client
from app.director.tools.database import _run_sql
from app.director.events import director_events


def _already_triggered_recently(trigger_name: str, hours: int = 24) -> bool:
    """Check if this trigger fired within the last N hours to avoid spam."""
    try:
        sql = f"""
            SELECT id FROM director_events
            WHERE event_type = 'proactive_trigger'
              AND payload->>'trigger' = '{trigger_name}'
              AND timestamp > now() - interval '{hours} hours'
            LIMIT 1
        """
        rows = _run_sql(sql)
        return len(rows) > 0
    except Exception:
        return False


def _emit_trigger(trigger_name: str, message: str, payload: dict,
                  channel_id: str | None = None) -> None:
    """Emit a proactive_trigger event."""
    director_events.emit_sync(
        module="director",
        event="proactive_trigger",
        payload={"trigger": trigger_name, "message": message, **payload},
        channel_id=channel_id,
    )


def _write_recommendation(title: str, description: str, priority: int,
                           module_name: str = "clip_pipeline") -> None:
    """Write a recommendation if none with the same title is already pending."""
    try:
        client = get_client()
        existing = (client.table("director_recommendations")
                    .select("id").eq("title", title).eq("status", "pending")
                    .execute())
        if existing.data:
            return  # already exists
        client.table("director_recommendations").insert({
            "module_name": module_name,
            "title": title,
            "description": description,
            "priority": priority,
            "status": "pending",
        }).execute()
    except Exception as e:
        print(f"[Proactive] _write_recommendation error: {e}")


# ──────────────────────────────────────────────────────────
# TRIGGER 1: DNA_STALE
# ──────────────────────────────────────────────────────────

def check_dna_stale() -> dict | None:
    """Channel DNA not updated for > 90 days OR reference clips < 5."""
    try:
        if _already_triggered_recently("DNA_STALE", hours=48):
            return None

        client = get_client()
        channels_res = client.table("channels").select("id,name,updated_at,channel_dna").execute()
        if not channels_res.data:
            return None

        now = datetime.now(timezone.utc)
        stale = []
        for ch in channels_res.data:
            updated_str = ch.get("updated_at")
            if not updated_str:
                continue
            try:
                updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                days_old = (now - updated_at).days
                dna = ch.get("channel_dna") or {}
                ref_clips = len(dna.get("reference_clips", []))
                if days_old > 90 or ref_clips < 5:
                    stale.append({"channel_id": ch["id"], "name": ch.get("name", ch["id"]),
                                  "days_old": days_old, "ref_clips": ref_clips})
            except Exception:
                continue

        if not stale:
            return None

        for ch in stale:
            msg = (f"Kanal '{ch['name']}' DNA'sı {ch['days_old']} gündür güncellenmedi "
                   f"(referans klip: {ch['ref_clips']}).")
            _emit_trigger("DNA_STALE", msg,
                          {"channel_id": ch["channel_id"], "days_old": ch["days_old"],
                           "ref_clips": ch["ref_clips"]},
                          channel_id=ch["channel_id"])
            _write_recommendation(
                title=f"Kanal DNA Güncelle: {ch['name']}",
                description=msg + " Güncel başarılı klipler üzerinden DNA yeniden oluşturulmalı.",
                priority=2,
            )

        return {"trigger": "DNA_STALE", "stale_channels": stale}
    except Exception as e:
        print(f"[Proactive] DNA_STALE error: {e}")
        return None


# ──────────────────────────────────────────────────────────
# TRIGGER 2: PERFORMANCE_DROP
# ──────────────────────────────────────────────────────────

def check_performance_drop() -> dict | None:
    """Last 7 days pass_rate < (last 30 days pass_rate - 10pp)."""
    try:
        if _already_triggered_recently("PERFORMANCE_DROP", hours=24):
            return None

        sql = """
            SELECT
                COUNT(*) FILTER (WHERE created_at > now() - interval '7 days') AS total_7,
                COUNT(*) FILTER (WHERE created_at > now() - interval '7 days'
                                   AND quality_verdict IN ('pass','fixable'))   AS pass_7,
                COUNT(*) FILTER (WHERE created_at > now() - interval '30 days') AS total_30,
                COUNT(*) FILTER (WHERE created_at > now() - interval '30 days'
                                   AND quality_verdict IN ('pass','fixable'))   AS pass_30
            FROM clips
        """
        rows = _run_sql(sql)
        if not rows:
            return None
        r = rows[0]
        t7, p7 = int(r.get("total_7") or 0), int(r.get("pass_7") or 0)
        t30, p30 = int(r.get("total_30") or 0), int(r.get("pass_30") or 0)

        if t7 < 5 or t30 < 10:
            return None  # not enough data

        rate_7 = p7 / t7 * 100
        rate_30 = p30 / t30 * 100

        if rate_7 < (rate_30 - 10):
            msg = (f"Pass rate son 7 günde %{rate_7:.1f} — 30 günlük ortalama "
                   f"%{rate_30:.1f}'den 10pp+ düştü.")
            _emit_trigger("PERFORMANCE_DROP", msg,
                          {"rate_7d": round(rate_7, 1), "rate_30d": round(rate_30, 1),
                           "drop_pp": round(rate_30 - rate_7, 1)})
            _write_recommendation(
                title="Performans Düşüşü: Pass Rate İncelemesi Gerekiyor",
                description=msg + " S05/S06 logları ve Channel DNA incelenmeli.",
                priority=1,
            )
            return {"trigger": "PERFORMANCE_DROP", "rate_7d": rate_7, "rate_30d": rate_30}
        return None
    except Exception as e:
        print(f"[Proactive] PERFORMANCE_DROP error: {e}")
        return None


# ──────────────────────────────────────────────────────────
# TRIGGER 3: COST_SPIKE
# ──────────────────────────────────────────────────────────

def check_cost_spike() -> dict | None:
    """Most recent job cost > 2σ above mean."""
    try:
        if _already_triggered_recently("COST_SPIKE", hours=12):
            return None

        from app.director.tools.database import get_cost_per_job
        rows = get_cost_per_job(30)
        if len(rows) < 4:
            return None

        costs = [float(r.get("total_cost_usd") or 0) for r in rows]
        if not costs or max(costs) == 0:
            return None

        mean = statistics.mean(costs)
        std = statistics.stdev(costs)
        if std == 0:
            return None

        latest = rows[0]
        latest_cost = float(latest.get("total_cost_usd") or 0)
        z = (latest_cost - mean) / std

        if z > 2.0:
            msg = (f"Son pipeline maliyeti ${latest_cost:.4f} — "
                   f"30 günlük ortalama ${mean:.4f}'in {z:.1f}σ üzerinde.")
            _emit_trigger("COST_SPIKE", msg,
                          {"job_id": latest.get("job_id"), "cost_usd": latest_cost,
                           "mean_usd": round(mean, 4), "z_score": round(z, 2)})
            _write_recommendation(
                title="Maliyet Spike: Anormal Pipeline Maliyeti",
                description=msg + " Hangi adımın (S05/S06) token kullanımı arttı incelenmeli.",
                priority=2,
            )
            return {"trigger": "COST_SPIKE", "job_id": latest.get("job_id"),
                    "cost_usd": latest_cost, "z_score": round(z, 2)}
        return None
    except Exception as e:
        print(f"[Proactive] COST_SPIKE error: {e}")
        return None


# ──────────────────────────────────────────────────────────
# TRIGGER 4: UNUSED_CLIPS
# ──────────────────────────────────────────────────────────

def check_unused_clips() -> dict | None:
    """Pass clips produced in last 14 days but never opened in editor."""
    try:
        if _already_triggered_recently("UNUSED_CLIPS", hours=48):
            return None

        sql = """
            SELECT COUNT(*) AS unused_count
            FROM clips
            WHERE created_at > now() - interval '14 days'
              AND quality_verdict IN ('pass', 'fixable')
              AND (is_successful IS NULL OR is_successful = false)
        """
        rows = _run_sql(sql)
        if not rows:
            return None
        unused = int((rows[0] or {}).get("unused_count") or 0)

        if unused >= 5:
            msg = f"Son 14 günde {unused} adet pass/fixable klip editörde hiç açılmadı."
            _emit_trigger("UNUSED_CLIPS", msg, {"unused_count": unused})
            return {"trigger": "UNUSED_CLIPS", "unused_count": unused}
        return None
    except Exception as e:
        print(f"[Proactive] UNUSED_CLIPS error: {e}")
        return None


# ──────────────────────────────────────────────────────────
# TRIGGER 5: SUCCESS_CELEBRATION
# ──────────────────────────────────────────────────────────

def check_success_celebration() -> dict | None:
    """Last 5 jobs have pass_rate > 60% OR avg_confidence > 8.0 — save pattern to memory."""
    try:
        if _already_triggered_recently("SUCCESS_CELEBRATION", hours=72):
            return None

        sql = """
            SELECT
                COUNT(*)                                                      AS total,
                COUNT(*) FILTER (WHERE quality_verdict IN ('pass','fixable')) AS passed,
                ROUND(AVG(overall_confidence)::NUMERIC, 2)                    AS avg_conf
            FROM clips
            WHERE job_id IN (
                SELECT id FROM jobs ORDER BY created_at DESC LIMIT 5
            )
        """
        rows = _run_sql(sql)
        if not rows:
            return None
        r = rows[0]
        total = int(r.get("total") or 0)
        passed = int(r.get("passed") or 0)
        avg_conf = float(r.get("avg_conf") or 0)

        if total < 5:
            return None

        pass_rate = passed / total * 100
        if pass_rate > 60 or avg_conf > 8.0:
            msg = (f"Son 5 job'da harika sonuçlar: pass rate %{pass_rate:.1f}, "
                   f"avg confidence {avg_conf:.2f}.")
            _emit_trigger("SUCCESS_CELEBRATION", msg,
                          {"pass_rate": round(pass_rate, 1), "avg_confidence": float(avg_conf)})
            # Save to director memory
            try:
                from app.director.tools.memory import save_memory
                save_memory(
                    content=f"Başarı paterni ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                            f"Son 5 job'da pass rate %{pass_rate:.1f}, avg conf {avg_conf:.2f}. "
                            f"Bu dönemde neyin iyi çalıştığı incelenmeli.",
                    type="learning",
                    tags=["success", "pattern", "pass_rate"],
                    source="auto",
                )
            except Exception:
                pass
            return {"trigger": "SUCCESS_CELEBRATION", "pass_rate": pass_rate, "avg_conf": avg_conf}
        return None
    except Exception as e:
        print(f"[Proactive] SUCCESS_CELEBRATION error: {e}")
        return None


# ──────────────────────────────────────────────────────────
# TRIGGER 6: NEW_PATTERN_DETECTED
# ──────────────────────────────────────────────────────────

def check_new_pattern() -> dict | None:
    """Content type pass rate changed > 2x in last 14 days vs previous 14 days."""
    try:
        if _already_triggered_recently("NEW_PATTERN_DETECTED", hours=48):
            return None

        sql = """
            SELECT
                content_type,
                COUNT(*) FILTER (WHERE created_at > now() - interval '14 days')  AS total_now,
                COUNT(*) FILTER (WHERE created_at > now() - interval '14 days'
                                   AND quality_verdict IN ('pass','fixable'))     AS pass_now,
                COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '28 days'
                                                       AND now() - interval '14 days') AS total_prev,
                COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '28 days'
                                                       AND now() - interval '14 days'
                                   AND quality_verdict IN ('pass','fixable'))          AS pass_prev
            FROM clips
            WHERE content_type IS NOT NULL
            GROUP BY content_type
            HAVING COUNT(*) FILTER (WHERE created_at > now() - interval '14 days') >= 3
               AND COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '28 days'
                                                         AND now() - interval '14 days') >= 3
        """
        rows = _run_sql(sql)
        if not rows:
            return None

        patterns = []
        for r in rows:
            ct = r.get("content_type")
            tn, pn = int(r.get("total_now") or 0), int(r.get("pass_now") or 0)
            tp, pp = int(r.get("total_prev") or 0), int(r.get("pass_prev") or 0)
            if tn == 0 or tp == 0:
                continue
            rate_now = pn / tn
            rate_prev = pp / tp
            if rate_prev == 0:
                continue
            ratio = rate_now / rate_prev
            if ratio > 2.0 or ratio < 0.5:
                direction = "artış" if ratio > 1 else "düşüş"
                patterns.append({
                    "content_type": ct,
                    "rate_now": round(rate_now * 100, 1),
                    "rate_prev": round(rate_prev * 100, 1),
                    "ratio": round(ratio, 2),
                    "direction": direction,
                })

        if not patterns:
            return None

        for p in patterns:
            msg = (f"'{p['content_type']}' içerik tipi son 14 günde %{p['rate_now']} pass rate — "
                   f"önceki dönem %{p['rate_prev']} ({p['direction']}, {p['ratio']}x).")
            _emit_trigger("NEW_PATTERN_DETECTED", msg, p)
            try:
                from app.director.tools.memory import save_memory
                save_memory(
                    content=f"Yeni pattern ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                            f"{msg}",
                    type="learning",
                    tags=["pattern", p["content_type"], p["direction"]],
                    source="auto",
                )
            except Exception:
                pass

        return {"trigger": "NEW_PATTERN_DETECTED", "patterns": patterns}
    except Exception as e:
        print(f"[Proactive] NEW_PATTERN_DETECTED error: {e}")
        return None


# ──────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────

def run_proactive_checks(job_id: str | None = None) -> list[dict]:
    """
    Run all proactive triggers. Call after pipeline completion or on hourly cron.
    Returns list of fired triggers (may be empty).
    """
    fired = []
    for check_fn in [
        check_dna_stale,
        check_performance_drop,
        check_cost_spike,
        check_unused_clips,
        check_success_celebration,
        check_new_pattern,
    ]:
        try:
            result = check_fn()
            if result:
                fired.append(result)
        except Exception as e:
            print(f"[Proactive] {check_fn.__name__} unhandled error: {e}")

    if fired:
        print(f"[Proactive] {len(fired)} trigger(s) fired: {[f['trigger'] for f in fired]}")
    return fired
