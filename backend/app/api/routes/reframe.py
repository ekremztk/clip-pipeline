"""
Reframe API endpoints.
POST /reframe/upload         → upload a video file, returns local_path
POST /reframe/process        → start async reframe job, returns job_id
GET  /reframe/status/{id}    → poll progress + keyframes when done
"""

import os
import uuid
import threading
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel

from app.reframe.processor import run_reframe
from app.config import settings
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/reframe", tags=["reframe"])

# In-memory job store (per-process, resets on restart)
_jobs: dict[str, dict] = {}


class ReframeRequest(BaseModel):
    clip_url: Optional[str] = None
    clip_local_path: Optional[str] = None   # from /reframe/upload
    clip_id: Optional[str] = None
    job_id: Optional[str] = None
    clip_start: float = 0.0
    clip_end: Optional[float] = None


class ReframeStatusResponse(BaseModel):
    status: str          # "processing" | "done" | "error"
    step: str
    percent: int
    keyframes: Optional[list] = None
    src_w: Optional[int] = None
    src_h: Optional[int] = None
    error: Optional[str] = None


@router.post("/upload")
async def upload_reframe_video(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """
    Upload a video file for reframing.
    Returns {"local_path": "..."} to pass to /reframe/process.
    The file is cleaned up automatically after processing.
    """
    try:
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temp_id = uuid.uuid4().hex
        ext = Path(file.filename or "video.mp4").suffix or ".mp4"
        save_path = str(settings.UPLOAD_DIR / f"reframe_upload_{temp_id}{ext}")

        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        print(f"[ReframeUpload] Saved {len(content)} bytes → {save_path}")
        return {"local_path": save_path}

    except Exception as e:
        print(f"[ReframeUpload] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process")
async def start_reframe(req: ReframeRequest, current_user: dict = Depends(get_current_user)):
    """
    Start a reframe job in the background.
    Returns {"reframe_job_id": "..."} immediately.
    Pass either clip_url (remote HTTP URL) or clip_local_path (from /reframe/upload).
    """
    if not req.clip_url and not req.clip_local_path:
        raise HTTPException(status_code=400, detail="Provide clip_url or clip_local_path")

    reframe_job_id = str(uuid.uuid4())
    _jobs[reframe_job_id] = {
        "status": "processing",
        "step": "Starting...",
        "percent": 0,
        "keyframes": None,
        "src_w": None,
        "src_h": None,
        "error": None,
    }

    def run():
        try:
            def on_progress(step: str, pct: int):
                _jobs[reframe_job_id]["step"] = step
                _jobs[reframe_job_id]["percent"] = pct

            result = run_reframe(
                clip_url=req.clip_url,
                clip_local_path=req.clip_local_path,
                clip_id=req.clip_id,
                job_id=req.job_id,
                clip_start=req.clip_start,
                clip_end=req.clip_end,
                on_progress=on_progress,
            )

            _jobs[reframe_job_id]["status"] = "done"
            _jobs[reframe_job_id]["step"] = "Done!"
            _jobs[reframe_job_id]["percent"] = 100
            _jobs[reframe_job_id]["keyframes"] = result["keyframes"]
            _jobs[reframe_job_id]["src_w"] = result["src_w"]
            _jobs[reframe_job_id]["src_h"] = result["src_h"]

        except Exception as e:
            print(f"[ReframeRoute] Job {reframe_job_id} failed: {e}")
            _jobs[reframe_job_id]["status"] = "error"
            _jobs[reframe_job_id]["step"] = "Failed"
            _jobs[reframe_job_id]["error"] = str(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    return {"reframe_job_id": reframe_job_id}


@router.get("/status/{reframe_job_id}", response_model=ReframeStatusResponse)
async def get_reframe_status(reframe_job_id: str, current_user: dict = Depends(get_current_user)):
    """Poll progress and result of a reframe job."""
    job = _jobs.get(reframe_job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Reframe job not found")

    return ReframeStatusResponse(
        status=job["status"],
        step=job["step"],
        percent=job["percent"],
        keyframes=job.get("keyframes"),
        src_w=job.get("src_w"),
        src_h=job.get("src_h"),
        error=job.get("error"),
    )
