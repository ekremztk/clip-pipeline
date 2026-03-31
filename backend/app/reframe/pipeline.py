"""
Reframe V3 — Ana orkestrator.

Pipeline adimlari:
  1. Video download (gerekirse)
  2. ffprobe → src_w, src_h, fps, duration_s
  3. detect_shots() → Shot listesi
  4. analyze_shots() → FrameAnalysis listesi
  5. Diarization yukle (varsa)
  6. select_focus_points() → FocusPoint listesi
  7. compute_camera_path() → SmoothedPoint listesi
  8. emit_keyframes() → ReframeResult
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
from .frame_analyzer import analyze_shots
from .focus_selector import select_focus_points
from .camera_path import compute_camera_path
from .keyframe_emitter import emit_keyframes
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
    tracking_mode: str = "x_only",
    content_type_hint: Optional[str] = None,
    on_progress: Optional[Callable[[str, int], None]] = None,
) -> ReframeResult:
    """
    V3 reframe pipeline. Fonksiyon imzasi V2 ile ayni — frontend degisiklik gerektirmez.
    """
    if not clip_url and not clip_local_path:
        raise ValueError("clip_url veya clip_local_path zorunlu")

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

    temp_path: Optional[str] = None

    # Input path cozumle
    if clip_local_path and os.path.exists(clip_local_path):
        input_path = clip_local_path
    else:
        temp_path = os.path.join(
            str(settings.UPLOAD_DIR),
            f"reframe_{uuid.uuid4().hex}.mp4",
        )
        input_path = temp_path

    try:
        # 1. Video indir (gerekirse)
        if temp_path:
            progress("Downloading video...", 5)
            _download_video(clip_url, temp_path)

        # 2. Video metadata
        progress("Reading video metadata...", 8)
        src_w, src_h, fps, duration_s = _probe_video(input_path)
        logger.info("[Reframe] %dx%d @ %.2ffps, %.2fs", src_w, src_h, fps, duration_s)

        effective_end = clip_end if clip_end is not None else duration_s

        # 3. Shot detection
        progress("Detecting scene cuts...", 12)
        shots = detect_shots(input_path, duration_s, config.shot_detection)
        logger.info("[Reframe] %d shot tespit edildi", len(shots))

        # 4. Frame analysis
        progress("Analyzing frames...", 20)
        frame_analyses = analyze_shots(
            input_path, shots, src_w, src_h, config.frame_analysis,
        )
        logger.info("[Reframe] %d frame analiz edildi", len(frame_analyses))

        # 5. Diarization yukle
        progress("Loading speaker data...", 55)
        diarization_segments: list[dict] = []
        if job_id:
            try:
                diarization_segments = _load_diarization(job_id, clip_start, effective_end)
                logger.info("[Reframe] %d diarization segmenti", len(diarization_segments))
            except Exception as e:
                logger.warning("[Reframe] Diarization yuklenemedi: %s — visual-only", e)

        # 6. Focus selection (Gemini semantic + diarization fallback)
        progress("Selecting focus points...", 65)

        # Build transcript context for Gemini (first 1000 chars of word timestamps)
        transcript_context = ""
        if diarization_segments:
            transcript_context = " | ".join(
                f"[{s.get('start', 0):.1f}-{s.get('end', 0):.1f}s] speaker_{s.get('speaker', 0)}"
                for s in diarization_segments[:30]
            )

        focus_points = select_focus_points(
            frame_analyses, diarization_segments, shots, src_w, config.focus_selection,
            video_path=input_path,
            transcript_context=transcript_context,
            gemini_config=config.gemini_director,
        )

        # 7. Camera path
        progress("Computing camera path...", 75)
        smooth_points = compute_camera_path(focus_points, shots, config.camera_path)

        # 8. Keyframe emission
        progress("Generating keyframes...", 85)
        result = emit_keyframes(
            smooth_points, shots, src_w, src_h, fps, duration_s, config,
        )

        progress("Done!", 100)
        logger.info(
            "[Reframe] Tamamlandi — %d keyframe, %d scene cut",
            len(result.keyframes), len(result.scene_cuts),
        )
        return result

    except Exception as e:
        logger.error("[Reframe] Pipeline hatasi: %s", e)
        import traceback
        traceback.print_exc()
        raise

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# --- Video yardimcilari -------------------------------------------------------

def _probe_video(video_path: str) -> tuple[int, int, float, float]:
    """ffprobe ile video boyutlari, FPS ve suresini al."""
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
        raise RuntimeError(f"ffprobe hatasi: {result.stderr[:200]}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("ffprobe video stream bulamadi")

    stream = streams[0]
    src_w = int(stream.get("width", 0))
    src_h = int(stream.get("height", 0))
    if src_w == 0 or src_h == 0:
        raise RuntimeError(f"Gecersiz video boyutu: {src_w}x{src_h}")

    # FPS
    r_frame_rate = stream.get("r_frame_rate", "30/1")
    try:
        num, den = r_frame_rate.split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 30.0

    # Sure
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
        raise RuntimeError("Video suresi belirlenemedi")

    return src_w, src_h, round(fps, 4), round(duration_s, 4)


def _download_video(url: str, dest_path: str) -> None:
    """Uzak videoyu indir. FFmpeg basarisiz olursa requests ile dene."""
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
    """'9:16' → (9, 16). Gecersizse (9, 16) fallback."""
    try:
        parts = ratio_str.strip().split(":")
        w, h = int(parts[0]), int(parts[1])
        if w > 0 and h > 0:
            return (w, h)
    except Exception:
        pass
    return (9, 16)


# --- Diarization yukleyici ----------------------------------------------------

def _load_diarization(
    job_id: str,
    clip_start: float,
    clip_end: float,
) -> list[dict]:
    """
    Supabase'den diarization verisini yukle.
    Deepgram word_timestamps'ten konusmaci segmentleri olusturur,
    clip zamanina gore filtreler ve klip-relative zamana cevirir.
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
        logger.warning("[Diarization] Transcript bulunamadi: job_id=%s", job_id)
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

    # Kelimelerden konusmaci segmentleri olustur
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

    # Clip penceresine filtrele ve klip-relative zamana cevir
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

    logger.info("[Diarization] %d segment (clip %.1f-%.1fs)", len(clip_segments), clip_start, clip_end)
    return clip_segments
