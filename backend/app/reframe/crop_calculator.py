"""
Calculates per-frame crop x-offset for the 9:16 reframe.

Logic:
- Source: typically 1920×1080 (16:9)
- Target: 1080×1920 (9:16)
- We crop a (crop_w × src_height) strip from the source, then upscale to 1080×1920

Speaker tracking rules:
1. If diarization available → follow active speaker's face position
2. At scene cuts → instant jump (no EMA bleed)
3. At speaker switches → instant jump
4. During same speaker/same scene → smooth EMA (alpha = 0.25)
5. No active speaker (silence/gap) → hold last position
6. No faces detected in scene → use center
"""

import numpy as np
from typing import List, Optional


# EMA smoothing factor within a continuous segment (higher = faster response)
EMA_ALPHA = 0.25

# How many pixels of change are considered "no real movement" (suppressed)
MIN_MOVE_PX = 3


def compute_crop_width(src_width: int, src_height: int) -> int:
    """
    Crop width needed to extract a 9:16 strip from the source frame.
    We use the full source height, so crop_width = src_height * (9/16).
    """
    return max(1, int(src_height * 9 / 16))


def face_cx_to_crop_x(
    face_cx_norm: float,
    src_width: int,
    crop_w: int,
) -> int:
    """
    Convert normalized face center-x to the crop x-offset that centers the face.
    Clamped to [0, src_width - crop_w].
    """
    face_px = face_cx_norm * src_width
    desired_x = face_px - crop_w / 2
    return int(np.clip(desired_x, 0, src_width - crop_w))


def calculate_crop_positions(
    total_frames: int,
    fps: float,
    src_width: int,
    src_height: int,
    scene_intervals: List[dict],
    scene_face_maps: List[List[float]],
    speaker_segments: List[dict],
) -> np.ndarray:
    """
    Returns a 1-D int32 array of length `total_frames` with crop x-offsets.

    scene_intervals: [{"start": int, "end": int}, ...]
    scene_face_maps: parallel list; scene_face_maps[i] = [left_cx, right_cx] or [single_cx]
    speaker_segments: [{"speaker": int, "start": float, "end": float}, ...]
    """
    try:
        crop_w = compute_crop_width(src_width, src_height)
        center_x = (src_width - crop_w) // 2

        positions = np.full(total_frames, center_x, dtype=np.int32)

        # Build a per-frame active-speaker array from diarization
        active_speaker = _build_speaker_array(total_frames, fps, speaker_segments)

        smoothed_x = float(center_x)

        for scene_idx, scene in enumerate(scene_intervals):
            s_start = int(scene["start"])
            s_end = min(int(scene["end"]), total_frames)

            if s_start >= total_frames:
                break

            face_map = scene_face_maps[scene_idx] if scene_idx < len(scene_face_maps) else [0.5]

            # Hard reset at scene boundary
            target_x = _get_target_x(s_start, active_speaker, face_map, src_width, crop_w, center_x)
            smoothed_x = float(target_x)

            prev_speaker = active_speaker[s_start] if s_start < total_frames else None

            for frame in range(s_start, s_end):
                cur_speaker = active_speaker[frame]

                # Hard jump on speaker switch
                if cur_speaker != prev_speaker:
                    target_x = _get_target_x(frame, active_speaker, face_map, src_width, crop_w, center_x)
                    smoothed_x = float(target_x)
                    prev_speaker = cur_speaker
                else:
                    target_x = _get_target_x(frame, active_speaker, face_map, src_width, crop_w, center_x)
                    diff = target_x - smoothed_x
                    if abs(diff) > MIN_MOVE_PX:
                        smoothed_x = EMA_ALPHA * target_x + (1.0 - EMA_ALPHA) * smoothed_x

                positions[frame] = int(np.clip(smoothed_x, 0, src_width - crop_w))

        return positions

    except Exception as e:
        print(f"[CropCalculator] Error: {e}")
        crop_w = compute_crop_width(src_width, src_height)
        center_x = (src_width - crop_w) // 2
        return np.full(total_frames, center_x, dtype=np.int32)


def _get_target_x(
    frame: int,
    active_speaker: np.ndarray,
    face_map: List[float],
    src_width: int,
    crop_w: int,
    center_x: int,
) -> int:
    """
    Returns the ideal crop x for this frame based on active speaker and face map.
    """
    try:
        speaker = int(active_speaker[frame]) if frame < len(active_speaker) else -1

        if speaker < 0 or len(face_map) == 0:
            return center_x

        # Clamp speaker index to available faces
        face_idx = min(speaker, len(face_map) - 1)
        cx_norm = face_map[face_idx]
        return face_cx_to_crop_x(cx_norm, src_width, crop_w)

    except Exception:
        return center_x


def _build_speaker_array(
    total_frames: int,
    fps: float,
    speaker_segments: List[dict],
) -> np.ndarray:
    """
    Returns int8 array of length total_frames.
    Value: 0 = Speaker 0, 1 = Speaker 1, -1 = unknown/silence.
    Uses last-speaker hold for gaps.
    """
    arr = np.full(total_frames, -1, dtype=np.int8)

    if not speaker_segments or fps <= 0:
        return arr

    # Fill in known speaker ranges
    for seg in speaker_segments:
        f_start = int(seg["start"] * fps)
        f_end = int(seg["end"] * fps)
        f_start = max(0, f_start)
        f_end = min(total_frames, f_end)
        arr[f_start:f_end] = int(seg["speaker"])

    # Forward-fill silence gaps with last known speaker
    last = -1
    for i in range(total_frames):
        if arr[i] >= 0:
            last = arr[i]
        elif last >= 0:
            arr[i] = last

    return arr
