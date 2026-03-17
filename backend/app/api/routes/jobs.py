from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from app.services.supabase_client import get_client
from app.services import storage
from app.pipeline.orchestrator import run_pipeline
from app.models.schemas import JobResponse
from app.models.enums import JobStatus
from app.config import settings
import uuid
import shutil
import os
import json

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("")
async def create_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    title: str = Form(...),
    guest_name: Optional[str] = Form(None),
    channel_id: str = Form("speedy_cast")
):
    channel_id = channel_id.replace("-", "_")
    try:
        if not video.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail="Uploaded file is not a video.")
        
        job_id = str(uuid.uuid4())
        file_bytes = await video.read()
        
        # Save uploaded file
        video_path = storage.save_upload(file_bytes, video.filename, job_id)
        if not video_path:
            raise HTTPException(status_code=500, detail="Failed to save video file.")
            
        supabase = get_client()
        
        # Insert job into Supabase
        job_data = {
            "id": job_id,
            "channel_id": channel_id,
            "video_title": title,
            "guest_name": guest_name,
            "status": JobStatus.QUEUED.value,
            "current_step": "queued",
            "progress_pct": 0
        }
        
        response = supabase.table("jobs").insert(job_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create job in database.")
            
        # Add run_pipeline to background tasks
        background_tasks.add_task(
            run_pipeline,
            job_id,
            video_path,
            title,
            guest_name,
            channel_id
        )
        
        print(f"[JobsRoute] Started job {job_id} for video '{title}'")
        return {"job_id": job_id, "status": "queued", "message": "Processing started"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in POST /jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}")
async def get_job(job_id: str):
    try:
        supabase = get_client()
        
        # Query job
        job_response = supabase.table("jobs").select("*").eq("id", job_id).execute()
        if not job_response.data:
            raise HTTPException(status_code=404, detail="Job not found")
            
        job = job_response.data[0]
        
        # Query clips
        clips_response = supabase.table("clips").select("*").eq("job_id", job_id).order("posting_order").execute()
        
        # Also fetch transcript speaker_map
        transcript_res = supabase.table("transcripts").select("speaker_map").eq("job_id", job_id).execute()
        speaker_map = {}
        if transcript_res.data:
            speaker_map = transcript_res.data[0].get("speaker_map", {})
        
        print(f"[JobsRoute] Fetched job {job_id}")
        return {
            "job": job,
            "clips": clips_response.data if clips_response.data else [],
            "speaker_map": speaker_map
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in GET /jobs/{job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_jobs(channel_id: str = "speedy_cast", limit: int = 20):
    channel_id = channel_id.replace("-", "_")
    try:
        supabase = get_client()
        
        jobs_response = supabase.table("jobs").select("*").eq("channel_id", channel_id).order("created_at", desc=True).limit(limit).execute()
        
        print(f"[JobsRoute] Fetched jobs for channel {channel_id}")
        return jobs_response.data if jobs_response.data else []
        
    except Exception as e:
        print(f"[JobsRoute] Error in GET /jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    try:
        supabase = get_client()
        
        # Delete clips
        supabase.table("clips").delete().eq("job_id", job_id).execute()
        
        # Delete job
        job_response = supabase.table("jobs").delete().eq("id", job_id).execute()
        if not job_response.data:
            raise HTTPException(status_code=404, detail="Job not found")
            
        # Delete output directory for job using storage
        job_dir = os.path.join(storage.OUTPUT_DIR, job_id)
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
            print(f"[JobsRoute] Deleted output directory: {job_dir}")
            
        print(f"[JobsRoute] Deleted job {job_id}")
        return {"deleted": True, "job_id": job_id}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in DELETE /jobs/{job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
