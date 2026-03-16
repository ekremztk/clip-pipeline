from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timezone
from app.services.supabase_client import get_client
from app.memory import feedback_processor
from workers import feedback_worker

router = APIRouter(prefix="/feedback", tags=["feedback"])

class PublishRequest(BaseModel):
    youtube_video_id: str
    published_platform: str = "youtube"

class ApproveRagRequest(BaseModel):
    approved: bool

@router.post("/clips/{clip_id}/publish")
async def publish_clip(clip_id: str, request: PublishRequest):
    try:
        supabase = get_client()
        supabase.table("clips").update({
            "youtube_video_id": request.youtube_video_id,
            "published_platform": request.published_platform,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "feedback_status": "pending"
        }).eq("id", clip_id).execute()
        
        return {"published": True, "clip_id": clip_id}
    except Exception as e:
        print(f"[Feedback] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clips/{clip_id}/approve-rag")
async def approve_rag(clip_id: str, request: ApproveRagRequest, background_tasks: BackgroundTasks):
    try:
        supabase = get_client()
        result = supabase.table("clips").select("*").eq("id", clip_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Clip not found")
            
        clip = result.data[0]
        
        if request.approved:
            background_tasks.add_task(feedback_processor.process_successful_clip, clip)
        else:
            supabase.table("clips").update({
                "is_successful": False
            }).eq("id", clip_id).execute()
            
        return {"processed": True, "clip_id": clip_id, "approved": request.approved}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Feedback] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collect")
async def collect_feedback(background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(feedback_worker.check_pending_clips)
        return {"started": True, "message": "Feedback collection started"}
    except Exception as e:
        print(f"[Feedback] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clips/{clip_id}/performance")
async def get_performance(clip_id: str):
    try:
        supabase = get_client()
        result = supabase.table("clips").select(
            "id, views_48h, views_7d, avd_pct, is_successful, feedback_status, why_failed"
        ).eq("id", clip_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Clip not found")
            
        clip = result.data[0]
        return {
            "clip_id": clip_id,
            "views_48h": clip.get("views_48h"),
            "views_7d": clip.get("views_7d"),
            "avd_pct": clip.get("avd_pct"),
            "is_successful": clip.get("is_successful"),
            "feedback_status": clip.get("feedback_status"),
            "why_failed": clip.get("why_failed")
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Feedback] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
