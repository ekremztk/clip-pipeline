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


def detect_scene_cuts(video_path: str, threshold: float = 0.30) -> List[float]:
    """
    Run FFmpeg scene filter and return cut timestamps as floats (seconds).

    The 'scene' value is normalized [0.0, 1.0]:
      0.0 = identical consecutive frames
      1.0 = completely different frames
    Threshold 0.30 catches hard camera switches while ignoring micro-movements.
    Podcast hard cuts typically score 0.7-0.9.

    Returns sorted, deduplicated list of cut timestamps, excluding t=0.
    Returns [] if no cuts found (single-scene video).
    """
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-vsync", "vfr",
            "-f", "null", "-"
        ]
        result = subprocess.run(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=300,
        )
        cuts: List[float] = []
        for match in re.finditer(r"pts_time:([\d.]+)", result.stderr):
            t = float(match.group(1))
            if t > 0.1:  # skip the very first frame
                cuts.append(round(t, 4))
        return sorted(set(cuts))
    except Exception as e:
        print(f"[SceneDetector] Error detecting scenes: {e}")
        return []


def get_scene_intervals(video_path: str, duration_s: float, threshold: float = 0.30) -> List[SceneInterval]:
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
