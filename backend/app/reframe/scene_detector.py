"""
Layer 1 — Scene Detection
Uses FFmpeg's built-in scene filter to detect cuts.
All output is float timestamps (seconds), never frame numbers.
This eliminates FPS drift between video time and timeline time.
"""
import re
import subprocess
from typing import List

from app.reframe.models.types import SceneInterval


# Minimum gap between two accepted cuts (seconds).
# Prevents double-counting a single hard cut that spans 1-2 frames.
_MIN_CUT_GAP_S = 0.5


def detect_scene_cuts(video_path: str, threshold: float = 0.10) -> List[float]:
    """
    Run FFmpeg scene filter and return cut timestamps as floats (seconds).

    The 'scene' value is normalized [0.0, 1.0]:
      0.0 = identical consecutive frames
      1.0 = completely different frames

    Threshold guidance for podcast/talking-head content:
      0.10  — safe default: catches hard camera cuts (typically score 0.10–0.25)
               while ignoring auto-focus pulses, minor lighting flicker (< 0.05)
      0.05  — more sensitive: use if cuts are still missed at 0.10
      0.20  — stricter: use only for high-contrast scene changes

    NOTE: `-vsync vfr` was removed. It is deprecated in FFmpeg 5.0+ (replaced by
    `-fps_mode vfr`) and is unnecessary when the output is `-f null -` (null muxer
    discards all frames regardless of timing). Removing it avoids deprecation
    warnings and silent misbehavior on Railway's FFmpeg 6.x.

    Returns sorted list of cut timestamps, excluding t < 0.5s (opening frames).
    Returns [] if no cuts found (single-scene video).
    """
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null", "-",
        ]
        result = subprocess.run(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=300,
        )

        raw: List[float] = []
        for match in re.finditer(r"pts_time:([\d.]+)", result.stderr):
            t = float(match.group(1))
            if t > 0.5:  # skip opening frames — they always carry noise
                raw.append(round(t, 4))

        if not raw:
            print(
                f"[SceneDetector] 0 cuts at threshold={threshold:.2f}. "
                f"If cuts are expected, lower the threshold (min 0.05)."
            )
            return []

        # Merge cuts that are closer than _MIN_CUT_GAP_S to each other.
        # A single hard cut can trigger showinfo on 2-3 consecutive frames.
        raw.sort()
        merged: List[float] = [raw[0]]
        for t in raw[1:]:
            if t - merged[-1] >= _MIN_CUT_GAP_S:
                merged.append(t)

        print(f"[SceneDetector] {len(raw)} raw triggers → {len(merged)} cuts after merge")
        return merged

    except Exception as e:
        print(f"[SceneDetector] Error detecting scenes: {e}")
        return []


def get_scene_intervals(
    video_path: str,
    duration_s: float,
    threshold: float = 0.10,
) -> List[SceneInterval]:
    """
    Returns a list of SceneInterval covering the full video duration.
    Each interval is [start_s, end_s) in float seconds.

    Example for a 60s video with cuts at 15.2s and 38.7s:
      [SceneInterval(0.0, 15.2), SceneInterval(15.2, 38.7), SceneInterval(38.7, 60.0)]

    Single-scene video: returns [SceneInterval(0.0, duration_s)]
    """
    cuts = detect_scene_cuts(video_path, threshold=threshold)

    boundaries = [0.0] + cuts + [round(duration_s, 4)]
    intervals: List[SceneInterval] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        if end - start > 0.05:  # skip sub-frame rounding artefacts
            intervals.append(SceneInterval(start_s=start, end_s=end))

    # Always return at least one interval
    if not intervals:
        intervals = [SceneInterval(start_s=0.0, end_s=round(duration_s, 4))]

    print(f"[SceneDetector] {len(cuts)} cuts → {len(intervals)} scenes in {duration_s:.1f}s video")
    return intervals
