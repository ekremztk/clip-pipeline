# rebuilt 2026-04-10
# gaming-pipeline-v1
"""
Prognot Reframe — Modal GPU Worker.

Runs run_reframe() from backend/app/reframe/pipeline.py on an A10G GPU.
Writes progress + results directly to Supabase (same schema as the Railway route
and gpu_server/main.py).

Deploy:
    modal deploy gpu_server/modal_worker.py

Invoke remotely (from Railway or anywhere):
    modal run gpu_server/modal_worker.py \\
        --payload '{"reframe_job_id": "<uuid>", "clip_url": "<url>", ...}'

Required Modal secret (create once via `modal secret create prognot-reframe-secrets`):
    SUPABASE_URL
    SUPABASE_SERVICE_KEY
    GEMINI_API_KEY
    GCP_CREDENTIALS_JSON   single-line JSON of GCP service account (store as-is from the .json file)
    GCP_PROJECT            GCP project ID
    GCP_LOCATION           Vertex AI region (e.g. us-central1)
    GCS_BUCKET_NAME        GCS bucket used for large video uploads to Gemini
    ANTHROPIC_API_KEY      only needed if debug_mode=True and debug analyzer runs
    R2_BUCKET_NAME         only needed if debug_mode=True
    R2_PUBLIC_URL
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_ACCOUNT_ID
"""
import os
import sys
from pathlib import Path
from typing import Optional

import modal

# ─── Paths ────────────────────────────────────────────────────────────────────

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parent
_BACKEND_DIR = _REPO_ROOT / "backend"

# ─── Modal Image ──────────────────────────────────────────────────────────────

# System packages required by ffmpeg, OpenCV, MediaPipe, and YOLO
_APT_PACKAGES = [
    "ffmpeg",
    "libgl1",
    "libglib2.0-0",
    "libsm6",
    "libxext6",
    "libxrender-dev",
    "libgomp1",         # OpenMP (YOLO / numpy parallel ops)
    "libgcc-s1",
]

# Python packages — mirrors backend/requirements.txt, web-server deps excluded
_PIP_PACKAGES = [
    # Core utilities
    "python-dotenv",
    "requests",
    "httpx>=0.27.0",
    "pydantic>=2.0",
    # Database / storage
    "supabase",
    "boto3",
    "google-cloud-storage",
    # AI / models
    "google-genai",
    "anthropic",
    # Video / vision
    "numpy",
    "Pillow",
    "opencv-python-headless",
    "mediapipe>=0.10.0",
    "ultralytics>=8.1.0",   # YOLOv8 — yolov8l.pt pre-downloaded at image build time
]

image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"CACHE_DATE": "2026-04-10_gaming-v4-custom-yolo"})
    .apt_install(_APT_PACKAGES)
    .pip_install(_PIP_PACKAGES)
    # Pre-download yolov8l-face.pt (face-specific model) at image build time.
    # Source: HuggingFace arnabdhar/YOLOv8-Face-Detection (requests already installed)
    .run_commands(
        "python -c \""
        "import requests, os; "
        "url = 'https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt'; "
        "print('[Modal build] Downloading face model from HuggingFace...'); "
        "r = requests.get(url, stream=True, timeout=300); r.raise_for_status(); "
        "open('/root/yolov8l-face.pt', 'wb').write(r.content); "
        "from ultralytics import YOLO; m = YOLO('/root/yolov8l-face.pt'); "
        "sz = os.path.getsize('/root/yolov8l-face.pt') / 1024 / 1024; "
        "print(f'[Modal build] yolov8l-face.pt ready size={sz:.1f}MB')"
        "\""
    )
    # Include backend source tree at /backend inside the container.
    # copy=True bakes it into the image layer (required for GPU functions).
    .add_local_dir(str(_BACKEND_DIR), remote_path="/backend", copy=True)
    # Custom webcam-detection model — baked in at deploy time.
    # Local path: ~/Documents/prognot-webcam.pt
    .add_local_file(
        str(Path.home() / "Documents" / "prognot-webcam.pt"),
        remote_path="/root/prognot-webcam.pt",
        copy=True,
    )
)

# ─── Modal App ────────────────────────────────────────────────────────────────

app = modal.App("prognot-reframe")

# ─── GPU Function ─────────────────────────────────────────────────────────────

@app.function(
    image=image,
    gpu="A10G",
    secrets=[
        modal.Secret.from_name("prognot-reframe-secrets"),
        modal.Secret.from_name("langfuse-secrets"),  # Gemini token cost tracking
    ],
    timeout=1800,       # 30 minutes — long videos with Gemini analysis can be slow
    memory=8192,        # 8 GB RAM
    retries=0,          # no auto-retry; caller decides whether to requeue
)
def process_reframe(payload: dict) -> dict:
    """
    GPU-accelerated reframe pipeline.

    Payload keys:
        reframe_job_id  str   required — Supabase reframe_jobs row to update
        clip_url        str   required — R2/CDN URL; container downloads the video
        clip_id         str   optional — Supabase clip UUID
        job_id          str   optional — pipeline job UUID (loads diarization)
        clip_start      float default 0.0
        clip_end        float default None (full clip)
        strategy        str   default "auto"
        aspect_ratio    str   default "9:16"
        tracking_mode   str   default "dynamic_xy"
        content_type_hint str default None
        detection_engine  str default "yolo" (uses CUDA on A10G)
        debug_mode      bool  default False

    Returns a summary dict. Full result is written to Supabase reframe_jobs.
    """
    # ── 1. Add backend to Python path ─────────────────────────────────────────
    if "/backend" not in sys.path:
        sys.path.insert(0, "/backend")

    # ── 2. Set writable UPLOAD_DIR before config module loads ─────────────────
    _upload_dir = "/tmp/reframe_uploads"
    os.makedirs(_upload_dir, exist_ok=True)

    # ── 2b. Normalize GCP_CREDENTIALS_JSON before any import touches it ───────
    # Modal secret injection can corrupt the private_key PEM block with CRLF,
    # literal two-char \n, or bare \r. cryptography >= 42 uses a strict Rust
    # base64 parser that rejects ANY stray byte. We rebuild the PEM from
    # scratch: extract base64 content, strip non-base64 chars, re-wrap at 64.
    _gcp_raw = os.environ.get("GCP_CREDENTIALS_JSON", "")
    if _gcp_raw:
        import json as _json
        import re as _re
        try:
            _creds = _json.loads(_gcp_raw)
        except Exception:
            # JSON is malformed — likely real newlines inside the string value.
            # Collapse them so json.loads can parse it.
            _gcp_raw = _gcp_raw.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
            _creds = _json.loads(_gcp_raw)
        if "private_key" in _creds:
            pk = _creds["private_key"]
            pk = pk.replace("\\n", "\n")   # literal \n two-chars → real newline
            pk = pk.replace("\r", "")      # strip all CR
            _lines = [l.strip() for l in pk.strip().split("\n") if l.strip()]
            if len(_lines) >= 3 and _lines[0].startswith("-----BEGIN") and _lines[-1].startswith("-----END"):
                _header = _lines[0]
                _footer = _lines[-1]
                _raw_b64 = "".join(_lines[1:-1])
                _clean_b64 = _re.sub(r"[^A-Za-z0-9+/=]", "", _raw_b64)
                _wrapped = "\n".join(_clean_b64[i:i+64] for i in range(0, len(_clean_b64), 64))
                pk = f"{_header}\n{_wrapped}\n{_footer}\n"
            _creds["private_key"] = pk
        os.environ["GCP_CREDENTIALS_JSON"] = _json.dumps(_creds)
        del _json, _re, _creds, _gcp_raw

    # ── 3. Deferred imports (path + env must be ready first) ──────────────────
    from app.reframe.pipeline import run_reframe
    from app.reframe.types import ReframeKeyframe
    from app.services.supabase_client import get_client
    from app.config import settings

    # Patch UPLOAD_DIR so pipeline writes temp files to /tmp (writable in Modal)
    settings.UPLOAD_DIR = Path(_upload_dir)

    # ── 4. Parse payload ──────────────────────────────────────────────────────
    reframe_job_id: str = payload["reframe_job_id"]
    clip_url: Optional[str] = payload.get("clip_url")
    clip_id: Optional[str] = payload.get("clip_id")
    job_id: Optional[str] = payload.get("job_id")
    clip_start: float = float(payload.get("clip_start", 0.0))
    clip_end: Optional[float] = payload.get("clip_end")
    if clip_end is not None:
        clip_end = float(clip_end)
    strategy: str = payload.get("strategy", "auto")
    aspect_ratio: str = payload.get("aspect_ratio", "9:16")
    tracking_mode: str = payload.get("tracking_mode", "dynamic_xy")
    content_type_hint: Optional[str] = payload.get("content_type_hint")
    detection_engine: str = payload.get("detection_engine", "yolo")
    debug_mode: bool = bool(payload.get("debug_mode", False))

    # ── 5. Supabase helpers ────────────────────────────────────────────────────

    def _update_job(**fields) -> None:
        """Write progress or result to Supabase reframe_jobs. Never raises."""
        try:
            get_client().table("reframe_jobs").update(fields).eq("id", reframe_job_id).execute()
        except Exception as exc:
            print(f"[ModalWorker] Supabase update error (job={reframe_job_id}): {exc}")

    def _keyframes_to_dicts(keyframes: list[ReframeKeyframe]) -> list[dict]:
        return [
            {
                "time_s": kf.time_s,
                "offset_x": kf.offset_x,
                "offset_y": kf.offset_y,
                "interpolation": kf.interpolation,
            }
            for kf in keyframes
        ]

    # ── 6. Run pipeline ────────────────────────────────────────────────────────
    try:
        _update_job(status="processing", step="Starting...", percent=0)

        def on_progress(step: str, pct: int) -> None:
            _update_job(step=step, percent=pct)

        result = run_reframe(
            clip_url=clip_url,
            clip_local_path=None,           # Modal always fetches from clip_url
            clip_id=clip_id,
            job_id=job_id,
            clip_start=clip_start,
            clip_end=clip_end,
            strategy=strategy,
            aspect_ratio=aspect_ratio,
            tracking_mode=tracking_mode,
            content_type_hint=content_type_hint,
            detection_engine=detection_engine,
            on_progress=on_progress,
            debug_mode=debug_mode,
        )

        keyframes_dicts = _keyframes_to_dicts(result.keyframes)
        debug_url = result.metadata.get("debug_video_url", "") if debug_mode else ""
        done_step = f"Done! Debug: {debug_url}" if debug_url else "Done!"

        _update_job(
            status="done",
            step=done_step,
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
            f"[ModalWorker] Job {reframe_job_id} complete — "
            f"{len(result.keyframes)} keyframes, {len(result.scene_cuts)} cuts, "
            f"type={result.content_type}"
        )

        return {
            "status": "done",
            "reframe_job_id": reframe_job_id,
            "keyframe_count": len(result.keyframes),
            "scene_cut_count": len(result.scene_cuts),
            "content_type": result.content_type,
        }

    except Exception as exc:
        import traceback
        error_msg = str(exc)[:500]
        print(f"[ModalWorker] Job {reframe_job_id} failed: {exc}")
        traceback.print_exc()

        _update_job(
            status="error",
            step="Failed",
            percent=0,
            error=error_msg,
        )

        return {
            "status": "error",
            "reframe_job_id": reframe_job_id,
            "error": error_msg,
        }


# ─── Local entrypoint ─────────────────────────────────────────────────────────
# modal run gpu_server/modal_worker.py --payload '{"reframe_job_id": "...", ...}'

@app.local_entrypoint()
def main(payload: str = ""):
    """
    Smoke-test entrypoint.

    Usage:
        TEST_JOB_ID=<uuid> TEST_CLIP_URL=<url> modal run gpu_server/modal_worker.py
    Or pass --payload as JSON string:
        modal run gpu_server/modal_worker.py --payload '{"reframe_job_id": "...", "clip_url": "..."}'
    """
    import json

    if payload:
        job_payload = json.loads(payload)
    else:
        job_id = os.environ.get("TEST_JOB_ID")
        clip_url = os.environ.get("TEST_CLIP_URL")
        if not job_id or not clip_url:
            print(
                "Provide TEST_JOB_ID and TEST_CLIP_URL env vars, or pass --payload as JSON.\n"
                "  TEST_JOB_ID=<uuid> TEST_CLIP_URL=<url> modal run gpu_server/modal_worker.py"
            )
            return
        job_payload = {
            "reframe_job_id": job_id,
            "clip_url": clip_url,
            "aspect_ratio": "9:16",
            "tracking_mode": "dynamic_xy",
            "detection_engine": "yolo",
        }

    print(f"[ModalWorker] Submitting job: {job_payload['reframe_job_id']}")
    result = process_reframe.remote(job_payload)
    print(f"[ModalWorker] Result: {result}")
