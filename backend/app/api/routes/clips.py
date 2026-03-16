from fastapi import APIRouter, HTTPException, Body
from app.services.supabase_client import get_client
from typing import Optional, Any

router = APIRouter(prefix="/clips", tags=["clips"])

@router.get("")
async def get_clips(
    job_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    limit: int = 20
):
    try:
        print(f"[ClipsRoute] Fetching clips (job_id={job_id}, channel_id={channel_id}, limit={limit})")
        supabase = get_client()
        
        query = supabase.table("clips").select("*")
        
        if job_id:
            response = query.eq("job_id", job_id).order("posting_order").execute()
        elif channel_id:
            response = query.eq("channel_id", channel_id).order("created_at", desc=True).limit(limit).execute()
        else:
            response = query.order("created_at", desc=True).limit(limit).execute()
            
        return response.data
    except Exception as e:
        print(f"[ClipsRoute] Error fetching clips: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{clip_id}")
async def get_clip(clip_id: str):
    try:
        print(f"[ClipsRoute] Fetching clip {clip_id}")
        supabase = get_client()
        
        response = supabase.table("clips").select("*").eq("id", clip_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Clip not found")
            
        return response.data[0]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ClipsRoute] Error fetching clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{clip_id}/approve")
async def approve_clip(clip_id: str, notes: Optional[str] = Body(default=None, embed=True)):
    try:
        print(f"[ClipsRoute] Approving clip {clip_id}")
        supabase = get_client()
        
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
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{clip_id}/reject")
async def reject_clip(clip_id: str, notes: Optional[str] = Body(default=None, embed=True)):
    try:
        print(f"[ClipsRoute] Rejecting clip {clip_id}")
        supabase = get_client()
        
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
        raise HTTPException(status_code=500, detail=str(e))
