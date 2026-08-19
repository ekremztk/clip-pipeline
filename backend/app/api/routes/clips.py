from fastapi import APIRouter, HTTPException, Body, Depends
from app.services.supabase_client import get_client
from app.middleware.auth import get_current_user
import uuid
from typing import Optional, Any
from datetime import datetime, timezone

router = APIRouter(prefix="/clips", tags=["clips"])


def _verify_clip_owner(clip_id: str, user_id: str, supabase) -> dict:
    """Fetch clip and verify ownership via its parent job. Returns clip or raises 404."""
    clip_res = supabase.table("clips").select("*").eq("id", clip_id).execute()
    if not clip_res.data:
        raise HTTPException(status_code=404, detail="Clip not found")
    clip = clip_res.data[0]
    job_id = clip.get("job_id")
    if job_id:
        job_res = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", user_id).execute()
        if not job_res.data:
            raise HTTPException(status_code=404, detail="Clip not found")
    return clip


# Bounds one request; the projects page sends 30 at a time.
MAX_JOB_IDS = 100


@router.get("")
async def get_clips(
    job_id: Optional[str] = None,
    job_ids: Optional[str] = None,
    channel_id: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    if channel_id:
        channel_id = channel_id.replace("-", "_")

    try:
        print(f"[ClipsRoute] Fetching clips (job_id={job_id}, job_ids={job_ids}, channel_id={channel_id}, limit={limit})")
        supabase = get_client()

        query = supabase.table("clips").select("*")

        if job_ids:
            # The projects page loads one page of jobs at a time and needs
            # exactly those jobs' clips — a channel-wide limit would either
            # overfetch or, once the reader scrolls far enough, silently stop
            # covering the jobs on screen and leave their cards blank.
            # Postgres rejects a malformed uuid with an error rather than an
            # empty match, so anything that is not one is dropped here — a junk
            # query string should come back empty, not as a 500.
            requested = []
            for raw in job_ids.split(",")[:MAX_JOB_IDS]:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    uuid.UUID(raw)
                except ValueError:
                    continue
                requested.append(raw)
            if not requested:
                return []
            # Query only the ids this user actually owns, never the ids asked
            # for: an id belonging to someone else must return nothing rather
            # than an error, so probing cannot distinguish "not yours" from
            # "does not exist".
            owned = (
                supabase.table("jobs").select("id")
                .in_("id", requested).eq("user_id", current_user["id"]).execute()
            )
            owned_ids = [j["id"] for j in (owned.data or [])]
            if not owned_ids:
                return []
            response = query.in_("job_id", owned_ids).order("posting_order").execute()
        elif job_id:
            # Verify job belongs to user
            job_check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
            if not job_check.data:
                raise HTTPException(status_code=404, detail="Job not found")
            response = query.eq("job_id", job_id).order("posting_order").execute()
        elif channel_id:
            # Verify channel belongs to user
            ch_check = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
            if not ch_check.data:
                raise HTTPException(status_code=404, detail="Channel not found")
            response = query.eq("channel_id", channel_id).order("created_at", desc=True).limit(limit).execute()
        else:
            # Return clips for all of user's jobs
            user_jobs = supabase.table("jobs").select("id").eq("user_id", current_user["id"]).execute()
            if not user_jobs.data:
                return []
            job_ids = [j["id"] for j in user_jobs.data]
            response = query.in_("job_id", job_ids).order("created_at", desc=True).limit(limit).execute()

        return response.data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error fetching clips: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{clip_id}")
async def delete_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a single clip: cascades to R2 (captioned + reframed + landscape)."""
    try:
        supabase = get_client()
        clip = _verify_clip_owner(clip_id, current_user["id"], supabase)

        # Remove R2 objects first (best-effort — DB row goes away regardless)
        try:
            from app.services.r2_client import delete_url
            for url in [
                clip.get("video_captioned_path"),
                clip.get("video_reframed_path"),
                clip.get("file_url"),
            ]:
                if url:
                    delete_url(url)
        except Exception as _e:
            print(f"[ClipsRoute] R2 cleanup warning (non-fatal): {_e}")

        supabase.table("clips").delete().eq("id", clip_id).execute()
        print(f"[ClipsRoute] Deleted clip {clip_id}")
        return {"deleted": True, "id": clip_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error deleting clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete clip")


@router.get("/{clip_id}")
async def get_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    try:
        print(f"[ClipsRoute] Fetching clip {clip_id}")
        supabase = get_client()
        clip = _verify_clip_owner(clip_id, current_user["id"], supabase)
        return clip
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error fetching clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{clip_id}/approve")
async def approve_clip(clip_id: str, notes: Optional[str] = Body(default=None, embed=True), current_user: dict = Depends(get_current_user)):
    try:
        print(f"[ClipsRoute] Approving clip {clip_id}")
        supabase = get_client()
        _verify_clip_owner(clip_id, current_user["id"], supabase)

        update_data: dict[str, Any] = {"user_approved": True}
        if notes is not None:
            update_data["user_notes"] = notes

        response = supabase.table("clips").update(update_data).eq("id", clip_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")

        return {"approved": True, "clip_id": clip_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error approving clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{clip_id}/unset-approval")
async def unset_approval_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    try:
        print(f"[ClipsRoute] Unsetting approval for clip {clip_id}")
        supabase = get_client()
        _verify_clip_owner(clip_id, current_user["id"], supabase)

        update_data: dict[str, Any] = {"user_approved": None}

        response = supabase.table("clips").update(update_data).eq("id", clip_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")

        return {"unset": True, "clip_id": clip_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error unsetting approval clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{clip_id}/publish")
async def publish_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    try:
        print(f"[ClipsRoute] Marking clip {clip_id} as published")
        supabase = get_client()
        _verify_clip_owner(clip_id, current_user["id"], supabase)

        response = supabase.table("clips").update({"is_published": True}).eq("id", clip_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")
        return {"published": True, "clip_id": clip_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error publishing clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{clip_id}/unpublish")
async def unpublish_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    try:
        print(f"[ClipsRoute] Unmarking clip {clip_id} as published")
        supabase = get_client()
        _verify_clip_owner(clip_id, current_user["id"], supabase)

        response = supabase.table("clips").update({"is_published": False}).eq("id", clip_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")
        return {"published": False, "clip_id": clip_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error unpublishing clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{clip_id}/stock-review")
async def update_stock_review(
    clip_id: str,
    status: Optional[str] = Body(default=None, embed=True),
    note: Optional[str] = Body(default=None, embed=True),
    current_user: dict = Depends(get_current_user),
):
    try:
        print(f"[ClipsRoute] Updating stock review for clip {clip_id}")
        supabase = get_client()
        _verify_clip_owner(clip_id, current_user["id"], supabase)

        allowed_statuses = {"unreviewed", "selected", "rejected", "posted"}
        update_data: dict[str, Any] = {
            "stock_reviewed_at": datetime.now(timezone.utc).isoformat(),
            "stock_review_updated_by": current_user["id"],
        }
        if status is not None:
            normalized_status = status.strip().lower()
            if normalized_status not in allowed_statuses:
                raise HTTPException(status_code=400, detail="Invalid stock review status")
            update_data["stock_review_status"] = normalized_status
            if normalized_status == "posted":
                update_data["is_published"] = True
        if note is not None:
            update_data["stock_review_note"] = note

        response = supabase.table("clips").update(update_data).eq("id", clip_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error updating stock review for clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{clip_id}/transcript")
async def get_clip_transcript(clip_id: str, current_user: dict = Depends(get_current_user)):
    """
    Returns word-level transcript for a clip's time range.
    Timestamps are relative to clip start (0 = first second of the clip).
    """
    try:
        supabase = get_client()
        clip = _verify_clip_owner(clip_id, current_user["id"], supabase)

        job_id = clip.get("job_id")
        clip_start = float(clip.get("start_time") or 0)
        clip_end = float(clip.get("end_time") or 0)

        if not job_id or clip_end <= clip_start:
            return {"words": []}

        transcript_res = (
            supabase.table("transcripts")
            .select("word_timestamps")
            .eq("job_id", job_id)
            .limit(1)
            .execute()
        )

        if not transcript_res.data:
            return {"words": []}

        words = transcript_res.data[0].get("word_timestamps") or []

        # Filter to clip's time range, adjust timestamps to be relative to clip start
        clip_words = []
        for w in words:
            w_start = float(w.get("start", 0))
            w_end = float(w.get("end", w_start))
            if clip_start <= w_start <= clip_end:
                clip_words.append({
                    "word": w.get("punctuated_word") or w.get("word", ""),
                    "start": round(w_start - clip_start, 3),
                    "end": round(w_end - clip_start, 3),
                })

        return {"words": clip_words}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error fetching transcript for clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{clip_id}/reject")
async def reject_clip(clip_id: str, notes: Optional[str] = Body(default=None, embed=True), current_user: dict = Depends(get_current_user)):
    try:
        print(f"[ClipsRoute] Rejecting clip {clip_id}")
        supabase = get_client()
        _verify_clip_owner(clip_id, current_user["id"], supabase)

        update_data: dict[str, Any] = {"user_approved": False}
        if notes is not None:
            update_data["user_notes"] = notes

        response = supabase.table("clips").update(update_data).eq("id", clip_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")

        return {"rejected": True, "clip_id": clip_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error rejecting clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
