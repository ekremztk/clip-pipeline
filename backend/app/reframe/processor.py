"""
Reframe processor — keyframe mode.
Pipeline:
  1. Download video from URL → temp file
  2. Detect scenes
  3. Detect face positions per scene
  4. Fetch diarization (if job_id provided)
  5. Calculate per-frame crop positions
  6. Convert to canvas keyframes
  7. Return keyframe list (no encoding, no upload)
"""

import os
import uuid
import subprocess
import requests
import cv2
from typing import Callable, Optional

from app.reframe.scene_detector import get_scene_intervals
from app.reframe.face_detector import build_scene_face_map
from app.reframe.diarization import get_speaker_segments
from app.reframe.crop_calculator import calculate_crop_positions, compute_crop_width, extract_canvas_keyframes
from app.config import settings


def run_reframe(
    clip_url: str,
    clip_id: Optional[str] = None,
    job_id: Optional[str] = None,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> dict:
    """
    Reframe pipeline. Returns a dict with keyframes and video metadata.
    Keyframes: [{time_s, offset_x}, ...] in canvas-pixel coordinates.
    on_progress(step_label, percent) called throughout.
    """

    def progress(step: str, pct: int):
        print(f"[Reframe] {pct}% — {step}")
        if on_progress:
            on_progress(step, pct)

    temp_dir = os.path.join(str(settings.UPLOAD_DIR), f"reframe_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=True)
    input_path = os.path.join(temp_dir, "input.mp4")

    try:
        # ── 1. Download ──────────────────────────────────────────────────────
        progress("Downloading video...", 5)
        _download_video(clip_url, input_path)

        # ── 2. Video info ────────────────────────────────────────────────────
        progress("Reading video metadata...", 10)
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        if src_w == 0 or src_h == 0 or total_frames == 0:
            raise RuntimeError(f"Invalid video: {src_w}x{src_h}, {total_frames} frames")

        duration_s = total_frames / fps
        effective_end = clip_end if clip_end is not None else duration_s
        print(f"[Reframe] Video: {src_w}x{src_h} @ {fps:.2f}fps, {total_frames} frames, {duration_s:.1f}s")

        # ── 3. Scene detection ───────────────────────────────────────────────
        progress("Detecting scene cuts...", 15)
        scene_intervals = get_scene_intervals(input_path, total_frames)
        print(f"[Reframe] {len(scene_intervals)} scenes detected")

        # ── 4. Face detection per scene ──────────────────────────────────────
        progress("Detecting faces...", 25)
        scene_face_maps = []
        for i, scene in enumerate(scene_intervals):
            face_map = build_scene_face_map(
                input_path,
                scene["start"],
                scene["end"],
                sample_count=8,
            )
            scene_face_maps.append(face_map)
            if (i + 1) % 5 == 0:
                pct = 25 + int(((i + 1) / len(scene_intervals)) * 10)
                progress(f"Detecting faces (scene {i+1}/{len(scene_intervals)})...", pct)

        # ── 5. Diarization ───────────────────────────────────────────────────
        progress("Loading speaker data...", 36)
        speaker_segments = []
        if job_id:
            speaker_segments = get_speaker_segments(job_id, clip_start, effective_end)
            if speaker_segments:
                print(f"[Reframe] Using diarization: {len(speaker_segments)} segments")
            else:
                print("[Reframe] No diarization found — visual-only mode")
        else:
            print("[Reframe] No job_id — visual-only mode")

        # ── 6. Crop trajectory ───────────────────────────────────────────────
        progress("Calculating crop trajectory...", 40)
        crop_positions = calculate_crop_positions(
            total_frames=total_frames,
            fps=fps,
            src_width=src_w,
            src_height=src_h,
            scene_intervals=scene_intervals,
            scene_face_maps=scene_face_maps,
            speaker_segments=speaker_segments,
        )
        crop_w = compute_crop_width(src_w, src_h)
        print(f"[Reframe] Crop width: {crop_w}px")

        # ── 7. Extract canvas keyframes ──────────────────────────────────────
        progress("Generating keyframes...", 80)
        keyframes = extract_canvas_keyframes(
            crop_positions=crop_positions,
            fps=fps,
            src_w=src_w,
            src_h=src_h,
            crop_w=crop_w,
        )
        print(f"[Reframe] {len(keyframes)} keyframes generated")

        progress("Done!", 100)
        return {
            "keyframes": keyframes,
            "fps": fps,
            "src_w": src_w,
            "src_h": src_h,
            "duration_s": duration_s,
        }

    except Exception as e:
        print(f"[Reframe] Pipeline error: {e}")
        raise

    finally:
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except Exception:
            pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _download_video(url: str, dest_path: str) -> None:
    """Download video from URL to local path using FFmpeg (handles auth headers, etc.)."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", url,
            "-c", "copy",
            dest_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        # Fallback: HTTP download with requests
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
