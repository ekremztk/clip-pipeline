"""
Prognot GPU Reframe Server — standalone FastAPI service.

Receives reframe jobs from Railway via POST /run, processes them using
the existing reframe pipeline (with CUDA-enabled YOLOv8 when available),
and writes progress + results directly to Supabase.

Railway never sends video bytes — the GPU server downloads from clip_url itself.

Required env vars:
    SUPABASE_URL            Supabase project URL
    SUPABASE_SERVICE_KEY    Supabase service role key
    GEMINI_API_KEY          Gemini Developer API key
    GCP_PROJECT             GCP project ID (for Vertex AI / GCS)
    GCP_CREDENTIALS_JSON    GCP service account JSON (single-line, \\n escaped)
    GPU_SECRET              Shared secret checked via X-Gpu-Secret header (optional)
    UPLOAD_DIR              Directory for temp video downloads (default: /tmp/reframe_uploads)

Optional env vars (inherited from backend config):
    GEMINI_MODEL_PRO        Override Gemini Pro model name
    GCS_BUCKET_NAME         GCS bucket for large video uploads
    R2_BUCKET_NAME          R2 bucket for debug video uploads
    R2_PUBLIC_URL           R2 public base URL
    R2_ACCESS_KEY_ID        R2 credentials
    R2_SECRET_ACCESS_KEY    R2 credentials
    R2_ACCOUNT_ID           Cloudflare account ID

Launch:
    bash gpu_server/start.sh
"""
import os
import sys
import threading
from typing import Optional

# ── Python path: add backend/ so we can import app.* ─────────────────────────
# Works whether launched from repo root, gpu_server/, or via start.sh.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
_BACKEND_DIR = os.path.join(_REPO_ROOT, "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.reframe.pipeline import run_reframe
from app.reframe.types import ReframeKeyframe
from app.services.supabase_client import get_client

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Prognot GPU Reframe Server", version="1.0.0")

# Shared secret between Railway and this server.
# Set GPU_SECRET on both sides. If empty, auth is skipped (dev only).
_GPU_SECRET = os.getenv("GPU_SECRET", "")


# ── Request model ─────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    reframe_job_id: str
    clip_url: str                               # R2/CDN URL — server downloads this itself
    clip_id: Optional[str] = None              # Supabase clip UUID
    job_id: Optional[str] = None               # Pipeline job UUID for diarization lookup
    clip_start: float = 0.0
    clip_end: Optional[float] = None
    strategy: str = "auto"
    aspect_ratio: str = "9:16"
    tracking_mode: str = "dynamic_xy"
    content_type_hint: Optional[str] = None
    detection_engine: str = "yolo"             # "yolo" uses CUDA when torch+CUDA available
    debug_mode: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update_job(reframe_job_id: str, **fields) -> None:
    """Write job progress or result to Supabase. Never raises."""
    try:
        get_client().table("reframe_jobs").update(fields).eq("id", reframe_job_id).execute()
    except Exception as e:
        print(f"[GPUServer] Supabase update error (job={reframe_job_id}): {e}")


def _keyframes_to_dicts(keyframes: list[ReframeKeyframe]) -> list[dict]:
    """Convert ReframeKeyframe dataclass list to JSON-serializable dicts."""
    return [
        {
            "time_s": kf.time_s,
            "offset_x": kf.offset_x,
            "offset_y": kf.offset_y,
            "interpolation": kf.interpolation,
        }
        for kf in keyframes
    ]


def _process_job(req: RunRequest) -> None:
    """
    Background thread: runs the full reframe pipeline and writes results to Supabase.
    Mirrors the _run() closure in backend/app/api/routes/reframe.py exactly.
    """
    try:
        _update_job(req.reframe_job_id, status="processing", step="Starting...", percent=0)

        def on_progress(step: str, pct: int) -> None:
            _update_job(req.reframe_job_id, step=step, percent=pct)

        result = run_reframe(
            clip_url=req.clip_url,
            clip_local_path=None,           # GPU server always fetches from clip_url
            clip_id=req.clip_id,
            job_id=req.job_id,
            clip_start=req.clip_start,
            clip_end=req.clip_end,
            strategy=req.strategy,
            aspect_ratio=req.aspect_ratio,
            tracking_mode=req.tracking_mode,
            content_type_hint=req.content_type_hint,
            detection_engine=req.detection_engine,
            on_progress=on_progress,
            debug_mode=req.debug_mode,
        )

        keyframes_dicts = _keyframes_to_dicts(result.keyframes)

        _update_job(
            req.reframe_job_id,
            status="done",
            step="Done!",
            percent=100,
            keyframes=keyframes_dicts,
            scene_cuts=result.scene_cuts,
            src_w=result.src_w,
            src_h=result.src_h,
            fps=result.fps,
            duration_s=result.duration_s,
            pipeline_metadata=result.metadata,
            error=None,
        )
        print(
            f"[GPUServer] Job {req.reframe_job_id} complete — "
            f"{len(result.keyframes)} keyframes, type={result.content_type}"
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[GPUServer] Job {req.reframe_job_id} failed: {e}")
        _update_job(
            req.reframe_job_id,
            status="error",
            step="Failed",
            percent=0,
            error=str(e)[:500],
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check — Railway and load balancers poll this."""
    return {"status": "ok", "service": "gpu-reframe-server"}


@app.post("/run", status_code=202)
def start_reframe_job(
    req: RunRequest,
    x_gpu_secret: Optional[str] = Header(None),
):
    """
    Accept a reframe job and process it in a background thread.
    Returns immediately (202 Accepted). Progress + result are written to Supabase.

    Railway sends X-Gpu-Secret header matching the GPU_SECRET env var.
    """
    if _GPU_SECRET and x_gpu_secret != _GPU_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Gpu-Secret header")

    thread = threading.Thread(target=_process_job, args=(req,), daemon=True)
    thread.start()

    print(f"[GPUServer] Accepted job {req.reframe_job_id} (engine={req.detection_engine})")
    return {"reframe_job_id": req.reframe_job_id, "status": "accepted"}
