from fastapi import APIRouter, HTTPException, Body, Depends
from app.services.supabase_client import get_client
from app.middleware.auth import get_current_user
from typing import Optional, Any

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


@router.get("")
async def get_clips(
    job_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    if channel_id:
        channel_id = channel_id.replace("-", "_")

    try:
        print(f"[ClipsRoute] Fetching clips (job_id={job_id}, channel_id={channel_id}, limit={limit})")
        supabase = get_client()

        query = supabase.table("clips").select("*")

        if job_id:
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
