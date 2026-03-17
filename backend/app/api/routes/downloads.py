import os
import zipfile
import tempfile
import pathlib
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from app.services.supabase_client import get_client

router = APIRouter(prefix="/downloads", tags=["downloads"])

def cleanup_temp_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
            print(f"[DownloadsRoute] Cleaned up temporary file: {path}")
    except Exception as e:
        print(f"[DownloadsRoute] Error cleaning up temp file: {e}")

@router.get("/clips/{clip_id}")
async def download_clip(clip_id: str):
    try:
        print(f"[DownloadsRoute] Request to download clip: {clip_id}")
        supabase = get_client()
        result = supabase.table("clips").select("*").eq("id", clip_id).execute()
        
        if not result.data:
            print(f"[DownloadsRoute] Clip not found: {clip_id}")
            raise HTTPException(status_code=404, detail="Clip not found")
            
        clip = result.data[0]
        file_url = clip.get("file_url")
        
        if not file_url:
            print(f"[DownloadsRoute] File URL not found for clip {clip_id}")
            raise HTTPException(status_code=404, detail="Video file URL not found")
            
        return RedirectResponse(url=file_url)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DownloadsRoute] Error downloading clip {clip_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}/all")
async def download_all_clips(job_id: str, background_tasks: BackgroundTasks):
    try:
        print(f"[DownloadsRoute] Request to download all clips for job: {job_id}")
        supabase = get_client()
        
        # Query clips table WHERE job_id = job_id AND video_landscape_path IS NOT NULL
        # ORDER BY posting_order
        result = supabase.table("clips").select("*").eq("job_id", job_id).order("posting_order").execute()
        
        clips = [c for c in result.data if c.get("video_landscape_path") is not None]
        
        if not clips:
            print(f"[DownloadsRoute] No clips found for job: {job_id}")
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
                print(f"[DownloadsRoute] No clip files found on disk for job: {job_id}")
                cleanup_temp_file(zip_path)
                raise HTTPException(status_code=404, detail="No clip files found on disk")
                
            filename = f"job_{job_id[:8]}_clips.zip"
            print(f"[DownloadsRoute] Serving ZIP {zip_path} with {added_count} clips as {filename}")
            
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
        raise HTTPException(status_code=500, detail=str(e))
