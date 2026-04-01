"""
Reframe V4 (Director's Cut) — Main orchestrator.

Pipeline steps:
  1. Video download (if needed)
  2. ffprobe → src_w, src_h, fps, duration_s
  3. detect_shots() → Shot list (for scene cut markers)
  4. analyze_shots() → FrameAnalysis list (YOLO person positions)
  5. Load diarization (if available)
  6. analyze_video_focus() → DirectorPlan (Gemini Pro + Video)
  7. anchor_plan() → AnchoredSegment list (YOLO-snapped positions)
  8. convert_to_keyframes() → ReframeResult (pixel keyframes)

Fallback: if Gemini fails, step 6 uses diarization-only plan.
"""
import json
import logging
import os
import subprocess
import uuid
from typing import Callable, Optional

import requests

from app.config import settings

from .config import ReframeConfig
from .shot_detector import detect_shots
from .frame_analyzer import analyze_shots, classify_shots
from .video_director import analyze_video_focus, build_fallback_plan
from .plan_anchor import anchor_plan
from .keyframe_converter import convert_to_keyframes
from .types import ReframeResult

logger = logging.getLogger(__name__)


def run_reframe(
    clip_url: Optional[str] = None,
    clip_local_path: Optional[str] = None,
    clip_id: Optional[str] = None,
    job_id: Optional[str] = None,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    strategy: str = "podcast",
    aspect_ratio: str = "9:16",
    tracking_mode: str = "dynamic_xy",
    content_type_hint: Optional[str] = None,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> ReframeResult:
    """
    V4 reframe pipeline. Function signature matches V2/V3 — frontend needs no changes.
    """
    if not clip_url and not clip_local_path:
        raise ValueError("clip_url or clip_local_path required")

    def progress(step: str, pct: int) -> None:
        logger.info("[Reframe] %d%% — %s", pct, step)
        if on_progress:
            on_progress(step, pct)

    # Config
    ar_tuple = _parse_aspect_ratio(aspect_ratio)
    config = ReframeConfig(
        aspect_ratio=ar_tuple,
        tracking_mode=tracking_mode,
    )

    # Map content_type_hint to video director style
    effective_style = _resolve_content_type(content_type_hint, strategy)
    config.video_director.content_type = effective_style

    temp_path: Optional[str] = None

    # Resolve input path
    if clip_local_path and os.path.exists(clip_local_path):
        input_path = clip_local_path
    else:
        temp_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"reframe_{uuid.uuid4().hex}.mp4",
        )
        input_path = temp_path

    try:
        # 1. Download video (if needed)
        if temp_path:
            progress("Downloading video...", 5)
            _download_video(clip_url, temp_path)

        # 2. Video metadata
        progress("Reading video metadata...", 8)
        src_w, src_h, fps, duration_s = _probe_video(input_path)
        logger.info("[Reframe] %dx%d @ %.2ffps, %.2fs", src_w, src_h, fps, duration_s)

        effective_end = clip_end if clip_end is not None else duration_s

        # 3. Shot detection (for scene cut markers)
        progress("Detecting scene cuts...", 12)
        shots = detect_shots(input_path, duration_s, config.shot_detection)
        logger.info("[Reframe] %d shots detected", len(shots))

        # 4. Frame analysis (YOLO — needed for position anchoring)
        progress("Analyzing frames...", 20)
        frame_analyses = analyze_shots(
            input_path, shots, src_w, src_h, config.frame_analysis,
        )
        logger.info("[Reframe] %d frames analyzed", len(frame_analyses))

        # 4b. Classify shots by type (wide/closeup/b_roll) based on YOLO data
        progress("Classifying camera angles...", 35)
        classify_shots(shots, frame_analyses)
        for s in shots:
            logger.info("[Reframe] Shot %.1f-%.1fs: %s", s.start_s, s.end_s, s.shot_type)

        # 5. Load diarization
        progress("Loading speaker data...", 40)
        diarization_segments: list[dict] = []
        if job_id:
            try:
                diarization_segments = _load_diarization(job_id, clip_start, effective_end)
                logger.info("[Reframe] %d diarization segments", len(diarization_segments))
            except Exception as e:
                logger.warning("[Reframe] Diarization load failed: %s — visual-only", e)

        # 6. Video Director (Gemini Pro + full video analysis)
        progress("AI analyzing video focus...", 50)
        try:
            director_plan = analyze_video_focus(
                video_path=input_path,
                diarization_segments=diarization_segments,
                shots=shots,
                src_w=src_w,
                src_h=src_h,
                fps=fps,
                duration_s=duration_s,
                aspect_ratio=ar_tuple,
                config=config.video_director,
            )
            logger.info(
                "[Reframe] Gemini plan: %s, %d segments",
                director_plan.content_type, len(director_plan.segments),
            )
        except Exception as e:
            logger.warning("[Reframe] Gemini analysis failed: %s — using fallback", e)
            director_plan = build_fallback_plan(
                diarization_segments, shots, duration_s,
            )

        # 7. Plan anchoring (snap timestamps + resolve YOLO positions)
        progress("Anchoring focus plan to frames...", 75)
        anchored = anchor_plan(
            plan=director_plan,
            frame_analyses=frame_analyses,
            diarization_segments=diarization_segments,
            shots=shots,
            fps=fps,
            duration_s=duration_s,
            config=config.anchor,
        )

        # 8. Keyframe conversion
        progress("Generating keyframes...", 85)
        result = convert_to_keyframes(
            anchored_segments=anchored,
            shots=shots,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            duration_s=duration_s,
            config=config,
        )

        # Store detected content type
        result.content_type = director_plan.content_type

        progress("Done!", 100)
        logger.info(
            "[Reframe] Complete — %d keyframes, %d scene cuts, type=%s",
            len(result.keyframes), len(result.scene_cuts), result.content_type,
        )
        return result

    except Exception as e:
        logger.error("[Reframe] Pipeline error: %s", e)
        import traceback
        traceback.print_exc()
        raise

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# --- Content type resolution -------------------------------------------------

def _resolve_content_type(
    content_type_hint: Optional[str],
    strategy_fallback: str,
) -> str:
    """Map content_type_hint or strategy to a style guide key."""
    if content_type_hint and content_type_hint != "auto":
        mapping = {
            "podcast": "conversation",
            "interview": "conversation",
            "single": "presentation",
            "gaming": "action",
            "generic": "auto",
            "conversation": "conversation",
            "presentation": "presentation",
            "action": "action",
        }
        return mapping.get(content_type_hint, "auto")

    # Fallback from old strategy parameter
    strategy_mapping = {
        "podcast": "conversation",
        "interview": "conversation",
        "single_speaker": "presentation",
    }
    return strategy_mapping.get(strategy_fallback, "auto")


# --- Video helpers -----------------------------------------------------------

def _probe_video(video_path: str) -> tuple[int, int, float, float]:
    """Get video dimensions, FPS and duration via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr[:200]}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("ffprobe found no video stream")

    stream = streams[0]
    src_w = int(stream.get("width", 0))
    src_h = int(stream.get("height", 0))
    if src_w == 0 or src_h == 0:
        raise RuntimeError(f"Invalid video dimensions: {src_w}x{src_h}")

    # FPS
    r_frame_rate = stream.get("r_frame_rate", "30/1")
    try:
        num, den = r_frame_rate.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    # Duration
    duration_s = float(stream.get("duration", 0.0))
    if duration_s == 0.0:
        cmd2 = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]
        r2 = subprocess.run(
            cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30,
        )
        if r2.returncode == 0:
            fmt = json.loads(r2.stdout).get("format", {})
            duration_s = float(fmt.get("duration", 0.0))

    if duration_s == 0.0:
        raise RuntimeError("Could not determine video duration")

    return src_w, src_h, round(fps, 4), round(duration_s, 4)


def _download_video(url: str, dest_path: str) -> None:
    """Download remote video. Try FFmpeg copy first, then requests fallback."""
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", url,
            "-c", "copy", dest_path,
        ]
        subprocess.run(
            cmd, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300,
        )
    except subprocess.CalledProcessError:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)


def _parse_aspect_ratio(ratio_str: str) -> tuple[int, int]:
    """'9:16' → (9, 16). Invalid → (9, 16) fallback."""
    try:
        parts = ratio_str.strip().split(":")
        w, h = int(parts[0]), int(parts[1])
        if w > 0 and h > 0:
            return (w, h)
    except Exception:
        pass
    return (9, 16)


# --- Diarization loader ------------------------------------------------------

def _load_diarization(
    job_id: str,
    clip_start: float,
    clip_end: float,
) -> list[dict]:
    """
    Load diarization data from Supabase.
    Builds speaker segments from Deepgram word timestamps,
    filters to clip window and converts to clip-relative time.
    """
    from app.services.supabase_client import get_client

    supabase = get_client()
    resp = (
        supabase.table("transcripts")
        .select("word_timestamps, speaker_map")
        .eq("job_id", job_id)
        .execute()
    )

    if not resp.data:
        logger.warning("[Diarization] Transcript not found: job_id=%s", job_id)
        return []

    row = resp.data[0]
    words = row.get("word_timestamps") or []
    speaker_map = row.get("speaker_map") or {}

    if not words:
        return []

    # speaker_map: {"0": "HOST", "1": "GUEST"} → HOST=0, GUEST=1
    raw_to_index: dict[str, int] = {}
    for k, v in speaker_map.items():
        role = str(v).upper()
        raw_id = str(k)
        if role == "HOST":
            raw_to_index[raw_id] = 0
        elif role == "GUEST":
            raw_to_index[raw_id] = 1

    # Build speaker segments from words
    segments: list[dict] = []
    current_speaker = None
    current_start = None
    current_end = None

    for word in words:
        raw_speaker = str(word.get("speaker", 0))
        speaker_idx = raw_to_index.get(raw_speaker, int(raw_speaker) % 2)
        w_start = float(word.get("start", 0))
        w_end = float(word.get("end", 0))

        if speaker_idx != current_speaker:
            if current_speaker is not None and current_start is not None:
                segments.append({
                    "speaker": current_speaker,
                    "start": current_start,
                    "end": current_end,
                })
            current_speaker = speaker_idx
            current_start = w_start
            current_end = w_end
        else:
            current_end = w_end

    if current_speaker is not None and current_start is not None:
        segments.append({
            "speaker": current_speaker,
            "start": current_start,
            "end": current_end,
        })

    # Filter to clip window and convert to clip-relative time
    clip_segments: list[dict] = []
    for seg in segments:
        if seg["end"] <= clip_start or seg["start"] >= clip_end:
            continue
        clipped_start = max(0.0, seg["start"] - clip_start)
        clipped_end = min(clip_end - clip_start, seg["end"] - clip_start)
        if clipped_end > clipped_start:
            clip_segments.append({
                "speaker": seg["speaker"],
                "start": round(clipped_start, 3),
                "end": round(clipped_end, 3),
            })

    logger.info("[Diarization] %d segments (clip %.1f-%.1fs)", len(clip_segments), clip_start, clip_end)
    return clip_segments
