"""
Scene cut detection using PySceneDetect (CPU-only).
Returns list of scene boundaries as frame numbers.
"""

import subprocess
import json
import os
from typing import List


def detect_scene_cuts(video_path: str, threshold: float = 27.0) -> List[int]:
    """
    Detect scene cuts using scenedetect library.
    Returns list of frame numbers where scene cuts occur (the first frame of each new scene).

    Falls back to empty list (treat entire video as one scene) on failure.
    """
    try:
        from scenedetect import detect, ContentDetector
        scene_list = detect(video_path, ContentDetector(threshold=threshold))

        # scene_list is list of (start_timecode, end_timecode)
        # We want the start frame of each scene (except the first)
        cut_frames = []
        for i, (start_tc, _end_tc) in enumerate(scene_list):
            if i == 0:
                continue
            cut_frames.append(int(start_tc.get_frames()))

        print(f"[SceneDetector] Found {len(cut_frames)} scene cuts in {video_path}")
        return cut_frames

    except ImportError:
        print("[SceneDetector] scenedetect not installed — treating video as one scene")
        return []
    except Exception as e:
        print(f"[SceneDetector] Error: {e}")
        return []


def get_scene_intervals(video_path: str, total_frames: int, threshold: float = 27.0) -> List[dict]:
    """
    Returns list of scene intervals:
    [{"start": frame_num, "end": frame_num}, ...]
    """
    try:
        cut_frames = detect_scene_cuts(video_path, threshold)

        # Build intervals from cut frames
        boundaries = [0] + cut_frames + [total_frames]
        intervals = []
        for i in range(len(boundaries) - 1):
            intervals.append({
                "start": boundaries[i],
                "end": boundaries[i + 1],
            })

        return intervals

    except Exception as e:
        print(f"[SceneDetector] get_scene_intervals error: {e}")
        return [{"start": 0, "end": total_frames}]
