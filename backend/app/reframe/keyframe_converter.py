"""
Keyframe Converter — transforms anchored segments into pixel-offset keyframes.

Pure deterministic conversion. No AI, no heuristics, no EMA smoothing.
Takes AnchoredSegments (validated positions) and produces ReframeKeyframes
(pixel offsets for the frontend editor).

Transition types:
  "cut"    → hold keyframe at old position + linear at new position (instant jump)
  "smooth" → linear keyframes over a configurable transition window

Coordinate system:
  Input:  normalized (0.0-1.0) center positions from YOLO
  Output: pixel offsets (crop top-left corner) for the frontend
"""
import logging

from .config import KeyframeConfig, ReframeConfig
from .types import AnchoredSegment, ReframeKeyframe, ReframeResult, Shot

logger = logging.getLogger(__name__)


def convert_to_keyframes(
    anchored_segments: list[AnchoredSegment],
    shots: list[Shot],
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    config: ReframeConfig,
) -> ReframeResult:
    """
    Convert anchored segments to pixel-offset keyframes.

    Each segment's positions are converted to crop offsets. Transitions between
    segments use "cut" (hold+linear) or "smooth" (linear over transition window).
    """
    kf_config = config.keyframe
    ar_w, ar_h = config.aspect_ratio

    # Compute crop dimensions (must match frontend containScale logic)
    if config.tracking_mode == "dynamic_xy" and kf_config.y_headroom_zoom > 1.0:
        crop_h = int(src_h / kf_config.y_headroom_zoom)
        crop_w = min(int(crop_h * (ar_w / ar_h)), src_w)
    else:
        crop_w = min(int(src_h * (ar_w / ar_h)), src_w)
        crop_h = src_h

    frame_dur = 1.0 / fps if fps > 0 else 1.0 / 30.0

    logger.info(
        "[KeyframeConverter] crop=%dx%d, src=%dx%d, mode=%s, zoom=%.2f",
        crop_w, crop_h, src_w, src_h, config.tracking_mode, kf_config.y_headroom_zoom,
    )

    keyframes: list[ReframeKeyframe] = []
    last_ox: float = -999.0
    last_oy: float = -999.0

    for seg_idx, seg in enumerate(anchored_segments):
        if not seg.positions:
            continue

        # First position of this segment
        first_pos = seg.positions[0]
        first_ox = _to_offset_x(first_pos.x, src_w, crop_w)
        first_oy = _to_offset_y(first_pos.y, src_h, crop_h) if config.tracking_mode == "dynamic_xy" else 0.0
        first_ox = _clamp(round(first_ox, 1), 0.0, max(0, src_w - crop_w))
        first_oy = _clamp(round(first_oy, 1), 0.0, max(0, src_h - crop_h))

        # Handle transition INTO this segment
        if seg_idx == 0:
            # First segment: start directly at position
            keyframes.append(ReframeKeyframe(
                time_s=round(seg.start_s, 4),
                offset_x=first_ox,
                offset_y=first_oy,
                interpolation="linear",
            ))

        elif seg.transition_in == "cut":
            # Hard cut: hold previous position just before, then jump to new
            hold_time = max(
                keyframes[-1].time_s + 0.001 if keyframes else 0.0,
                seg.start_s - frame_dur,
            )
            # Hold at previous position
            keyframes.append(ReframeKeyframe(
                time_s=round(hold_time, 4),
                offset_x=last_ox,
                offset_y=last_oy,
                interpolation="hold",
            ))
            # Jump to new position
            keyframes.append(ReframeKeyframe(
                time_s=round(seg.start_s, 4),
                offset_x=first_ox,
                offset_y=first_oy,
                interpolation="linear",
            ))

        elif seg.transition_in == "smooth":
            # Smooth: linear interpolation over transition window
            # The frontend will interpolate between last keyframe and this one
            keyframes.append(ReframeKeyframe(
                time_s=round(seg.start_s, 4),
                offset_x=first_ox,
                offset_y=first_oy,
                interpolation="linear",
            ))

        last_ox = first_ox
        last_oy = first_oy

        # Emit keyframes for positions WITHIN the segment (tracking movement)
        for pos in seg.positions[1:]:
            ox = _to_offset_x(pos.x, src_w, crop_w)
            oy = _to_offset_y(pos.y, src_h, crop_h) if config.tracking_mode == "dynamic_xy" else 0.0
            ox = _clamp(round(ox, 1), 0.0, max(0, src_w - crop_w))
            oy = _clamp(round(oy, 1), 0.0, max(0, src_h - crop_h))

            # Dedup: skip if movement is below threshold
            if (abs(ox - last_ox) < kf_config.dedup_threshold_px
                    and abs(oy - last_oy) < kf_config.dedup_threshold_px):
                continue

            keyframes.append(ReframeKeyframe(
                time_s=round(pos.time_s, 4),
                offset_x=ox,
                offset_y=oy,
                interpolation="linear",
            ))
            last_ox = ox
            last_oy = oy

    # Pin last position to video end
    if keyframes and keyframes[-1].time_s < duration_s - frame_dur:
        keyframes.append(ReframeKeyframe(
            time_s=round(duration_s, 4),
            offset_x=keyframes[-1].offset_x,
            offset_y=keyframes[-1].offset_y,
            interpolation="linear",
        ))

    # Fallback: at least 1 keyframe (center crop)
    if not keyframes:
        center_ox = _clamp(_to_offset_x(0.5, src_w, crop_w), 0.0, max(0, src_w - crop_w))
        keyframes = [ReframeKeyframe(
            time_s=0.0, offset_x=round(center_ox, 1), offset_y=0.0,
            interpolation="linear",
        )]

    # Scene cuts = shot boundaries after the first one
    scene_cuts = [s.start_s for s in shots[1:]]

    for kf in keyframes:
        logger.debug(
            "[KeyframeConverter] KF t=%.3fs ox=%.1f oy=%.1f interp=%s",
            kf.time_s, kf.offset_x, kf.offset_y, kf.interpolation,
        )

    logger.info(
        "[KeyframeConverter] %d keyframes, %d scene cuts",
        len(keyframes), len(scene_cuts),
    )

    return ReframeResult(
        keyframes=keyframes,
        scene_cuts=scene_cuts,
        src_w=src_w,
        src_h=src_h,
        fps=fps,
        duration_s=duration_s,
        content_type=anchored_segments[0].reason if anchored_segments else "",
        tracking_mode=config.tracking_mode,
        metadata={
            "crop_w": crop_w,
            "crop_h": crop_h,
            "total_shots": len(shots),
            "total_segments": len(anchored_segments),
            "aspect_ratio": f"{ar_w}:{ar_h}",
        },
    )


# --- Coordinate Conversion ---------------------------------------------------

def _to_offset_x(center_x_norm: float, src_w: int, crop_w: int) -> float:
    """Normalized center X → pixel offset (crop left edge)."""
    return center_x_norm * src_w - crop_w / 2


def _to_offset_y(center_y_norm: float, src_h: int, crop_h: int) -> float:
    """Normalized center Y → pixel offset (crop top edge)."""
    return center_y_norm * src_h - crop_h / 2


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    if hi < lo:
        return lo
    return max(lo, min(hi, value))
