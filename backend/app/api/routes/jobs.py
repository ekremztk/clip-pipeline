from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Depends, Request
from app.services.supabase_client import get_client
from app.middleware.auth import get_current_user
from app.services import storage
from app.pipeline.orchestrator import run_pipeline
from app.models.schemas import JobResponse
from app.models.enums import JobStatus
from app.config import settings
from app.limiter import limiter
import uuid
import shutil
import os
import json
import subprocess

# Allowed video MIME types and extensions
_ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm"}
_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

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
@limiter.limit("10/minute")
async def upload_preview(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Instantly uploads a video file and returns its duration.
    Called as soon as user selects a file, before job creation.
    Rate limited: 10 uploads/minute per IP.
    """
    try:
        # YÜKS-3: Validate MIME type
        if file.content_type not in _ALLOWED_VIDEO_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        # YÜKS-3: Sanitize filename — use only UUID + safe extension, ignore user-provided name
        original_ext = os.path.splitext(file.filename or "")[1].lower()
        if original_ext not in _ALLOWED_VIDEO_EXTS:
            original_ext = ".mp4"
        upload_id = str(uuid.uuid4())
        safe_filename = f"{upload_id}{original_ext}"
        file_path = settings.UPLOAD_DIR / safe_filename

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        ffprobe_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json", str(file_path)
        ]
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration_seconds = float(data["format"]["duration"])

        print(f"[UploadPreview] Uploaded {safe_filename}, duration: {duration_seconds:.1f}s")

        # YÜKS-2: Never return server file_path to client
        return {
            "upload_id": upload_id,
            "duration_seconds": duration_seconds,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[UploadPreview] Error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

async def _download_and_run_pipeline(
    job_id: str,
    youtube_url: str,
    video_title: str,
    guest_name: Optional[str],
    channel_id: str,
    user_id: str,
    clip_duration_min: Optional[int],
    clip_duration_max: Optional[int],
    trim_start_seconds: float = 0.0,
    trim_end_seconds: Optional[float] = None,
) -> None:
    """Background task: downloads YouTube video, applies trim if needed, then runs pipeline."""
    from app.services.video_downloader import VideoDownloader
    from app.pipeline.orchestrator import run_pipeline, update_job
    from app.models.enums import JobStatus
    from app.services.supabase_client import get_client

    downloader = VideoDownloader()
    video_path = None
    trimmed_path = None
    try:
        update_job(
            job_id,
            status=JobStatus.PROCESSING.value,
            current_step="downloading_video",
            current_step_number=0,
            progress_pct=2,
        )
        print(f"[JobsRoute] Downloading YouTube video for job {job_id}: {youtube_url}")
        video_path = await downloader.download(youtube_url, max_quality="1080")
        print(f"[JobsRoute] Download complete: {video_path}")

        # Apply trim if requested
        if trim_start_seconds > 0.0 or trim_end_seconds is not None:
            duration = get_video_duration(video_path)
            end = trim_end_seconds if trim_end_seconds is not None else duration
            if trim_start_seconds > 0.0 or end < duration:
                trimmed_path = video_path.replace(".", "_trimmed.", 1)
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_start_seconds),
                    "-i", video_path,
                    "-t", str(end - trim_start_seconds),
                    "-c", "copy",
                    trimmed_path,
                ]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0 and os.path.exists(trimmed_path):
                    os.remove(video_path)
                    video_path = trimmed_path
                    trimmed_path = None
                else:
                    print(f"[JobsRoute] Trim failed, using full video: {result.stderr}")

        get_client().table("jobs").update({"video_path": video_path}).eq("id", job_id).execute()
        run_pipeline(job_id, video_path, video_title, guest_name, channel_id, user_id, clip_duration_min, clip_duration_max)
    except Exception as e:
        print(f"[JobsRoute] YouTube download failed for job {job_id}: {e}")
        update_job(job_id, status=JobStatus.FAILED.value, error_message=f"YouTube download failed: {e}")
        for path in [video_path, trimmed_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


@router.get("/youtube-info")
async def get_youtube_info(url: str, current_user: dict = Depends(get_current_user)):
    """Fetch YouTube video metadata (title, duration) without downloading."""
    from app.services.video_downloader import VideoDownloader
    if not any(h in url for h in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/")):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    try:
        downloader = VideoDownloader()
        info = await downloader.get_info(url)
        return {
            "title": info.get("title", ""),
            "duration_seconds": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("uploader", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch video info: {e}")


@router.post("")
@limiter.limit("20/hour")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    upload_id: str = Form(None),
    video: UploadFile = File(None),
    youtube_url: Optional[str] = Form(None),
    title: str = Form(...),
    guest_name: Optional[str] = Form(None),
    channel_id: str = Form(...),
    trim_start_seconds: float = Form(0.0),
    trim_end_seconds: float = Form(None),
    clip_duration_min: Optional[int] = Form(None),
    clip_duration_max: Optional[int] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    genre: Optional[str] = Form(None),
    auto_hook: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    channel_id = channel_id.replace("-", "_")
    try:
        job_id = str(uuid.uuid4())

        if youtube_url:
            # Validate it's a real YouTube URL
            if not any(host in youtube_url for host in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/")):
                raise HTTPException(status_code=400, detail="Invalid YouTube URL. Supported: youtube.com/watch, youtu.be, youtube.com/shorts")
            video_path = ""  # Will be set by background downloader

        elif upload_id:
            upload_dir = storage.UPLOAD_DIR
            video_path = None
            for f in os.listdir(upload_dir):
                if f.startswith(upload_id):
                    video_path = os.path.join(upload_dir, f)
                    break

            if not video_path:
                raise HTTPException(status_code=404, detail="Uploaded file not found.")

        elif video:
            # YÜKS-3: Validate MIME type
            if video.content_type not in _ALLOWED_VIDEO_TYPES:
                raise HTTPException(status_code=400, detail="Uploaded file is not a supported video format.")

            # YÜKS-3: Sanitize filename
            original_ext = os.path.splitext(video.filename or "")[1].lower()
            if original_ext not in _ALLOWED_VIDEO_EXTS:
                original_ext = ".mp4"
            safe_name = f"{job_id}{original_ext}"

            file_bytes = await video.read()
            video_path = storage.save_upload(file_bytes, safe_name, job_id)
            if not video_path:
                raise HTTPException(status_code=500, detail="Failed to save video file.")
        else:
            raise HTTPException(status_code=400, detail="Must provide youtube_url, upload_id, or video file.")
            
        # Trimming logic (skip for YouTube — video isn't downloaded yet)
        if not youtube_url and (trim_start_seconds > 0.0 or (trim_end_seconds is not None)):
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
                
                print(f"[JobsRoute] Trimming video")
                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                    video_path = trimmed_path
                except Exception as e:
                    print(f"[JobsRoute] Error trimming video: {e}")
                    # Clean up temp file on trim failure
                    if os.path.exists(trimmed_path):
                        os.remove(trimmed_path)
                    raise HTTPException(status_code=500, detail="Failed to trim video.")
            
        supabase = get_client()

        # Verify channel belongs to current user
        channel_check = supabase.table("channels").select("id").eq("id", channel_id).eq("user_id", current_user["id"]).execute()
        if not channel_check.data:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Insert job into Supabase
        # Log new clip settings for future pipeline use
        if clip_duration_min is not None or clip_duration_max is not None:
            print(f"[JobsRoute] Clip duration: {clip_duration_min}–{clip_duration_max}s, aspect: {aspect_ratio}, genre: {genre}, auto_hook: {auto_hook}")

        job_data = {
            "id": job_id,
            "channel_id": channel_id,
            "user_id": current_user["id"],
            "video_title": title,
            "guest_name": guest_name,
            "status": JobStatus.QUEUED.value,
            "current_step": "queued",
            "progress_pct": 0,
            "video_path": video_path,
            "trim_start_seconds": trim_start_seconds,
            "trim_end_seconds": trim_end_seconds,
        }
        if clip_duration_min is not None:
            job_data["clip_duration_min"] = clip_duration_min
        if clip_duration_max is not None:
            job_data["clip_duration_max"] = clip_duration_max
        
        response = supabase.table("jobs").insert(job_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create job in database.")
            
        # Add pipeline task to background
        if youtube_url:
            background_tasks.add_task(
                _download_and_run_pipeline,
                job_id,
                youtube_url,
                title,
                guest_name,
                channel_id,
                current_user["id"],
                clip_duration_min,
                clip_duration_max,
                trim_start_seconds,
                trim_end_seconds,
            )
        else:
            background_tasks.add_task(
                run_pipeline,
                job_id,
                video_path,
                title,
                guest_name,
                channel_id,
                current_user["id"],
                clip_duration_min,
                clip_duration_max,
            )

        print(f"[JobsRoute] Started job {job_id} for video '{title}'" + (" (YouTube)" if youtube_url else ""))
        return {"job_id": job_id, "status": "queued", "message": "Processing started"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[JobsRoute] Error in POST /jobs: {e}")
        raise HTTPException(status_code=500, detail="Job creation failed")


@router.post("/youtube-preview")
@limiter.limit("5/minute")
async def youtube_preview(
    request: Request,
    url: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Downloads a YouTube video (up to 1080p) to temp storage for preview.
    Returns upload_id and duration so the frontend can show a real <video> element
    and re-use the pre-downloaded file when starting the pipeline.
    """
    from app.services.video_downloader import VideoDownloader

    if not any(h in url for h in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/")):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        downloader = VideoDownloader()
        video_path = await downloader.download(url, max_quality="1080")
        upload_id = os.path.splitext(os.path.basename(video_path))[0]
        duration = get_video_duration(video_path)
        print(f"[YoutubePreview] Downloaded {upload_id}, duration: {duration:.1f}s")
        return {"upload_id": upload_id, "duration_seconds": duration}
    except Exception as e:
        print(f"[YoutubePreview] Error: {e}")
        raise HTTPException(status_code=422, detail=f"Could not download video: {e}")


@router.get("/video-stream/{upload_id}")
async def video_stream(upload_id: str, current_user: dict = Depends(get_current_user)):
    """Stream a pre-downloaded temp video file for browser preview."""
    import re
    from fastapi.responses import FileResponse

    if not re.match(r"^[a-f0-9\-]{36}$", upload_id):
        raise HTTPException(status_code=400, detail="Invalid upload ID")

    upload_dir = settings.UPLOAD_DIR
    for fname in os.listdir(upload_dir):
        if os.path.splitext(fname)[0] == upload_id:
            file_path = os.path.join(upload_dir, fname)
            return FileResponse(file_path, media_type="video/mp4")

    raise HTTPException(status_code=404, detail="File not found")


@router.get("/{job_id}")
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()
        
        # Query job (ownership check via user_id)
        job_response = supabase.table("jobs").select("*").eq("id", job_id).eq("user_id", current_user["id"]).execute()
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("")
async def list_jobs(channel_id: str, limit: int = 20, current_user: dict = Depends(get_current_user)):
    channel_id = channel_id.replace("-", "_")
    try:
        supabase = get_client()
        
        jobs_response = supabase.table("jobs").select("*").eq("channel_id", channel_id).eq("user_id", current_user["id"]).order("created_at", desc=True).limit(limit).execute()
        
        print(f"[JobsRoute] Fetched jobs for channel {channel_id}")
        return jobs_response.data if jobs_response.data else []
        
    except Exception as e:
        print(f"[JobsRoute] Error in GET /jobs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{job_id}")
async def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    try:
        supabase = get_client()

        # Verify ownership before deleting
        check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
        if not check.data:
            raise HTTPException(status_code=404, detail="Job not found")

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
        raise HTTPException(status_code=500, detail="Internal server error")
