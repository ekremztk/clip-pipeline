from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timezone
from app.services.supabase_client import get_client
from app.memory import feedback_processor
from workers import feedback_worker

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _director_approved(clip_id: str) -> None:
    try:
        from app.director.learning import on_clip_approved
        on_clip_approved(clip_id)
    except Exception as e:
        print(f"[Feedback] director approved hook error: {e}")


def _director_rejected(clip_id: str, why_failed: str | None) -> None:
    try:
        from app.director.learning import on_clip_rejected
        on_clip_rejected(clip_id, why_failed)
    except Exception as e:
        print(f"[Feedback] director rejected hook error: {e}")

class PublishRequest(BaseModel):
    youtube_video_id: str
    published_platform: str = "youtube"

class ApproveRagRequest(BaseModel):
    approved: bool

@router.post("/clips/{clip_id}/publish")
async def publish_clip(clip_id: str, request: PublishRequest, background_tasks: BackgroundTasks):
    try:
        supabase = get_client()
        supabase.table("clips").update({
            "youtube_video_id": request.youtube_video_id,
            "published_platform": request.published_platform,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "feedback_status": "pending"
        }).eq("id", clip_id).execute()

        def _director_published(cid: str, yt_id: str) -> None:
            try:
                from app.director.learning import on_clip_published
                on_clip_published(cid, yt_id)
            except Exception as e:
                print(f"[Feedback] director published hook error: {e}")

        background_tasks.add_task(_director_published, clip_id, request.youtube_video_id)
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
            background_tasks.add_task(_director_approved, clip_id)
        else:
            supabase.table("clips").update({
                "user_approved": False
            }).eq("id", clip_id).execute()
            background_tasks.add_task(_director_rejected, clip_id, None)
            
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
