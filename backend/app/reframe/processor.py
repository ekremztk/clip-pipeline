"""
Main reframe processor.
Pipeline:
  1. Download video from R2 URL → temp file
  2. Detect scenes
  3. Detect face positions per scene
  4. Fetch diarization (if job/clip IDs provided)
  5. Calculate per-frame crop positions
  6. Encode: read → crop → resize → pipe to FFmpeg
  7. Merge audio
  8. Upload to R2
  9. Cleanup
"""

import os
import uuid
import subprocess
import requests
import cv2
import numpy as np
from typing import Callable, Optional

from app.reframe.scene_detector import get_scene_intervals
from app.reframe.face_detector import build_scene_face_map
from app.reframe.diarization import get_speaker_segments
from app.reframe.crop_calculator import calculate_crop_positions, compute_crop_width
from app.services.r2_client import upload_clip
from app.config import settings

TARGET_W = 1080
TARGET_H = 1920


def run_reframe(
    clip_url: str,
    clip_id: Optional[str] = None,
    job_id: Optional[str] = None,
    clip_start: float = 0.0,
    clip_end: Optional[float] = None,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> str:
    """
    Full reframe pipeline. Returns R2 URL of the output 9:16 video.
    on_progress(step_label, percent) called throughout.
    """

    def progress(step: str, pct: int):
        print(f"[Reframe] {pct}% — {step}")
        if on_progress:
            on_progress(step, pct)

    temp_dir = os.path.join(str(settings.UPLOAD_DIR), f"reframe_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=True)

    input_path = os.path.join(temp_dir, "input.mp4")
    video_only_path = os.path.join(temp_dir, "video_only.mp4")
    output_path = os.path.join(temp_dir, "output.mp4")

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
                print("[Reframe] No diarization found — using visual-only mode")
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
        print(f"[Reframe] Crop width: {crop_w}px → upscale to {TARGET_W}x{TARGET_H}")

        # ── 7. Encode video (no audio) ───────────────────────────────────────
        progress("Encoding video...", 45)
        _encode_frames(
            input_path=input_path,
            output_path=video_only_path,
            crop_positions=crop_positions,
            crop_w=crop_w,
            src_h=src_h,
            target_w=TARGET_W,
            target_h=TARGET_H,
            fps=fps,
            total_frames=total_frames,
            on_frame_progress=lambda pct: progress(f"Encoding... {pct}%", 45 + int(pct * 0.35)),
        )

        # ── 8. Merge audio ───────────────────────────────────────────────────
        progress("Merging audio...", 82)
        _merge_audio(video_only_path, input_path, output_path)

        # ── 9. Upload to R2 ──────────────────────────────────────────────────
        progress("Uploading to storage...", 90)
        reframe_job_id = f"reframe_{clip_id or uuid.uuid4().hex}"
        filename = f"reframe_{uuid.uuid4().hex}.mp4"
        r2_url = upload_clip(reframe_job_id, filename, output_path)
        print(f"[Reframe] Uploaded: {r2_url}")

        progress("Done!", 100)
        return r2_url

    except Exception as e:
        print(f"[Reframe] Pipeline error: {e}")
        raise

    finally:
        for path in [input_path, video_only_path, output_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _download_video(url: str, dest_path: str) -> None:
    """Download video from URL to local path using FFmpeg (handles auth headers, CORS, etc.)."""
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


def _encode_frames(
    input_path: str,
    output_path: str,
    crop_positions: np.ndarray,
    crop_w: int,
    src_h: int,
    target_w: int,
    target_h: int,
    fps: float,
    total_frames: int,
    on_frame_progress: Callable[[int], None],
) -> None:
    """
    Read source video frame-by-frame, crop and resize, pipe to FFmpeg for H.264 encoding.
    Audio is excluded here (merged separately).
    """
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{target_w}x{target_h}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-preset", settings.FFMPEG_PRESET,
        "-crf", str(settings.FFMPEG_CRF),
        "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]

    cap = cv2.VideoCapture(input_path)
    pipe = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        frame_num = 0
        report_every = max(1, total_frames // 20)

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Crop
            crop_x = int(crop_positions[frame_num]) if frame_num < len(crop_positions) else (src_h * 9 // 16)
            crop_x = max(0, min(crop_x, frame.shape[1] - crop_w))
            cropped = frame[:, crop_x: crop_x + crop_w]

            # Resize to target
            resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

            pipe.stdin.write(resized.tobytes())

            frame_num += 1
            if frame_num % report_every == 0:
                on_frame_progress(int(frame_num / total_frames * 100))

    finally:
        cap.release()
        try:
            pipe.stdin.close()
        except Exception:
            pass
        pipe.wait()

    if pipe.returncode != 0:
        raise RuntimeError(f"FFmpeg encoding failed (exit {pipe.returncode})")


def _merge_audio(video_path: str, audio_source_path: str, output_path: str) -> None:
    """Merge video track from video_path with audio track from audio_source_path."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_source_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "320k",
        output_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode != 0:
        # If source has no audio track, just copy video
        cmd_no_audio = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-c:v", "copy",
            output_path,
        ]
        subprocess.run(cmd_no_audio, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
