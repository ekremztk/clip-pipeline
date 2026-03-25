"""
Director Learning Loop — automatic memory generation from clip feedback.

Called after every clip approval/rejection (approve-rag endpoint).
Detects patterns and writes director_memory entries + channel DNA suggestions.
Never raises — all errors are caught silently.
"""

from datetime import datetime, timezone
from app.services.supabase_client import get_client
from app.director.tools.memory import save_memory
from app.director.events import director_events


def _get_clip_context(clip_id: str) -> dict | None:
    """Fetch clip with channel/content_type context."""
    try:
        client = get_client()
        res = (client.table("clips")
               .select("id,channel_id,job_id,content_type,quality_verdict,overall_confidence,"
                       "hook_text,is_successful,why_failed,suggested_title")
               .eq("id", clip_id)
               .single()
               .execute())
        return res.data
    except Exception:
        return None


def _count_rejections_for_content_type(channel_id: str, content_type: str, days: int = 30) -> int:
    """Count how many pass/fixable clips of this content_type were rejected in last N days."""
    try:
        from app.director.tools.database import _run_sql
        rows = _run_sql(f"""
            SELECT COUNT(*) AS cnt
            FROM clips
            WHERE channel_id = %s
              AND content_type = %s
              AND quality_verdict IN ('pass', 'fixable')
              AND is_successful = false
              AND created_at > now() - interval '{days} days'
        """, (channel_id, content_type))
        return int((rows[0] or {}).get("cnt") or 0) if rows else 0
    except Exception:
        return 0


def _suggest_no_go_zone(channel_id: str, content_type: str, rejection_count: int) -> None:
    """Write a recommendation to add content_type to channel DNA no_go_zones."""
    try:
        client = get_client()
        title = f"DNA No-Go Zone: '{content_type}' content type"
        # Check for duplicate pending
        existing = (client.table("director_recommendations")
                    .select("id").eq("title", title).eq("status", "pending").execute())
        if existing.data:
            return
        client.table("director_recommendations").insert({
            "module_name": "learning",
            "title": title,
            "description": (
                f"'{content_type}' clips were rejected {rejection_count} times in the last 30 days "
                f"despite passing quality gate. Consider adding to channel DNA no_go_zones."
            ),
            "priority": 2,
            "status": "pending",
        }).execute()
    except Exception as e:
        print(f"[Learning] _suggest_no_go_zone error: {e}")


def on_clip_approved(clip_id: str) -> None:
    """
    Called when a clip is approved (is_successful = True).
    Saves a positive learning memory for this content_type.
    """
    try:
        clip = _get_clip_context(clip_id)
        if not clip:
            return

        content_type = clip.get("content_type") or "unknown"
        channel_id = clip.get("channel_id")
        confidence = clip.get("overall_confidence") or 0

        memory_content = (
            f"Approved clip ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
            f"content_type='{content_type}', channel={channel_id}, "
            f"confidence={confidence:.2f}. "
            f"This content type is working — reinforce in DNA."
        )
        save_memory(
            content=memory_content,
            type="learning",
            tags=["approved", content_type, channel_id or ""],
            source="feedback",
        )

        director_events.emit_sync(
            module="learning",
            event="clip_feedback_received",
            payload={
                "clip_id": clip_id,
                "verdict": "approved",
                "content_type": content_type,
                "confidence": confidence,
            },
            channel_id=channel_id,
        )
    except Exception as e:
        print(f"[Learning] on_clip_approved error: {e}")


def on_clip_rejected(clip_id: str, why_failed: str | None = None) -> None:
    """
    Called when a clip is rejected (is_successful = False) despite passing quality gate.
    Saves negative learning memory, checks pattern threshold, suggests no_go_zone if needed.
    """
    try:
        clip = _get_clip_context(clip_id)
        if not clip:
            return

        content_type = clip.get("content_type") or "unknown"
        channel_id = clip.get("channel_id")
        quality_verdict = clip.get("quality_verdict") or "unknown"
        confidence = clip.get("overall_confidence") or 0

        memory_content = (
            f"Rejected clip ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
            f"content_type='{content_type}', channel={channel_id}, "
            f"quality_verdict={quality_verdict}, confidence={confidence:.2f}. "
            f"Reason: {why_failed or 'not specified'}. "
            f"Passed quality gate but rejected by user — high-priority mismatch."
        )
        save_memory(
            content=memory_content,
            type="learning",
            tags=["rejected", content_type, channel_id or "", "mismatch"],
            source="feedback",
        )

        director_events.emit_sync(
            module="learning",
            event="clip_feedback_received",
            payload={
                "clip_id": clip_id,
                "verdict": "rejected",
                "content_type": content_type,
                "quality_verdict": quality_verdict,
                "why_failed": why_failed,
            },
            channel_id=channel_id,
        )

        # Pattern threshold: 3+ rejections of this content_type → suggest no_go_zone
        if channel_id and content_type != "unknown":
            rejection_count = _count_rejections_for_content_type(channel_id, content_type)
            if rejection_count >= 3:
                _suggest_no_go_zone(channel_id, content_type, rejection_count)
                save_memory(
                    content=(
                        f"Pattern detected ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                        f"'{content_type}' rejected {rejection_count}x in 30 days on channel {channel_id}. "
                        f"Consider adding to no_go_zones in channel DNA."
                    ),
                    type="learning",
                    tags=["pattern", "no_go_zone", content_type, channel_id],
                    source="auto",
                )
    except Exception as e:
        print(f"[Learning] on_clip_rejected error: {e}")


def on_clip_published(clip_id: str, youtube_video_id: str | None = None) -> None:
    """Called when a clip is published. Records content type success signal."""
    try:
        clip = _get_clip_context(clip_id)
        if not clip:
            return

        content_type = clip.get("content_type") or "unknown"
        channel_id = clip.get("channel_id")

        save_memory(
            content=(
                f"Published clip ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                f"content_type='{content_type}', channel={channel_id}. "
                f"Content type validated through full pipeline → publish."
            ),
            type="learning",
            tags=["published", content_type, channel_id or ""],
            source="feedback",
        )

        director_events.emit_sync(
            module="learning", event="clip_published",
            payload={"clip_id": clip_id, "content_type": content_type,
                     "youtube_video_id": youtube_video_id},
            channel_id=channel_id,
        )
    except Exception as e:
        print(f"[Learning] on_clip_published error: {e}")


def on_views_received(clip_id: str, views_48h: int, avd_pct: float) -> None:
    """Called when 48h view data is available. Records real performance feedback."""
    try:
        clip = _get_clip_context(clip_id)
        if not clip:
            return

        content_type = clip.get("content_type") or "unknown"
        channel_id = clip.get("channel_id")

        if views_48h > 1000 and avd_pct > 50:
            verdict = "viral_success"
            memory_text = (
                f"Viral success ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                f"content_type='{content_type}', {views_48h} views in 48h, "
                f"{avd_pct:.1f}% AVD. This content type works — reinforce."
            )
        elif views_48h < 100:
            verdict = "low_performance"
            memory_text = (
                f"Low performance ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                f"content_type='{content_type}', only {views_48h} views in 48h, "
                f"{avd_pct:.1f}% AVD. Published but didn't gain traction."
            )
        else:
            verdict = "moderate"
            memory_text = (
                f"Moderate performance ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): "
                f"content_type='{content_type}', {views_48h} views in 48h, "
                f"{avd_pct:.1f}% AVD."
            )

        save_memory(
            content=memory_text,
            type="learning",
            tags=["performance", verdict, content_type, channel_id or ""],
            source="feedback",
        )

        director_events.emit_sync(
            module="learning", event="views_received",
            payload={"clip_id": clip_id, "views_48h": views_48h,
                     "avd_pct": avd_pct, "verdict": verdict,
                     "content_type": content_type},
            channel_id=channel_id,
        )
    except Exception as e:
        print(f"[Learning] on_views_received error: {e}")
