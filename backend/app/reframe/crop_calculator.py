"""
Calculates per-frame crop x-offset for the 9:16 reframe.

Logic:
- Source: typically 1920×1080 (16:9)
- Target: 1080×1920 (9:16)
- We crop a (crop_w × src_height) strip from the source, then upscale to 1080×1920

Speaker tracking rules:
1. If diarization available → follow active speaker's face (left=spk0, right=spk1)
2. At scene cuts → instant jump to new scene's face position
3. At speaker switches → instant jump to new speaker's face
4. During same speaker/same scene → smooth EMA (alpha = 0.15, tighter than before)
5. No diarization (speaker = -1) → follow any detected face
6. No face detected for this frame → hold last smoothed position
"""

import numpy as np
from typing import List, Optional


EMA_ALPHA = 0.15        # Tighter smoothing — less overshoot when face moves
MIN_MOVE_PX = 2         # Minimum source-pixel change to trigger EMA update


def compute_crop_width(src_width: int, src_height: int) -> int:
    """Crop width for a 9:16 strip using full source height."""
    return max(1, int(src_height * 9 / 16))


def face_cx_to_crop_x(face_cx_norm: float, src_width: int, crop_w: int) -> int:
    """Convert normalized face center-x to crop x-offset that centers the face."""
    face_px = face_cx_norm * src_width
    desired_x = face_px - crop_w / 2
    return int(np.clip(desired_x, 0, src_width - crop_w))


def calculate_crop_positions(
    total_frames: int,
    fps: float,
    src_width: int,
    src_height: int,
    scene_intervals: List[dict],
    left_cx_timeline: np.ndarray,
    right_cx_timeline: np.ndarray,
    speaker_segments: List[dict],
) -> np.ndarray:
    """
    Returns a 1-D int32 array of length `total_frames` with crop x-offsets.

    left_cx_timeline:  per-frame cx_norm for left-side face (NaN = no face)
    right_cx_timeline: per-frame cx_norm for right-side face (NaN = no face)
    speaker_segments:  [{"speaker": int, "start": float, "end": float}, ...]
    """
    try:
        crop_w = compute_crop_width(src_width, src_height)
        center_x = (src_width - crop_w) // 2

        positions = np.full(total_frames, center_x, dtype=np.int32)
        active_speaker = _build_speaker_array(total_frames, fps, speaker_segments)

        smoothed_x = float(center_x)

        for scene_idx, scene in enumerate(scene_intervals):
            s_start = int(scene["start"])
            s_end = min(int(scene["end"]), total_frames)

            if s_start >= total_frames:
                break

            # Hard reset at scene boundary — snap to new scene's face position
            target_x = _get_target_x(
                s_start, active_speaker, left_cx_timeline, right_cx_timeline,
                src_width, crop_w, center_x,
            )
            smoothed_x = float(target_x)
            prev_speaker = active_speaker[s_start]

            for frame in range(s_start, s_end):
                cur_speaker = active_speaker[frame]

                # Hard jump on speaker switch
                if cur_speaker != prev_speaker:
                    target_x = _get_target_x(
                        frame, active_speaker, left_cx_timeline, right_cx_timeline,
                        src_width, crop_w, center_x,
                    )
                    smoothed_x = float(target_x)
                    prev_speaker = cur_speaker
                else:
                    target_x = _get_target_x(
                        frame, active_speaker, left_cx_timeline, right_cx_timeline,
                        src_width, crop_w, center_x,
                    )
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
    left_cx_timeline: np.ndarray,
    right_cx_timeline: np.ndarray,
    src_width: int,
    crop_w: int,
    center_x: int,
) -> int:
    """
    Returns ideal crop x for this frame.

    Priority:
    - Speaker 0 (HOST): follow left face, fall back to right if left not detected
    - Speaker 1 (GUEST): follow right face, fall back to left if right not detected
    - Speaker -1 (no diarization / silence): follow any detected face
    - No face detected anywhere: return current center (hold position)
    """
    try:
        speaker = int(active_speaker[frame]) if frame < len(active_speaker) else -1

        left = float(left_cx_timeline[frame]) if frame < len(left_cx_timeline) else float("nan")
        right = float(right_cx_timeline[frame]) if frame < len(right_cx_timeline) else float("nan")

        left_ok = not np.isnan(left)
        right_ok = not np.isnan(right)

        if speaker == 0:
            cx = left if left_ok else (right if right_ok else None)
        elif speaker == 1:
            cx = right if right_ok else (left if left_ok else None)
        else:
            # No diarization — follow any face that's detected
            if left_ok and right_ok:
                # Both visible: pick the one closer to center (avoids extreme crop)
                cx = left if abs(left - 0.5) < abs(right - 0.5) else right
            elif left_ok:
                cx = left
            elif right_ok:
                cx = right
            else:
                return center_x

        if cx is None:
            return center_x

        return face_cx_to_crop_x(float(cx), src_width, crop_w)

    except Exception:
        return center_x


def extract_canvas_keyframes(
    crop_positions: np.ndarray,
    fps: float,
    src_w: int,
    src_h: int,
    crop_w: int,
    scene_intervals: Optional[List[dict]] = None,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
    min_delta_canvas_px: float = 25.0,
    min_interval_s: float = 0.5,
) -> list:
    """
    Convert per-frame crop_x array to a minimal keyframe list.

    Each keyframe: {"time_s": float, "offset_x": float, "interpolation": str}

    interpolation values:
      "linear" — smooth motion between this and the next keyframe
      "hold"   — freeze at this value until the next keyframe (used before scene cuts)

    offset_x is canvas pixels:
      0   = source center
      +N  = show left side of source
      -N  = show right side of source

    Scene cuts (from scene_intervals) emit a HOLD keyframe just before the cut and a
    LINEAR keyframe at the cut — this prevents the editor from panning across scene cuts.
    """
    try:
        if len(crop_positions) == 0:
            return []

        cover_scale = max(canvas_w / src_w, canvas_h / src_h)
        scaled_src_w = src_w * cover_scale
        max_offset = (scaled_src_w - canvas_w) / 2

        def crop_x_to_offset(cx: int) -> float:
            cx_norm = (cx + crop_w / 2) / src_w
            raw = scaled_src_w * (0.5 - cx_norm)
            return float(np.clip(raw, -max_offset, max_offset))

        # Build set of frame numbers that are scene cut boundaries
        cut_frames: set = set()
        if scene_intervals:
            for scene in scene_intervals[1:]:   # skip first — no cut before it
                cut_frames.add(int(scene["start"]))

        half_frame = 0.5 / fps
        keyframes = []
        last_kept_offset: float | None = None
        last_keyframe_time: float = -999.0

        for frame_num in range(len(crop_positions)):
            t = frame_num / fps
            offset = crop_x_to_offset(int(crop_positions[frame_num]))

            if frame_num == 0:
                keyframes.append({
                    "time_s": round(t, 4),
                    "offset_x": round(offset, 2),
                    "interpolation": "linear",
                })
                last_kept_offset = offset
                last_keyframe_time = t
                continue

            if frame_num in cut_frames:
                # Known scene cut — hold at previous position then snap to new one.
                prev_offset = crop_x_to_offset(int(crop_positions[frame_num - 1]))
                hold_t = max(0.0, round(t - half_frame, 4))
                keyframes.append({
                    "time_s": hold_t,
                    "offset_x": round(prev_offset, 2),
                    "interpolation": "hold",
                })
                keyframes.append({
                    "time_s": round(t, 4),
                    "offset_x": round(offset, 2),
                    "interpolation": "linear",
                })
                last_kept_offset = offset
                last_keyframe_time = t

            elif (
                last_kept_offset is not None
                and abs(offset - last_kept_offset) >= min_delta_canvas_px
                and (t - last_keyframe_time) >= min_interval_s
            ):
                keyframes.append({
                    "time_s": round(t, 4),
                    "offset_x": round(offset, 2),
                    "interpolation": "linear",
                })
                last_kept_offset = offset
                last_keyframe_time = t

        # Always include last frame
        last_t = (len(crop_positions) - 1) / fps
        last_offset = crop_x_to_offset(int(crop_positions[-1]))
        if not keyframes or keyframes[-1]["time_s"] < round(last_t - half_frame, 4):
            keyframes.append({
                "time_s": round(last_t, 4),
                "offset_x": round(last_offset, 2),
                "interpolation": "linear",
            })

        return keyframes

    except Exception as e:
        print(f"[CropCalculator] extract_canvas_keyframes error: {e}")
        return [{"time_s": 0.0, "offset_x": 0.0, "interpolation": "linear"}]


def _build_speaker_array(
    total_frames: int,
    fps: float,
    speaker_segments: List[dict],
) -> np.ndarray:
    """
    Returns int8 array of length total_frames.
    0 = Speaker 0 (HOST), 1 = Speaker 1 (GUEST), -1 = unknown/silence.
    Forward-fills silence gaps with the last known speaker.
    """
    arr = np.full(total_frames, -1, dtype=np.int8)

    if not speaker_segments or fps <= 0:
        return arr

    for seg in speaker_segments:
        f_start = max(0, int(seg["start"] * fps))
        f_end = min(total_frames, int(seg["end"] * fps))
        arr[f_start:f_end] = int(seg["speaker"])

    last = -1
    for i in range(total_frames):
        if arr[i] >= 0:
            last = arr[i]
        elif last >= 0:
            arr[i] = last

    return arr
