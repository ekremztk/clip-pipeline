"""
Sahne tespiti — FFmpeg scene filter kullanarak.
SSIM dogrulamasi YOK. FFmpeg'e guveniyoruz.
Talk show / podcast iceriklerde kamera acisi degisikliklerini tespit eder.
"""
import logging
import re
import subprocess

from .config import ShotDetectionConfig
from .types import Shot

logger = logging.getLogger(__name__)


def detect_shots(
    video_path: str,
    duration_s: float,
    config: ShotDetectionConfig,
    fps: float,
) -> list[Shot]:
    """
    Video'daki sahne kesimlerini tespit et.
    FFmpeg scene filter → yakin kesimleri birlestir → Shot listesi.
    Hicbir kesim bulunamazsa tum video tek shot olarak doner.
    """
    try:
        # 1. FFmpeg scene filter
        cut_times = _ffmpeg_scene_detect(video_path, config.threshold, fps)
        logger.info("[ShotDetector] FFmpeg ham kesim sayisi: %d", len(cut_times))

        # 2. Yakin kesimleri birlestir
        cut_times = _merge_nearby(cut_times, config.min_cut_gap_s)

        # 3. Kesimlerden Shot listesi olustur
        shots = _cuts_to_shots(cut_times, duration_s)

        # 4. Cok kisa shot'lari birlestir
        shots = _merge_short_shots(shots, config.min_shot_duration_s)

        for s in shots:
            logger.info(
                "[ShotDetector] Shot %.2f-%.2fs (%.2fs)",
                s.start_s, s.end_s, s.duration_s,
            )
        return shots

    except Exception as e:
        logger.error("[ShotDetector] Hata: %s — tek shot fallback", e)
        return [Shot(start_s=0.0, end_s=duration_s)]


# --- FFmpeg -------------------------------------------------------------------

def _ffmpeg_scene_detect(video_path: str, threshold: float, fps: float) -> list[float]:
    """FFmpeg scene filter ile kesim zamanlarini bul.

    pts (tam sayi frame numarasi) kullanir, pts_time float'u degil.
    time_base = 1/fps → time_s = pts / fps
    Bu sayede kayan nokta precision hatalari olmadan tam frame sinirinda zaman hesaplanir.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "0",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        time_base = 1.0 / fps if fps > 0 else 1.0 / 30.0
        times: list[float] = []
        for match in re.finditer(r"\bpts:(\d+)\b", result.stderr):
            pts = int(match.group(1))
            time_s = round(pts * time_base, 6)
            times.append(time_s)
        return sorted(set(times))
    except subprocess.TimeoutExpired:
        logger.error("[ShotDetector] FFmpeg timeout")
        return []
    except Exception as e:
        logger.error("[ShotDetector] FFmpeg hatasi: %s", e)
        return []


# --- Post-processing ----------------------------------------------------------

def _merge_nearby(cuts: list[float], min_gap: float) -> list[float]:
    """Birbirine cok yakin kesimleri birlestir (ilkini tut)."""
    if not cuts:
        return []
    merged = [cuts[0]]
    for c in cuts[1:]:
        if c - merged[-1] >= min_gap:
            merged.append(c)
    return merged


def _cuts_to_shots(cuts: list[float], duration_s: float) -> list[Shot]:
    """Kesim noktalarindan Shot listesi olustur."""
    boundaries = [0.0] + cuts + [duration_s]
    shots: list[Shot] = []
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        if e > s:
            shots.append(Shot(start_s=s, end_s=e))
    return shots if shots else [Shot(start_s=0.0, end_s=duration_s)]


def _merge_short_shots(shots: list[Shot], min_dur: float) -> list[Shot]:
    """Cok kisa shot'lari bir sonrakiyle birlestir."""
    if len(shots) <= 1:
        return shots
    merged: list[Shot] = []
    for shot in shots:
        if merged and shot.duration_s < min_dur:
            # Oncekinin sonunu uzat
            prev = merged[-1]
            merged[-1] = Shot(start_s=prev.start_s, end_s=shot.end_s)
        else:
            merged.append(Shot(start_s=shot.start_s, end_s=shot.end_s))
    return merged
