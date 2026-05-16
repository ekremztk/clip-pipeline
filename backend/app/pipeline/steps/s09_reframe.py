"""
Step 9: Reframe
For each exported 16:9 clip: run AI reframe analysis + FFmpeg render → 9:16 MP4.

Two strategies:
  - podcast: YOLO face tracking + Gemini direction + keyframe emission → render_podcast_reframe()
  - gaming:  YOLO webcam detection → run_gaming_reframe() (already renders + uploads)

Result: video_reframed_path updated on each clip row.
"""
import logging
import os
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import settings
from app.pipeline.stock_analytics import record_candidate_stage
from app.services.supabase_client import get_client
from app.services.r2_client import get_r2_client

logger = logging.getLogger(__name__)


def run(
    exported_clips: list,
    job_id: str,
    channel_id: str,
    reframe_content_type: str = "podcast",
) -> list:
    """
    Step 9: Reframe — produces a 9:16 MP4 for each exported clip.

    Args:
        exported_clips: List of clip dicts from S08 (must have video_landscape_path and id)
        job_id: Pipeline job ID
        channel_id: Channel ID
        reframe_content_type: "podcast" or "gaming"

    Returns: List of updated clip dicts with video_reframed_path set.
    """
    print(f"[S09] Starting reframe for {len(exported_clips)} clips. Strategy: {reframe_content_type}")
    supabase = get_client()
    reframed_clips = []

    def _process_clip(index: int, clip: dict) -> dict:
        clip_id = clip.get("id")
        landscape_url = clip.get("video_landscape_path") or clip.get("file_url")

        if not landscape_url:
            print(f"[S09] Clip {index+1}: No video_landscape_path. Skipping reframe.")
            record_candidate_stage(clip_id, "s09", "skipped", error_message="No video_landscape_path")
            return clip

        reframed_url = None
        reframe_meta = {}

        try:
            if reframe_content_type == "gaming":
                reframed_url, reframe_meta = _reframe_gaming(
                    clip_url=landscape_url,
                    job_id=job_id,
                    clip_index=index,
                )
            else:
                reframed_url, reframe_meta = _reframe_podcast(
                    clip_url=landscape_url,
                    job_id=job_id,
                    clip_index=index,
                )

            if clip_id and reframed_url:
                try:
                    supabase.table("clips").update({
                        "video_reframed_path": reframed_url,
                        "reframe_metadata": reframe_meta,
                    }).eq("id", str(clip_id)).execute()
                    print(f"[S09] Clip {index+1} (id: {clip_id}) reframed: {reframed_url}")
                except Exception as db_err:
                    print(f"[S09] DB update error for clip {index+1}: {db_err}")
                record_candidate_stage(clip_id, "s09", "completed", url=reframed_url)

            return {**clip, "video_reframed_path": reframed_url, "reframe_metadata": reframe_meta, "local_reframed_path": reframe_meta.get("local_reframed_path")}

        except Exception as e:
            print(f"[S09] Reframe error for clip {index+1}: {e}")
            traceback.print_exc()
            record_candidate_stage(clip_id, "s09", "failed", error_message=str(e))
            return clip

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_process_clip, index, clip): index
            for index, clip in enumerate(exported_clips)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                reframed_clips.append((idx, result))
            except Exception as e:
                print(f"[S09] Thread error for clip {idx+1}: {e}")
                reframed_clips.append((idx, exported_clips[idx]))

    reframed_clips.sort(key=lambda x: x[0])
    reframed_clips = [clip for _, clip in reframed_clips]

    successful = sum(1 for c in reframed_clips if c.get("video_reframed_path"))
    print(f"[S09] Reframe complete. {successful}/{len(exported_clips)} clips reframed.")
    return reframed_clips


def _reframe_podcast(
    clip_url: str,
    job_id: str,
    clip_index: int,
) -> tuple[str, dict]:
    """
    Podcast reframe:
    1. Run YOLO + Gemini analysis → keyframes (via run_reframe)
    2. render_podcast_reframe() → 9:16 MP4
    3. Upload to R2

    Returns (reframed_r2_url, metadata_dict)
    """
    from app.reframe.pipeline import run_reframe
    from app.reframe.render import render_podcast_reframe

    print(f"[S09] Podcast reframe for clip {clip_index+1}: {clip_url}")

    # Download once — reused for both analysis and render
    local_path = _download_temp(clip_url)
    output_path = os.path.join(
        str(settings.UPLOAD_DIR),
        f"podcast_reframe_{uuid.uuid4().hex}.mp4",
    )

    try:
        # Run analysis pipeline — gets keyframes + scene_cuts + crop dimensions
        result = run_reframe(
            clip_local_path=local_path,
            job_id=job_id,
            strategy="podcast",
            aspect_ratio="9:16",
            tracking_mode="x_only",
            content_type_hint="podcast",
            detection_engine="yolo",
        )

        crop_w = result.metadata.get("crop_w", 0)
        crop_h = result.metadata.get("crop_h", 0)

        if not crop_w or not crop_h:
            raise RuntimeError(f"[S09] Missing crop dimensions: crop_w={crop_w} crop_h={crop_h}")

        if not result.keyframes:
            raise RuntimeError("[S09] No keyframes returned from podcast reframe analysis")

        # Render 9:16 MP4 via FFmpeg (same local_path, no re-download)
        render_podcast_reframe(
            video_path=local_path,
            keyframes=result.keyframes,
            scene_cuts=result.scene_cuts,
            src_w=result.src_w,
            src_h=result.src_h,
            crop_w=crop_w,
            crop_h=crop_h,
            fps=result.fps,
            duration_s=result.duration_s,
            output_path=output_path,
            canvas_w=1080,
            canvas_h=1920,
        )

        r2_url = _upload_to_r2(output_path, f"reframe/podcast_{uuid.uuid4().hex}.mp4")

    finally:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    meta = {
        "strategy": "podcast",
        "local_reframed_path": output_path,
        "keyframe_count": len(result.keyframes),
        "scene_cut_count": len(result.scene_cuts),
        "crop_w": crop_w,
        "crop_h": crop_h,
        "src_w": result.src_w,
        "src_h": result.src_h,
        "fps": result.fps,
        "duration_s": result.duration_s,
        "keyframes": [
            {
                "time_s": kf.time_s,
                "offset_x": kf.offset_x,
                "offset_y": kf.offset_y,
                "interpolation": kf.interpolation,
            }
            for kf in result.keyframes
        ],
        "scene_cuts": result.scene_cuts,
    }

    return r2_url, meta


def _reframe_gaming(
    clip_url: str,
    job_id: str,
    clip_index: int,
) -> tuple[str, dict]:
    """
    Gaming reframe: YOLO webcam detection → FFmpeg vstack render.
    run_gaming_reframe() handles render + R2 upload internally.

    Returns (reframed_r2_url, metadata_dict)
    """
    from app.reframe.pipeline import run_reframe

    print(f"[S09] Gaming reframe for clip {clip_index+1}: {clip_url}")

    local_path = _download_temp(clip_url)
    try:
        result = run_reframe(
            clip_local_path=local_path,
            job_id=job_id,
            strategy="gaming",
            aspect_ratio="9:16",
            tracking_mode="x_only",
            content_type_hint="gaming",
            detection_engine="yolo",
        )
    finally:
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    reframed_url = result.metadata.get("processed_video_url", "")
    if not reframed_url:
        raise RuntimeError("[S09] Gaming reframe did not produce a processed_video_url")

    meta = {
        "strategy": "gaming",
        "webcam_crop": result.metadata.get("webcam_crop"),
        "game_bounds": result.metadata.get("game_bounds"),
        "webcam_raw_bounds": result.metadata.get("webcam_raw_bounds"),
        "face_center": result.metadata.get("face_center"),
        "webcam_detected_by": result.metadata.get("webcam_detected_by"),
        "overlap_pct": result.metadata.get("overlap_pct"),
        "source_w": result.metadata.get("source_w"),
        "source_h": result.metadata.get("source_h"),
    }

    return reframed_url, meta


def _download_temp(url: str) -> str:
    """Download a URL to a temp file, return local path."""
    import requests

    upload_dir = str(settings.UPLOAD_DIR)
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, f"s09_dl_{uuid.uuid4().hex}.mp4")
    try:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(temp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return temp_path
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise RuntimeError(f"[S09] Download failed for {url}: {e}") from e


def _upload_to_r2(local_path: str, r2_key: str) -> str:
    """Upload a local file to R2 and return the public URL."""
    r2 = get_r2_client()
    with open(local_path, "rb") as f:
        r2.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=r2_key,
            Body=f,
            ContentType="video/mp4",
        )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key}"
