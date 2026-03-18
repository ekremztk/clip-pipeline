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
import subprocess

router = APIRouter(prefix="/jobs", tags=["jobs"])

def get_video_duration(file_path: str) -> float:
    try:
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ffprobe] Error getting duration: {e}")
        return 0.0

@router.post("/upload-preview")
async def upload_preview(file: UploadFile = File(...)):
    """
    Instantly uploads a video file and returns its duration.
    Called as soon as user selects a file, before job creation.
    """
    try:
        import uuid, subprocess, json
        from fastapi import UploadFile, File
        
        upload_id = str(uuid.uuid4())
        filename = f"{upload_id}_{file.filename}"
        file_path = settings.UPLOAD_DIR / filename
        
        # Save file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Get duration with ffprobe
        ffprobe_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json", str(file_path)
        ]
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration_seconds = float(data["format"]["duration"])
        
        print(f"[UploadPreview] Uploaded {filename}, duration: {duration_seconds:.1f}s")
        
        return {
            "upload_id": upload_id,
            "duration_seconds": duration_seconds,
            "file_path": str(file_path),
            "filename": file.filename
        }
        
    except Exception as e:
        print(f"[UploadPreview] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_job(
    background_tasks: BackgroundTasks,
    upload_id: str = Form(None),
    video: UploadFile = File(None),
    title: str = Form(...),
    guest_name: Optional[str] = Form(None),
    channel_id: str = Form(...),
    trim_start_seconds: float = Form(0.0),
    trim_end_seconds: float = Form(None)
):
    channel_id = channel_id.replace("-", "_")
    try:
        job_id = str(uuid.uuid4())
        
        if upload_id:
            upload_dir = storage.UPLOAD_DIR
            video_path = None
            for f in os.listdir(upload_dir):
                if f.startswith(f"{upload_id}_"):
                    video_path = os.path.join(upload_dir, f)
                    break
            
            if not video_path:
                raise HTTPException(status_code=404, detail="Uploaded file not found.")
                
        elif video:
            if not video.content_type.startswith("video/"):
                raise HTTPException(status_code=400, detail="Uploaded file is not a video.")
            
            file_bytes = await video.read()
            video_path = storage.save_upload(file_bytes, video.filename, job_id)
            if not video_path:
                raise HTTPException(status_code=500, detail="Failed to save video file.")
        else:
            raise HTTPException(status_code=400, detail="Must provide either upload_id or video file.")
            
        # Trimming logic
        if trim_start_seconds > 0.0 or (trim_end_seconds is not None):
            duration = get_video_duration(video_path)
            if trim_end_seconds is None:
                trim_end_seconds = duration
            
            if trim_start_seconds > 0.0 or trim_end_seconds < duration:
                # Need to trim
                trimmed_filename = f"trimmed_{os.path.basename(video_path)}"
                trimmed_path = os.path.join(os.path.dirname(video_path), trimmed_filename)
                
                trim_duration = trim_end_seconds - trim_start_seconds
                
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_start_seconds),
                    "-i", video_path,
                    "-t", str(trim_duration),
                    "-c", "copy",
                    trimmed_path
                ]
                
                print(f"[JobsRoute] Trimming video: {' '.join(cmd)}")
                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                    video_path = trimmed_path
                except Exception as e:
                    print(f"[JobsRoute] Error trimming video: {e}")
                    raise HTTPException(status_code=500, detail="Failed to trim video.")
            
        supabase = get_client()
        
        # Insert job into Supabase
        job_data = {
            "id": job_id,
            "channel_id": channel_id,
            "video_title": title,
            "guest_name": guest_name,
            "status": JobStatus.QUEUED.value,
            "current_step": "queued",
            "progress_pct": 0,
            "video_path": video_path,
            "trim_start_seconds": trim_start_seconds,
            "trim_end_seconds": trim_end_seconds
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
async def list_jobs(channel_id: str, limit: int = 20):
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
