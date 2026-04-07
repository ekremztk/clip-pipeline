"""
Reframe V2 API endpoints.

POST /reframe/upload                       → video yükle, local_path döndür
POST /reframe/process                      → async job başlat, reframe_job_id döndür
GET  /reframe/status/{reframe_job_id}      → polling — ilerleme + sonuç
GET  /reframe/metadata/{job_id}/{clip_id}  → pipeline-editor köprüsü
"""
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.middleware.auth import get_current_user
from app.reframe.types import ReframeKeyframe
from app.reframe.pipeline import run_reframe
from app.services.supabase_client import get_client

router = APIRouter(prefix="/reframe", tags=["reframe"])

# Stale job threshold: 15 dakikadan uzun süren job'lar otomatik hata olarak işaretlenir
_STALE_MINUTES = 15

# Geçerli değerler
_VALID_ASPECT_RATIOS = {"9:16", "1:1", "4:5", "16:9"}
_VALID_TRACKING_MODES = {"x_only", "dynamic_xy"}
_VALID_CONTENT_TYPES = {"auto", "podcast", "single", "gaming", "generic"}
_VALID_DETECTION_ENGINES = {"mediapipe", "yolo"}


# ─── Request / Response Modelleri ─────────────────────────────────────────────

class ReframeRequest(BaseModel):
    clip_url: Optional[str] = None
    clip_local_path: Optional[str] = None      # /reframe/upload'dan dönen yol
    clip_id: Optional[str] = None
    job_id: Optional[str] = None               # Pipeline job_id → diarization verisi
    clip_start: float = 0.0
    clip_end: Optional[float] = None
    strategy: str = "podcast"                  # Geriye dönük uyumluluk için korundu
    aspect_ratio: str = "9:16"
    tracking_mode: str = "dynamic_xy"
    content_type: Optional[str] = None        # "auto" | "podcast" | "single" | "gaming" | "generic"
    detection_engine: Optional[str] = "mediapipe"  # "mediapipe" | "yolo"


class ReframeStatusResponse(BaseModel):
    status: str                                # queued | processing | done | error
    step: str
    percent: int
    keyframes: Optional[list[dict]] = None
    scene_cuts: Optional[list[float]] = None
    src_w: Optional[int] = None
    src_h: Optional[int] = None
    fps: Optional[float] = None
    duration_s: Optional[float] = None
    content_type: Optional[str] = None        # YENİ: tespit edilen içerik türü
    tracking_mode: Optional[str] = None       # YENİ: kullanılan tracking modu
    error: Optional[str] = None


# ─── Yardımcılar ──────────────────────────────────────────────────────────────

def _update_job(reframe_job_id: str, **fields) -> None:
    """Supabase reframe_jobs satırını güncelle. Hiçbir zaman exception fırlatmaz."""
    try:
        get_client().table("reframe_jobs").update(fields).eq("id", reframe_job_id).execute()
    except Exception as e:
        print(f"[ReframeRoute] Supabase update hatası (job={reframe_job_id}): {e}")


def _sanitize_aspect_ratio(value: str) -> str:
    return value if value in _VALID_ASPECT_RATIOS else "9:16"


def _sanitize_tracking_mode(value: str) -> str:
    return value if value in _VALID_TRACKING_MODES else "dynamic_xy"


def _sanitize_content_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value if value in _VALID_CONTENT_TYPES else None


def _sanitize_detection_engine(value: Optional[str]) -> str:
    if not value:
        return "mediapipe"
    return value if value in _VALID_DETECTION_ENGINES else "mediapipe"


def _keyframes_to_dicts(keyframes: list[ReframeKeyframe]) -> list[dict]:
    """ReframeKeyframe dataclass'larını JSON-serializable dict'lere çevir."""
    return [
        {
            "time_s": kf.time_s,
            "offset_x": kf.offset_x,
            "offset_y": kf.offset_y,
            "interpolation": kf.interpolation,
        }
        for kf in keyframes
    ]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_reframe_video(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Video dosyasını sunucuya yükle.
    Döndürür: {"local_path": "..."} → POST /reframe/process'e gönder.
    Dosya, processor tamamlandıktan sonra otomatik silinir.
    """
    try:
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temp_id = uuid.uuid4().hex
        ext = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"

        if ext not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
            ext = ".mp4"

        save_path = str(settings.UPLOAD_DIR / f"reframe_upload_{temp_id}{ext}")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Boş dosya")

        with open(save_path, "wb") as f:
            f.write(content)

        print(f"[ReframeUpload] {len(content):,} byte kaydedildi → {save_path}")
        return {"local_path": save_path}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ReframeUpload] Hata: {e}")
        raise HTTPException(status_code=500, detail="Upload başarısız")


@router.post("/process", status_code=201)
async def start_reframe(
    req: ReframeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Arka planda reframe job'ı başlat.
    Anında {"reframe_job_id": "..."} döndürür.
    İlerlemeyi GET /reframe/status/{id} ile takip et.
    """
    if not req.clip_url and not req.clip_local_path:
        raise HTTPException(
            status_code=400,
            detail="clip_url veya clip_local_path zorunlu",
        )

    # Parametreleri doğrula ve temizle
    aspect_ratio = _sanitize_aspect_ratio(req.aspect_ratio)
    tracking_mode = _sanitize_tracking_mode(req.tracking_mode)
    content_type = _sanitize_content_type(req.content_type)
    detection_engine = _sanitize_detection_engine(req.detection_engine)
    user_id = current_user["id"]

    # content_type yoksa strategy parametresini fallback olarak kullan
    effective_hint = content_type or req.strategy

    # Supabase'de job satırı oluştur
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
            "strategy": req.strategy,
            "aspect_ratio": aspect_ratio,
            "tracking_mode": tracking_mode,
        }
        resp = get_client().table("reframe_jobs").insert(row).execute()
        if not resp.data:
            raise RuntimeError("DB insert veri döndürmedi")
        reframe_job_id = resp.data[0]["id"]
    except Exception as e:
        print(f"[ReframeRoute] Job satırı oluşturulamadı: {e}")
        raise HTTPException(status_code=500, detail="Reframe job oluşturulamadı")

    if os.getenv("MODAL_ENABLED", "").lower() == "true":
        import modal
        fn = modal.Function.from_name("prognot-reframe", "process_reframe")
        fn.spawn({
            "reframe_job_id": reframe_job_id,
            "clip_url": req.clip_url,
            "clip_local_path": req.clip_local_path,
            "clip_id": req.clip_id,
            "job_id": req.job_id,
            "clip_start": req.clip_start,
            "clip_end": req.clip_end,
            "strategy": req.strategy,
            "aspect_ratio": aspect_ratio,
            "tracking_mode": tracking_mode,
            "content_type_hint": effective_hint,
            "detection_engine": detection_engine,
            "debug_mode": False,
        })
        print(f"[ReframeRoute] Job {reframe_job_id} spawned on Modal")
    else:
        def _run() -> None:
            try:
                _update_job(reframe_job_id, status="processing", step="Starting...", percent=0)

                def on_progress(step: str, pct: int) -> None:
                    _update_job(reframe_job_id, step=step, percent=pct)

                result = run_reframe(
                    clip_url=req.clip_url,
                    clip_local_path=req.clip_local_path,
                    clip_id=req.clip_id,
                    job_id=req.job_id,
                    clip_start=req.clip_start,
                    clip_end=req.clip_end,
                    strategy=req.strategy,
                    aspect_ratio=aspect_ratio,
                    tracking_mode=tracking_mode,
                    content_type_hint=effective_hint,
                    detection_engine=detection_engine,
                    on_progress=on_progress,
                )

                # Keyframe'leri JSON-serializable dict'e çevir
                keyframes_dicts = _keyframes_to_dicts(result.keyframes)

                _update_job(
                    reframe_job_id,
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
                print(f"[ReframeRoute] Job {reframe_job_id} tamamlandı — "
                      f"{len(result.keyframes)} keyframe")

            except Exception as e:
                print(f"[ReframeRoute] Job {reframe_job_id} başarısız: {e}")
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
    Reframe job'ının ilerleme ve sonucunu döndür.
    15 dakikadan uzun süren job'lar otomatik hata olarak işaretlenir.
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
        print(f"[ReframeRoute] Status sorgusu hatası: {e}")
        # Supabase geçici hata (502/503 vb.) — pipeline muhtemelen hala çalışıyor.
        # 500 fırlatmak yerine "processing" döndür, frontend polling'e devam eder.
        return ReframeStatusResponse(
            status="processing",
            step="Processing...",
            percent=0,
        )

    if not resp.data:
        raise HTTPException(status_code=404, detail="Reframe job bulunamadı")

    job = resp.data[0]

    # Sahiplik kontrolü
    if str(job.get("user_id")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Erişim reddedildi")

    # Stale job tespiti
    if job.get("status") == "processing":
        updated_at_str = job.get("updated_at")
        if updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at < datetime.now(timezone.utc) - timedelta(minutes=_STALE_MINUTES):
                    error_msg = "Job zaman aşımına uğradı — sunucu yeniden başlatıldı. Lütfen tekrar deneyin."
                    _update_job(
                        reframe_job_id,
                        status="error",
                        step="Timed out",
                        error=error_msg,
                    )
                    job["status"] = "error"
                    job["step"] = "Timed out"
                    job["error"] = error_msg
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
        content_type=job.get("content_type"),
        tracking_mode=job.get("tracking_mode"),
        error=job.get("error"),
    )


@router.post("/debug", status_code=201)
async def start_reframe_debug(
    req: ReframeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Debug mode: same as /process but generates an annotated overlay video.
    Result includes metadata.debug_video_url → R2 public URL of debug video.
    Use this to visually inspect MediaPipe detections, focus points, crop window.
    """
    if not req.clip_url and not req.clip_local_path:
        raise HTTPException(status_code=400, detail="clip_url veya clip_local_path zorunlu")

    aspect_ratio = _sanitize_aspect_ratio(req.aspect_ratio)
    tracking_mode = _sanitize_tracking_mode(req.tracking_mode)
    content_type = _sanitize_content_type(req.content_type)
    detection_engine = _sanitize_detection_engine(req.detection_engine)
    effective_hint = content_type or req.strategy

    # Create job row
    try:
        row = {
            "user_id": current_user["id"],
            "status": "queued",
            "step": "Queued (debug)",
            "percent": 0,
            "clip_url": req.clip_url,
            "clip_local_path": req.clip_local_path,
            "clip_id": req.clip_id,
            "job_id": req.job_id,
            "clip_start": req.clip_start,
            "clip_end": req.clip_end,
            "strategy": req.strategy,
            "aspect_ratio": aspect_ratio,
            "tracking_mode": tracking_mode,
        }
        resp = get_client().table("reframe_jobs").insert(row).execute()
        reframe_job_id = resp.data[0]["id"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job oluşturulamadı: {e}")

    if os.getenv("MODAL_ENABLED", "").lower() == "true":
        import modal
        fn = modal.Function.from_name("prognot-reframe", "process_reframe")
        fn.spawn({
            "reframe_job_id": reframe_job_id,
            "clip_url": req.clip_url,
            "clip_local_path": req.clip_local_path,
            "clip_id": req.clip_id,
            "job_id": req.job_id,
            "clip_start": req.clip_start,
            "clip_end": req.clip_end,
            "strategy": req.strategy,
            "aspect_ratio": aspect_ratio,
            "tracking_mode": tracking_mode,
            "content_type_hint": effective_hint,
            "detection_engine": detection_engine,
            "debug_mode": True,
        })
        print(f"[ReframeDebug] Job {reframe_job_id} spawned on Modal (debug)")
    else:
        def _run() -> None:
            try:
                _update_job(reframe_job_id, status="processing", step="Starting (debug)...", percent=0)

                def on_progress(step: str, pct: int) -> None:
                    _update_job(reframe_job_id, step=f"[DEBUG] {step}", percent=pct)

                result = run_reframe(
                    clip_url=req.clip_url,
                    clip_local_path=req.clip_local_path,
                    clip_id=req.clip_id,
                    job_id=req.job_id,
                    clip_start=req.clip_start,
                    clip_end=req.clip_end,
                    strategy=req.strategy,
                    aspect_ratio=aspect_ratio,
                    tracking_mode=tracking_mode,
                    content_type_hint=effective_hint,
                    detection_engine=detection_engine,
                    on_progress=on_progress,
                    debug_mode=True,
                )

                keyframes_dicts = _keyframes_to_dicts(result.keyframes)
                debug_url = result.metadata.get("debug_video_url", "")

                _update_job(
                    reframe_job_id,
                    status="done",
                    step=f"Done! Debug: {debug_url}",
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
                print(f"[ReframeDebug] Job {reframe_job_id} done — debug_url={debug_url}")

            except Exception as e:
                print(f"[ReframeDebug] Job {reframe_job_id} failed: {e}")
                _update_job(reframe_job_id, status="error", step="Failed", percent=0, error=str(e)[:500])

        import threading
        threading.Thread(target=_run, daemon=True).start()
    return {"reframe_job_id": reframe_job_id}


@router.post("/analyze-debug/{reframe_job_id}")
async def analyze_debug_video(
    reframe_job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Send the debug video for this job to Gemini 2.5 Pro for a comprehensive
    frame-by-frame quality analysis of the reframe pipeline.

    Returns structured analysis covering face detection, focus resolver,
    path solver, crop quality, shot classification, and improvement priorities.
    """
    try:
        resp = (
            get_client()
            .table("reframe_jobs")
            .select("id, user_id, status, step, pipeline_metadata, keyframes, scene_cuts, src_w, src_h, fps, duration_s")
            .eq("id", reframe_job_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database error")

    if not resp.data:
        raise HTTPException(status_code=404, detail="Reframe job not found")

    job = resp.data[0]
    if str(job.get("user_id")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Access denied")

    if job.get("status") != "done":
        raise HTTPException(status_code=400, detail="Job is not done yet")

    step = job.get("step", "")
    if "Debug: " not in step:
        raise HTTPException(status_code=400, detail="No debug video found for this job. Run with debug mode enabled.")

    debug_video_url = step.split("Debug: ", 1)[1].strip()
    if not debug_video_url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid debug video URL")

    # Build pipeline context from DB data
    pipeline_context = {
        "pipeline_metadata": job.get("pipeline_metadata") or {},
        "keyframes": job.get("keyframes") or [],
        "scene_cuts": job.get("scene_cuts") or [],
        "src_w": job.get("src_w"),
        "src_h": job.get("src_h"),
        "fps": job.get("fps"),
        "duration_s": job.get("duration_s"),
    }

    try:
        from app.reframe.debug_analyzer import analyze_debug_video as run_analysis
        result = run_analysis(debug_video_url, reframe_job_id, pipeline_context)
        return result
    except Exception as e:
        print(f"[ReframeRoute] Debug analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)[:200]}")


@router.get("/metadata/{job_id}/{clip_id}")
async def get_reframe_metadata(
    job_id: str,
    clip_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Pipeline → Editor köprüsü.
    Pipeline'ın klip export'ı sırasında kaydettiği reframe verilerini döndürür.
    Editor ?clipJobId= parametresiyle açıldığında çağrılır.
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
        print(f"[ReframeRoute] Metadata sorgusu hatası: {e}")
        raise HTTPException(status_code=500, detail="Veritabanı hatası")

    if not resp.data:
        raise HTTPException(
            status_code=404,
            detail="Bu klip için reframe metadata bulunamadı",
        )

    row = resp.data[0]
    return {
        "scene_cuts": row.get("scene_cuts", []),
        "speaker_segments": row.get("speaker_segments", []),
        "keyframes": row.get("keyframes", []),
        "src_w": row.get("src_w"),
        "src_h": row.get("src_h"),
        "fps": row.get("fps"),
        "duration_s": row.get("duration_s"),
        "strategy": row.get("strategy", "podcast"),
        "aspect_ratio": row.get("aspect_ratio", "9:16"),
        "content_type": row.get("content_type"),
    }
