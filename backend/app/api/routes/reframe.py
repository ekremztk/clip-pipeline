"""
Reframe API endpoint.
POST /reframe/process  → starts async reframe job, returns job_id
GET  /reframe/status/{job_id} → returns progress + keyframes when done
"""

import uuid
import threading
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.reframe.processor import run_reframe

router = APIRouter(prefix="/reframe", tags=["reframe"])

# In-memory job store (per-process, resets on restart)
_jobs: dict[str, dict] = {}


class ReframeRequest(BaseModel):
    clip_url: str
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


@router.post("/process")
async def start_reframe(req: ReframeRequest):
    """
    Start a reframe job in the background.
    Returns {"reframe_job_id": "..."} immediately.
    """
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
async def get_reframe_status(reframe_job_id: str):
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
