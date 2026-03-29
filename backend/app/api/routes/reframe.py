"""
Reframe API endpoints.

POST /reframe/upload                       → upload video, returns local_path
POST /reframe/process                      → start async job, returns reframe_job_id
GET  /reframe/status/{reframe_job_id}      → poll progress + result
GET  /reframe/metadata/{job_id}/{clip_id}  → pipeline-to-editor bridge
"""

import os
import uuid
import threading
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel

from app.reframe.processor import run_reframe
from app.config import settings
from app.middleware.auth import get_current_user
from app.services.supabase_client import get_client

router = APIRouter(prefix="/reframe", tags=["reframe"])

# ── Stale job threshold: jobs stuck in 'processing' for >15 min are marked error ──
_STALE_MINUTES = 15


# ── Request / Response models ──────────────────────────────────────────────────

class ReframeRequest(BaseModel):
    clip_url: Optional[str] = None
    clip_local_path: Optional[str] = None   # returned by /reframe/upload
    clip_id: Optional[str] = None
    job_id: Optional[str] = None            # pipeline job_id → diarization lookup
    clip_start: float = 0.0
    clip_end: Optional[float] = None
    strategy: str = "podcast"
    aspect_ratio: str = "9:16"
    tracking_mode: str = "x_only"


class ReframeStatusResponse(BaseModel):
    status: str                             # queued | processing | done | error
    step: str
    percent: int
    keyframes: Optional[List[dict]] = None
    scene_cuts: Optional[List[float]] = None
    src_w: Optional[int] = None
    src_h: Optional[int] = None
    fps: Optional[float] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _update_job(reframe_job_id: str, **fields) -> None:
    """Write progress/result fields to reframe_jobs row. Never raises."""
    try:
        get_client().table("reframe_jobs").update(fields).eq("id", reframe_job_id).execute()
    except Exception as e:
        print(f"[ReframeRoute] Supabase update failed for job {reframe_job_id}: {e}")


def _allowed_aspect_ratio(value: str) -> str:
    allowed = {"9:16", "1:1", "4:5", "16:9"}
    return value if value in allowed else "9:16"


def _allowed_tracking_mode(value: str) -> str:
    return value if value in {"x_only", "dynamic_xy"} else "x_only"


def _allowed_strategy(value: str) -> str:
    return value if value in {"podcast"} else "podcast"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_reframe_video(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a video file for reframing.
    Returns {"local_path": "..."} — pass this to POST /reframe/process.
    File is cleaned up automatically after the processor finishes.
    """
    try:
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temp_id = uuid.uuid4().hex
        ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"

        # Sanitize extension
        if ext not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
            ext = ".mp4"

        save_path = str(settings.UPLOAD_DIR / f"reframe_upload_{temp_id}{ext}")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        with open(save_path, "wb") as f:
            f.write(content)

        print(f"[ReframeUpload] Saved {len(content):,} bytes → {save_path}")
        return {"local_path": save_path}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ReframeUpload] Error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


@router.post("/process", status_code=201)
async def start_reframe(
    req: ReframeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Start a reframe job in the background.
    Returns {"reframe_job_id": "..."} immediately.
    Poll GET /reframe/status/{id} for progress.
    """
    if not req.clip_url and not req.clip_local_path:
        raise HTTPException(
            status_code=400,
            detail="Provide clip_url or clip_local_path"
        )

    # Validate / sanitize options
    strategy = _allowed_strategy(req.strategy)
    aspect_ratio = _allowed_aspect_ratio(req.aspect_ratio)
    tracking_mode = _allowed_tracking_mode(req.tracking_mode)
    user_id = current_user["id"]

    # Create job row in Supabase — this is the source of truth from now on
    try:
        row = {
            "user_id": user_id,
            "status": "queued",
            "step": "Queued",
            "percent": 0,
            "clip_url": req.clip_url,
            "clip_local_path": req.clip_local_path,
            "clip_id": req.clip_id,
            "job_id": req.job_id,
            "clip_start": req.clip_start,
            "clip_end": req.clip_end,
            "strategy": strategy,
            "aspect_ratio": aspect_ratio,
            "tracking_mode": tracking_mode,
        }
        resp = get_client().table("reframe_jobs").insert(row).execute()
        if not resp.data:
            raise RuntimeError("DB insert returned no data")
        reframe_job_id = resp.data[0]["id"]
    except Exception as e:
        print(f"[ReframeRoute] Failed to create job row: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reframe job")

    def _run():
        try:
            _update_job(reframe_job_id, status="processing", step="Starting...", percent=0)

            def on_progress(step: str, pct: int):
                _update_job(reframe_job_id, step=step, percent=pct)

            result = run_reframe(
                clip_url=req.clip_url,
                clip_local_path=req.clip_local_path,
                clip_id=req.clip_id,
                job_id=req.job_id,
                clip_start=req.clip_start,
                clip_end=req.clip_end,
                strategy=strategy,
                aspect_ratio=aspect_ratio,
                tracking_mode=tracking_mode,
                on_progress=on_progress,
            )

            _update_job(
                reframe_job_id,
                status="done",
                step="Done!",
                percent=100,
                keyframes=result.keyframes,
                scene_cuts=result.scene_cuts,
                src_w=result.src_w,
                src_h=result.src_h,
                fps=result.fps,
                duration_s=result.duration_s,
                error=None,
            )
            print(f"[ReframeRoute] Job {reframe_job_id} completed OK")

        except Exception as e:
            print(f"[ReframeRoute] Job {reframe_job_id} failed: {e}")
            _update_job(
                reframe_job_id,
                status="error",
                step="Failed",
                percent=0,
                error=str(e)[:500],
            )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"reframe_job_id": reframe_job_id}


@router.get("/status/{reframe_job_id}", response_model=ReframeStatusResponse)
async def get_reframe_status(
    reframe_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Poll progress and result of a reframe job.
    Returns 404 if job not found, 403 if owned by another user.
    Stale jobs (processing for >15 min) are auto-marked as error.
    """
    try:
        resp = (
            get_client()
            .table("reframe_jobs")
            .select("*")
            .eq("id", reframe_job_id)
            .execute()
        )
    except Exception as e:
        print(f"[ReframeRoute] Supabase status query error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    if not resp.data:
        raise HTTPException(status_code=404, detail="Reframe job not found")

    job = resp.data[0]

    # Ownership check — prevent user B from polling user A's job
    if str(job.get("user_id")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Access denied")

    # Stale job detection: stuck in processing for >15 minutes
    if job.get("status") == "processing":
        from datetime import datetime, timezone, timedelta
        updated_at_str = job.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at < datetime.now(timezone.utc) - timedelta(minutes=_STALE_MINUTES):
                    _update_job(
                        reframe_job_id,
                        status="error",
                        step="Timed out",
                        error="Job timed out — server restart likely. Please try again.",
                    )
                    job["status"] = "error"
                    job["step"] = "Timed out"
                    job["error"] = "Job timed out — server restart likely. Please try again."
            except Exception:
                pass

    return ReframeStatusResponse(
        status=job.get("status", "error"),
        step=job.get("step", ""),
        percent=job.get("percent", 0),
        keyframes=job.get("keyframes"),
        scene_cuts=job.get("scene_cuts"),
        src_w=job.get("src_w"),
        src_h=job.get("src_h"),
        fps=job.get("fps"),
        duration_s=job.get("duration_s"),
        error=job.get("error"),
    )


@router.get("/metadata/{job_id}/{clip_id}")
async def get_reframe_metadata(
    job_id: str,
    clip_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Pipeline-to-editor bridge.
    Returns pre-computed reframe data stored by the pipeline after export.
    Called by the editor when opened via ?clipJobId= URL parameter.
    Returns 404 if no reframe metadata has been generated for this clip yet.
    """
    try:
        resp = (
            get_client()
            .table("reframe_metadata")
            .select("*")
            .eq("job_id", job_id)
            .eq("clip_id", clip_id)
            .execute()
        )
    except Exception as e:
        print(f"[ReframeRoute] Metadata query error: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    if not resp.data:
        raise HTTPException(
            status_code=404,
            detail="No reframe metadata found for this clip"
        )

    row = resp.data[0]
    return {
        "scene_cuts": row.get("scene_cuts", []),
        "speaker_segments": row.get("speaker_segments", []),
        "face_positions": row.get("face_positions", []),
        "keyframes": row.get("keyframes", []),
        "src_w": row.get("src_w"),
        "src_h": row.get("src_h"),
        "fps": row.get("fps"),
        "duration_s": row.get("duration_s"),
        "strategy": row.get("strategy", "podcast"),
        "aspect_ratio": row.get("aspect_ratio", "9:16"),
    }
