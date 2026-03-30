"""
Reframe Processor — 5-layer pipeline orchestrator.

Layers:
  1. Scene Detection  (FFmpeg, float timestamps)
  2. Person Detection (YOLOv8 nano-pose, first frame per scene)
  3. Composition      (gaze direction + look room)
  4. Speaker Switcher (Deepgram diarization from Supabase or re-run)
  5. Strategy         (Podcast: who to follow, hard-cut on speaker change)

Progress callbacks write directly to Supabase reframe_jobs table.
"""

import os
import subprocess
import uuid
import requests
from typing import Callable, Optional

from app.config import settings
from app.reframe.scene_detector import get_scene_intervals
from app.reframe.person_detector import build_scene_person_detections
from app.reframe.diarization import get_speaker_segments
from app.reframe.strategies.podcast import decide as podcast_decide
from app.reframe.crop_calculator import decisions_to_keyframes
from app.reframe.models.types import ReframeResult


def run_reframe(
    clip_url: Optional[str] = None,
    clip_local_path: Optional[str] = None,
    clip_id: Optional[str] = None,
    job_id: Optional[str] = None,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    strategy: str = "podcast",
    aspect_ratio: str = "9:16",
    tracking_mode: str = "x_only",
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> ReframeResult:
    """
    Full reframe pipeline. Returns ReframeResult.
    Pass either clip_url (remote) or clip_local_path (already on disk).
    on_progress(step_label, percent) is called at each stage.
    """
    if not clip_url and not clip_local_path:
        raise ValueError("Either clip_url or clip_local_path must be provided")

    def progress(step: str, pct: int):
        print(f"[Reframe] {pct}% — {step}")
        if on_progress:
            on_progress(step, pct)

    temp_path: Optional[str] = None

    # Resolve input path
    if clip_local_path and os.path.exists(clip_local_path):
        input_path = clip_local_path
    else:
        temp_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"reframe_{uuid.uuid4().hex}.mp4"
        )
        input_path = temp_path

    try:
        # ── 1. Download (skip if local file provided) ─────────────────────────
        if temp_path:
            progress("Downloading video...", 5)
            _download_video(clip_url, temp_path)

        # ── 2. Video metadata via ffprobe ─────────────────────────────────────
        progress("Reading video metadata...", 10)
        src_w, src_h, fps, duration_s = _probe_video(input_path)
        print(f"[Reframe] {src_w}x{src_h} @ {fps:.2f}fps, {duration_s:.2f}s")

        effective_end = clip_end if clip_end is not None else duration_s

        # ── 3. Scene detection (FFmpeg, float timestamps) ─────────────────────
        progress("Detecting scene cuts...", 15)
        scenes = get_scene_intervals(input_path, duration_s=duration_s)

        # ── 4. Person detection (YOLOv8, first frame per scene) ───────────────
        progress("Detecting persons...", 25)
        scene_analyses = build_scene_person_detections(input_path, scenes)

        # ── 5. Diarization ────────────────────────────────────────────────────
        progress("Loading speaker data...", 45)
        speaker_segments: list = []
        if job_id:
            speaker_segments = get_speaker_segments(job_id, clip_start, effective_end)
            print(
                f"[Reframe] Diarization: {len(speaker_segments)} segments"
                if speaker_segments else "[Reframe] No diarization — visual-only"
            )
        else:
            print("[Reframe] No job_id — visual-only mode")

        # ── 6. Strategy layer ─────────────────────────────────────────────────
        progress("Applying reframe strategy...", 60)
        if strategy == "podcast":
            decisions = podcast_decide(
                scene_analyses=scene_analyses,
                speaker_segments=speaker_segments,
                src_w=src_w,
                src_h=src_h,
                aspect_ratio=aspect_ratio,
            )
        else:
            # Fallback to podcast for unknown strategies
            decisions = podcast_decide(
                scene_analyses=scene_analyses,
                speaker_segments=speaker_segments,
                src_w=src_w,
                src_h=src_h,
                aspect_ratio=aspect_ratio,
            )

        # ── 7. Keyframe generation ────────────────────────────────────────────
        progress("Generating keyframes...", 80)
        keyframes, scene_cuts = decisions_to_keyframes(
            decisions=decisions,
            src_w=src_w,
            src_h=src_h,
            aspect_ratio=aspect_ratio,
            scene_analyses=scene_analyses,
            speaker_segments=speaker_segments,
        )
        print(f"[Reframe] {len(keyframes)} keyframes, {len(scene_cuts)} cut markers")

        progress("Done!", 100)

        return ReframeResult(
            keyframes=keyframes,
            scene_cuts=scene_cuts,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            duration_s=duration_s,
        )

    except Exception as e:
        print(f"[Reframe] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _probe_video(video_path: str):
    """
    Use ffprobe to extract width, height, fps, and duration.
    Returns (src_w, src_h, fps, duration_s).
    Raises RuntimeError on failure.
    """
    import json as _json

    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:200]}")

    data = _json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("ffprobe returned no video streams")

    stream = streams[0]
    src_w = int(stream.get("width", 0))
    src_h = int(stream.get("height", 0))

    if src_w == 0 or src_h == 0:
        raise RuntimeError(f"Invalid dimensions: {src_w}x{src_h}")

    # FPS from r_frame_rate (e.g. "30/1" or "2997/100")
    r_frame_rate = stream.get("r_frame_rate", "30/1")
    try:
        num, den = r_frame_rate.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    # Duration: prefer stream duration, fallback to format
    duration_s = float(stream.get("duration", 0.0))
    if duration_s == 0.0:
        # Second ffprobe call for format duration
        cmd2 = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]
        r2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        if r2.returncode == 0:
            fmt = _json.loads(r2.stdout).get("format", {})
            duration_s = float(fmt.get("duration", 0.0))

    if duration_s == 0.0:
        raise RuntimeError("Could not determine video duration")

    return src_w, src_h, round(fps, 4), round(duration_s, 4)


def _download_video(url: str, dest_path: str) -> None:
    """Download a remote video to dest_path using FFmpeg, with requests fallback."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", url,
            "-c", "copy",
            dest_path,
        ]
        subprocess.run(
            cmd, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except subprocess.CalledProcessError:
        # HTTP fallback (R2 presigned URLs, etc.)
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
