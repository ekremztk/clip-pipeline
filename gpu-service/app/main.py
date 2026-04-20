"""
GPU Pipeline Service — Cloud Run L4
Runs S08 (export) → S09 (reframe) → S10 (captions) with GPU acceleration.

Single endpoint: POST /process-clips
Railway orchestrator calls this after S07 completes.
"""
import logging
import os
import time
import traceback
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("gpu-pipeline")

app = FastAPI(title="GPU Pipeline Service", version="1.0.0")


# --- Request/Response Models ---

class ClipInput(BaseModel):
    """Single clip from S07 cut_results."""
    final_start: float
    final_end: float
    final_duration_s: float
    content_type: str = "unknown"
    hook_text: Optional[str] = None
    score: Optional[float] = None
    quality_verdict: Optional[str] = None
    clip_strategy_role: Optional[str] = None
    posting_order: Optional[int] = None
    suggested_title: Optional[str] = None
    suggested_description: Optional[str] = None
    quality_notes: Optional[str] = None
    requires_stitch: Optional[bool] = False
    stitch_setup: Optional[dict] = None


class ProcessRequest(BaseModel):
    """Full request from Railway orchestrator."""
    job_id: str
    channel_id: str
    user_id: Optional[str] = None
    video_title: str = ""
    source_video_url: str
    clips: list[ClipInput]
    transcript_data: Optional[dict] = None
    reframe_content_type: str = "podcast"
    caption_template: str = "clean"


class ClipResult(BaseModel):
    """Result for a single clip."""
    clip_index: int
    clip_id: Optional[str] = None
    video_landscape_path: Optional[str] = None
    video_reframed_path: Optional[str] = None
    video_captioned_path: Optional[str] = None
    error: Optional[str] = None


class ProcessResponse(BaseModel):
    """Response back to Railway."""
    status: str  # "completed" or "partial" or "failed"
    total_clips: int
    successful_clips: int
    duration_s: float
    clips: list[ClipResult]


# --- Health Check ---

@app.get("/health")
def health():
    import torch
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else "none"
    return {
        "status": "healthy",
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
    }


# --- Main Endpoint ---

@app.post("/process-clips", response_model=ProcessResponse)
def process_clips(req: ProcessRequest):
    """
    Run S08 → S09 → S10 sequentially for all clips.
    Called by Railway orchestrator after S07 completes.
    """
    start_time = time.time()
    logger.info(f"[GPU] Starting job {req.job_id}: {len(req.clips)} clips")

    # Download source video once
    local_video = _download_source_video(req.source_video_url)
    if not local_video:
        raise HTTPException(status_code=500, detail="Failed to download source video")

    try:
        # S08: Export (cut + encode + R2 upload + DB insert)
        logger.info(f"[GPU] S08 starting — {len(req.clips)} clips")
        exported_clips = _run_s08(
            cut_results=[clip.model_dump() for clip in req.clips],
            job_id=req.job_id,
            channel_id=req.channel_id,
            video_path=local_video,
            video_title=req.video_title,
            user_id=req.user_id,
            transcript_data=req.transcript_data,
        )
        logger.info(f"[GPU] S08 done — {len(exported_clips)} clips exported")

        if not exported_clips:
            return ProcessResponse(
                status="failed",
                total_clips=len(req.clips),
                successful_clips=0,
                duration_s=time.time() - start_time,
                clips=[],
            )

        # S09: Reframe (YOLO + Gemini → 9:16)
        logger.info(f"[GPU] S09 starting — {len(exported_clips)} clips")
        reframed_clips = _run_s09(
            exported_clips=exported_clips,
            job_id=req.job_id,
            channel_id=req.channel_id,
            reframe_content_type=req.reframe_content_type,
        )
        logger.info(f"[GPU] S09 done — {sum(1 for c in reframed_clips if c.get('video_reframed_path'))}/{len(reframed_clips)} reframed")

        # S10: Captions (Deepgram + Pillow + FFmpeg overlay)
        source_clips = reframed_clips if reframed_clips else exported_clips
        logger.info(f"[GPU] S10 starting — {len(source_clips)} clips")
        captioned_clips = _run_s10(
            reframed_clips=source_clips,
            job_id=req.job_id,
            channel_id=req.channel_id,
            caption_template=req.caption_template,
        )
        logger.info(f"[GPU] S10 done — {sum(1 for c in captioned_clips if c.get('video_captioned_path'))}/{len(captioned_clips)} captioned")

        # Build response
        results = []
        for i, clip in enumerate(captioned_clips):
            results.append(ClipResult(
                clip_index=i,
                clip_id=clip.get("id"),
                video_landscape_path=clip.get("video_landscape_path"),
                video_reframed_path=clip.get("video_reframed_path"),
                video_captioned_path=clip.get("video_captioned_path"),
            ))

        successful = sum(1 for c in captioned_clips if c.get("video_captioned_path"))
        total_time = time.time() - start_time

        status = "completed" if successful == len(req.clips) else "partial" if successful > 0 else "failed"
        logger.info(f"[GPU] Job {req.job_id} {status}: {successful}/{len(req.clips)} clips in {total_time:.1f}s")

        return ProcessResponse(
            status=status,
            total_clips=len(req.clips),
            successful_clips=successful,
            duration_s=total_time,
            clips=results,
        )

    finally:
        if local_video and os.path.exists(local_video):
            try:
                os.remove(local_video)
            except Exception:
                pass


# --- Step Runners ---

def _run_s08(cut_results, job_id, channel_id, video_path, video_title, user_id, transcript_data):
    """Run S08 export step."""
    from app.pipeline.steps import s08_export
    return s08_export.run(
        cut_results=cut_results,
        job_id=job_id,
        channel_id=channel_id,
        video_path=video_path,
        video_title=video_title,
        user_id=user_id,
        transcript_data=transcript_data,
    )


def _run_s09(exported_clips, job_id, channel_id, reframe_content_type):
    """Run S09 reframe step."""
    from app.pipeline.steps import s09_reframe
    return s09_reframe.run(
        exported_clips=exported_clips,
        job_id=job_id,
        channel_id=channel_id,
        reframe_content_type=reframe_content_type,
    )


def _run_s10(reframed_clips, job_id, channel_id, caption_template):
    """Run S10 captions step."""
    from app.pipeline.steps import s10_captions
    return s10_captions.run(
        reframed_clips=reframed_clips,
        job_id=job_id,
        channel_id=channel_id,
        caption_template=caption_template,
    )


# --- Helpers ---

def _download_source_video(url: str) -> Optional[str]:
    """Download source video from R2 to local temp file."""
    import uuid
    import requests

    local_path = os.path.join("temp_uploads", f"gpu_source_{uuid.uuid4().hex}.mp4")
    os.makedirs("temp_uploads", exist_ok=True)

    try:
        logger.info(f"[GPU] Downloading source video: {url[:80]}...")
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=131072):
                if chunk:
                    f.write(chunk)
        size_mb = os.path.getsize(local_path) / 1024 / 1024
        logger.info(f"[GPU] Source video downloaded: {size_mb:.1f}MB")
        return local_path
    except Exception as e:
        logger.error(f"[GPU] Source video download failed: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)
        return None
