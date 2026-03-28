import os
import zipfile
import tempfile
import pathlib
import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, StreamingResponse
from app.services.supabase_client import get_client
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/downloads", tags=["downloads"])

def cleanup_temp_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"[DownloadsRoute] Cleaned up temporary file: {path}")
    except Exception as e:
        print(f"[DownloadsRoute] Error cleaning up temp file: {e}")

@router.get("/clips/{clip_id}")
async def download_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    try:
        print(f"[DownloadsRoute] Request to download clip: {clip_id}")
        supabase = get_client()
        result = supabase.table("clips").select("*").eq("id", clip_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Clip not found")

        clip = result.data[0]

        # Verify ownership via parent job
        job_id = clip.get("job_id")
        if job_id:
            job_check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
            if not job_check.data:
                raise HTTPException(status_code=404, detail="Clip not found")

        file_url = clip.get("file_url")

        if not file_url:
            raise HTTPException(status_code=404, detail="Video file URL not found")

        # ORTA-5: Stream from R2 instead of redirecting to public URL
        async def stream_clip():
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("GET", file_url) as r:
                    r.raise_for_status()
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        yield chunk

        return StreamingResponse(
            stream_clip(),
            media_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="clip_{clip_id[:8]}.mp4"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DownloadsRoute] Error downloading clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/jobs/{job_id}/all")
async def download_all_clips(job_id: str, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    try:
        print(f"[DownloadsRoute] Request to download all clips for job: {job_id}")
        supabase = get_client()

        # Verify job ownership
        job_check = supabase.table("jobs").select("id").eq("id", job_id).eq("user_id", current_user["id"]).execute()
        if not job_check.data:
            raise HTTPException(status_code=404, detail="Job not found")

        result = supabase.table("clips").select("*").eq("job_id", job_id).order("posting_order").execute()

        clips = [c for c in result.data if c.get("video_landscape_path") is not None]

        if not clips:
            raise HTTPException(status_code=404, detail="No clips found")

        fd, zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)

        added_count = 0
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for clip in clips:
                    video_path = clip.get("video_landscape_path")
                    if video_path and os.path.exists(video_path):
                        posting_order = clip.get("posting_order", 0)
                        content_type = clip.get("content_type", "video")
                        arcname = f"clip_{posting_order:02d}_{content_type}.mp4"
                        zipf.write(video_path, arcname=arcname)
                        added_count += 1

            if added_count == 0:
                cleanup_temp_file(zip_path)
                raise HTTPException(status_code=404, detail="No clip files found on disk")

            filename = f"job_{job_id[:8]}_clips.zip"
            print(f"[DownloadsRoute] Serving ZIP with {added_count} clips as {filename}")

            background_tasks.add_task(cleanup_temp_file, zip_path)

            return FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=filename
            )

        except HTTPException:
            raise
        except Exception as e:
            cleanup_temp_file(zip_path)
            raise e

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DownloadsRoute] Error downloading all clips for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
