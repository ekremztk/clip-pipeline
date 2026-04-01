"""
Debug Overlay — burns pipeline internals onto the video for visual QA.

Draws on each frame:
  GREEN  rectangle → MediaPipe face detection bbox
  RED    circle    → Focus resolver target point (what path solver receives)
  BLUE   circle    → Path solver smooth path position
  YELLOW rectangle → Final crop window (what frontend gets)
  WHITE  text      → Shot type, strategy, Gemini directive, offset math

Upload the result to R2 and return a public URL.
"""
import logging
import os
import tempfile
from typing import Optional

import cv2
import numpy as np

from .types import (
    Frame,
    FocusPoint,
    ReframeKeyframe,
    Shot,
    ShotPath,
)

logger = logging.getLogger(__name__)


def generate_debug_video(
    input_path: str,
    src_w: int,
    src_h: int,
    fps: float,
    shots: list[Shot],
    frames: list[Frame],
    focus_points: list[FocusPoint],
    shot_paths: list[ShotPath],
    keyframes: list[ReframeKeyframe],
    crop_w: int,
    crop_h: int,
) -> str:
    """
    Generate a debug video with all pipeline overlays burned in.
    Returns path to the output video file.
    """
    output_path = input_path.replace(".mp4", "_debug.mp4").replace(
        "temp_uploads", "temp_uploads"
    )
    if output_path == input_path:
        output_path = input_path + "_debug.mp4"

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (src_w, src_h))

    # Build lookup maps keyed by time for fast access
    face_by_time = {f.time_s: f for f in frames}
    focus_by_time = {fp.time_s: fp for fp in focus_points}

    # Build smooth path map: time_s -> (x, y)
    path_map: dict[float, tuple[float, float]] = {}
    for sp in shot_paths:
        for pt in sp.points:
            path_map[pt.time_s] = (pt.x, pt.y)

    # Get shot for each time
    def get_shot(t: float) -> Optional[Shot]:
        for s in shots:
            if s.start_s <= t < s.end_s:
                return s
        return shots[-1] if shots else None

    def get_path_at(t: float) -> Optional[tuple[float, float]]:
        """Interpolate smooth path position at time t."""
        times = sorted(path_map.keys())
        if not times:
            return None
        if t <= times[0]:
            return path_map[times[0]]
        if t >= times[-1]:
            return path_map[times[-1]]
        for i in range(len(times) - 1):
            t0, t1 = times[i], times[i + 1]
            if t0 <= t <= t1:
                x0, y0 = path_map[t0]
                x1, y1 = path_map[t1]
                alpha = (t - t0) / (t1 - t0)
                return (x0 + (x1 - x0) * alpha, y0 + (y1 - y0) * alpha)
        return None

    def get_keyframe_at(t: float) -> Optional[ReframeKeyframe]:
        """Get active keyframe at time t (last keyframe before t)."""
        active = None
        for kf in keyframes:
            if kf.time_s <= t:
                active = kf
            else:
                break
        return active

    def get_strategy_at(t: float) -> str:
        for sp in shot_paths:
            if shots and sp.shot_index < len(shots):
                s = shots[sp.shot_index]
                if s.start_s <= t < s.end_s:
                    return sp.strategy
        return "?"

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        t = frame_count / fps

        # --- Draw overlays ---
        overlay = frame.copy()

        shot = get_shot(t)
        shot_type = shot.shot_type if shot else "?"
        strategy = get_strategy_at(t)

        # Find nearest analyzed frame (within 0.15s)
        nearest_frame = None
        best_dist = 0.15
        for ft, ff in face_by_time.items():
            dist = abs(ft - t)
            if dist < best_dist:
                best_dist = dist
                nearest_frame = ff

        # GREEN: MediaPipe face bboxes
        if nearest_frame:
            for face in nearest_frame.faces:
                x1 = int((face.face_x - face.face_width / 2) * src_w)
                y1 = int((face.face_y - face.face_height / 2) * src_h)
                x2 = int((face.face_x + face.face_width / 2) * src_w)
                y2 = int((face.face_y + face.face_height / 2) * src_h)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"ID:{face.track_id} conf:{face.confidence:.2f}"
                cv2.putText(overlay, label, (x1, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        # RED: Focus resolver target point
        nearest_focus = None
        best_dist = 0.15
        for ft, fp in focus_by_time.items():
            dist = abs(ft - t)
            if dist < best_dist:
                best_dist = dist
                nearest_focus = fp

        if nearest_focus:
            fx = int(nearest_focus.x * src_w)
            fy = int(nearest_focus.y * src_h)
            cv2.circle(overlay, (fx, fy), 12, (0, 0, 255), -1)
            cv2.putText(overlay, f"Focus w={nearest_focus.weight:.1f}",
                        (fx + 14, fy + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)

        # BLUE: Path solver smooth position
        smooth = get_path_at(t)
        if smooth:
            sx = int(smooth[0] * src_w)
            sy = int(smooth[1] * src_h)
            cv2.circle(overlay, (sx, sy), 10, (255, 100, 0), -1)
            cv2.putText(overlay, f"Path ({smooth[0]:.3f},{smooth[1]:.3f})",
                        (sx + 14, sy - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 100, 0), 1)

        # YELLOW: Final crop rectangle
        active_kf = get_keyframe_at(t)
        if active_kf:
            ox = active_kf.offset_x
            oy = active_kf.offset_y
            cx1 = int(ox)
            cy1 = int(oy)
            cx2 = int(ox + crop_w)
            cy2 = int(oy + crop_h)
            cv2.rectangle(overlay, (cx1, cy1), (cx2, cy2), (0, 255, 255), 3)

        # Blend overlay with original (semi-transparent)
        frame = cv2.addWeighted(overlay, 0.85, frame, 0.15, 0)

        # WHITE text panel (top-left)
        info_lines = [
            f"t={t:.2f}s  shot={shot_type}  strategy={strategy}",
        ]
        if active_kf:
            # Show the coordinate math
            info_lines.append(
                f"offset_x = center_x*src_w - crop_w/2"
            )
            info_lines.append(
                f"  = {active_kf.offset_x + crop_w/2:.0f} - {crop_w/2:.0f} = {active_kf.offset_x:.1f}px"
            )
            info_lines.append(
                f"offset_y={active_kf.offset_y:.1f}px  crop={crop_w}x{crop_h}"
            )

        for i, line in enumerate(info_lines):
            y_pos = 22 + i * 20
            cv2.putText(frame, line, (8, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
            cv2.putText(frame, line, (8, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Legend (bottom-left)
        legend = [
            ("GREEN = MediaPipe face bbox", (0, 255, 0)),
            ("RED = Focus resolver target", (0, 0, 255)),
            ("BLUE = Path solver smooth pos", (255, 100, 0)),
            ("YELLOW = Final crop window", (0, 255, 255)),
        ]
        for i, (text, color) in enumerate(legend):
            y_pos = src_h - 20 - (len(legend) - 1 - i) * 20
            cv2.putText(frame, text, (8, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2)
            cv2.putText(frame, text, (8, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        out.write(frame)
        frame_count += 1

    cap.release()
    out.release()

    logger.info("[DebugOverlay] Debug video written: %s (%d frames)", output_path, frame_count)
    return output_path
