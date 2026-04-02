"""
Keyframe Emitter — converts smooth paths to pixel-offset keyframes.

Pure math: takes ShotPath objects (normalized positions) and converts
to ReframeKeyframes (pixel offsets) for the frontend editor.

Shot transitions are always hard cuts (hold + jump).
Within-shot movement comes from the path solver (already smooth).
"""
import logging

from .config import KeyframeEmitterConfig, ReframeConfig
from .types import ReframeKeyframe, ReframeResult, Shot, ShotPath

logger = logging.getLogger(__name__)


def emit_keyframes(
    shot_paths: list[ShotPath],
    shots: list[Shot],
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    config: ReframeConfig,
) -> ReframeResult:
    """Convert smooth paths into pixel-offset keyframes for the frontend."""
    kf_config = config.keyframe_emitter
    ar_w, ar_h = config.aspect_ratio

    # Compute crop dimensions
    if config.tracking_mode == "dynamic_xy" and kf_config.y_headroom_zoom > 1.0:
        crop_h = int(src_h / kf_config.y_headroom_zoom)
        crop_w = min(int(crop_h * (ar_w / ar_h)), src_w)
    else:
        crop_w = min(int(src_h * (ar_w / ar_h)), src_w)
        crop_h = src_h

    frame_dur = 1.0 / fps if fps > 0 else 1.0 / 30.0

    def _snap(t: float) -> float:
        """Quantize timestamp to the nearest video frame boundary."""
        return round(round(t * fps) / fps, 6)

    # Safety margin
    EDGE_MARGIN = 10.0
    ox_min = EDGE_MARGIN
    ox_max = max(EDGE_MARGIN, src_w - crop_w - EDGE_MARGIN)
    oy_min = EDGE_MARGIN if config.tracking_mode == "dynamic_xy" else 0.0
    oy_max = max(0.0, src_h - crop_h - EDGE_MARGIN) if config.tracking_mode == "dynamic_xy" else 0.0

    logger.info(
        "[KeyframeEmitter] crop=%dx%d, src=%dx%d, mode=%s, ox=[%.0f,%.0f], oy=[%.0f,%.0f]",
        crop_w, crop_h, src_w, src_h, config.tracking_mode,
        ox_min, ox_max, oy_min, oy_max,
    )

    keyframes: list[ReframeKeyframe] = []
    last_ox = -999.0
    last_oy = -999.0

    # Pixel distance threshold for intra-shot subject switch detection.
    # A jump larger than this means the focus resolver changed persons (not just head movement).
    # Matches PathSolverConfig.subject_switch_threshold in normalized space.
    subject_switch_px = kf_config.subject_switch_threshold * src_w

    for path_idx, path in enumerate(shot_paths):
        if not path.points:
            continue

        for pt_idx, pt in enumerate(path.points):
            ox = _to_offset_x(pt.x, src_w, crop_w)
            oy = _to_offset_y(pt.y, src_h, crop_h) if config.tracking_mode == "dynamic_xy" else 0.0
            ox = _clamp(round(ox, 1), ox_min, ox_max)
            oy = _clamp(round(oy, 1), oy_min, oy_max)

            is_first_point = (pt_idx == 0)
            is_first_path = (path_idx == 0)
            is_shot_boundary = is_first_point and not is_first_path and last_ox != -999.0
            # Intra-shot subject switch: large X jump within the same ShotPath means
            # the focus person changed (path_solver already teleported the path point).
            # We emit a hold+hold pair identical to shot boundaries so the frontend
            # hard-cuts instead of linearly interpolating across the person change.
            is_subject_switch = (
                not is_first_point
                and last_ox != -999.0
                and abs(ox - last_ox) > subject_switch_px
            )

            if is_shot_boundary:
                # Shot boundary: use the actual scene cut time from the shot detector,
                # NOT the first path point's sample time. The path point can be up to
                # 200ms after the real scene cut (due to 5 FPS sampling), causing frames
                # between the cut and the keyframe to show the new shot at the old position.
                cut_time = _snap(shots[path.shot_index].start_s) if path.shot_index < len(shots) else _snap(pt.time_s)
                hold_time = max(
                    keyframes[-1].time_s + frame_dur if keyframes else 0.0,
                    cut_time - frame_dur,
                )
                hold_time = _snap(hold_time)
                keyframes.append(ReframeKeyframe(
                    time_s=round(hold_time, 6),
                    offset_x=last_ox,
                    offset_y=last_oy,
                    interpolation="hold",
                ))
                keyframes.append(ReframeKeyframe(
                    time_s=round(cut_time, 6),
                    offset_x=ox,
                    offset_y=oy,
                    interpolation="hold",
                ))

            elif is_subject_switch:
                # Intra-shot subject switch: same hold+hold pattern as a shot boundary.
                # Prevents the frontend from smoothly panning between the two people.
                switch_time = _snap(pt.time_s)
                hold_time = max(
                    keyframes[-1].time_s + frame_dur if keyframes else 0.0,
                    switch_time - frame_dur,
                )
                hold_time = _snap(hold_time)
                keyframes.append(ReframeKeyframe(
                    time_s=round(hold_time, 6),
                    offset_x=last_ox,
                    offset_y=last_oy,
                    interpolation="hold",
                ))
                keyframes.append(ReframeKeyframe(
                    time_s=round(switch_time, 6),
                    offset_x=ox,
                    offset_y=oy,
                    interpolation="hold",
                ))
                logger.info(
                    "[KeyframeEmitter] t=%.3fs: subject switch hard-cut (ox %.1f → %.1f, Δ=%.1fpx > %.0fpx threshold)",
                    pt.time_s, last_ox, ox, abs(ox - last_ox), subject_switch_px,
                )

            else:
                # Normal within-shot movement: dedup tiny changes, then linear keyframe
                if (not is_first_point
                        and abs(ox - last_ox) < kf_config.dedup_threshold_px
                        and abs(oy - last_oy) < kf_config.dedup_threshold_px):
                    continue

                keyframes.append(ReframeKeyframe(
                    time_s=round(_snap(pt.time_s), 6),
                    offset_x=ox,
                    offset_y=oy,
                    interpolation="linear",
                ))

            last_ox = ox
            last_oy = oy

    # Pin last position to video end
    if keyframes and keyframes[-1].time_s < duration_s - frame_dur:
        keyframes.append(ReframeKeyframe(
            time_s=round(_snap(duration_s), 6),
            offset_x=keyframes[-1].offset_x,
            offset_y=keyframes[-1].offset_y,
            interpolation="linear",
        ))

    # Fallback: center crop
    if not keyframes:
        center_ox = _clamp(_to_offset_x(0.5, src_w, crop_w), ox_min, ox_max)
        keyframes = [ReframeKeyframe(
            time_s=0.0, offset_x=round(center_ox, 1), offset_y=0.0,
            interpolation="linear",
        )]

    scene_cuts = [s.start_s for s in shots[1:]]

    for kf in keyframes:
        logger.info(
            "[KeyframeEmitter] t=%.3fs ox=%.1f oy=%.1f %s",
            kf.time_s, kf.offset_x, kf.offset_y, kf.interpolation,
        )

    logger.info("[KeyframeEmitter] %d keyframes, %d scene cuts", len(keyframes), len(scene_cuts))

    return ReframeResult(
        keyframes=keyframes,
        scene_cuts=scene_cuts,
        src_w=src_w,
        src_h=src_h,
        fps=fps,
        duration_s=duration_s,
        tracking_mode=config.tracking_mode,
        metadata={
            "crop_w": crop_w,
            "crop_h": crop_h,
            "total_shots": len(shots),
            "total_paths": len(shot_paths),
            "strategies": [p.strategy for p in shot_paths],
            "aspect_ratio": f"{ar_w}:{ar_h}",
        },
    )


# --- Coordinate conversion ---------------------------------------------------

def _to_offset_x(center_x_norm: float, src_w: int, crop_w: int) -> float:
    return center_x_norm * src_w - crop_w / 2

def _to_offset_y(center_y_norm: float, src_h: int, crop_h: int) -> float:
    return center_y_norm * src_h - crop_h / 2

def _clamp(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        return lo
    return max(lo, min(hi, value))
