"""
Layer 3+4 — Crop Calculator
Converts ReframeDecisions (one per scene) into a flat keyframe list.

Key design rules:
  - All times are float seconds (never frame numbers)
  - Scene boundary → hold + linear keyframe pair (hard cut, no smooth pan)
  - Speaker switch → same hard cut treatment (detected via adjacent scene decisions)
  - Within a scene → single position held constant (YOLOv8 per-scene sampling = no jitter)
  - Minimum keyframe delta: 20px (avoid micro-jitter from rounding)
"""
from typing import List, Tuple

from app.reframe.models.types import ReframeDecision, ReframeResult, SceneInterval
from app.reframe.composition import compute_crop_width, center_crop_x


# Minimum pixel movement between keyframes to emit a new one
MIN_DELTA_PX = 20


def decisions_to_keyframes(
    decisions: List[ReframeDecision],
    src_w: int,
    src_h: int,
    aspect_ratio: str = "9:16",
) -> Tuple[List[dict], List[float]]:
    """
    Convert scene-level crop decisions to a timeline keyframe list.

    Returns:
        keyframes: [{time_s: float, offset_x: float, interpolation: "hold"|"linear"}]
        scene_cuts: [float, ...]   timestamps of scene boundaries (for timeline markers)

    Keyframe interpolation semantics (used by the editor):
        "hold"   = stay at this offset until the next keyframe
        "linear" = smoothly interpolate to the next keyframe value

    At each scene boundary we emit:
        1. "hold" keyframe at (scene_end - ε)  with the CURRENT position
        2. "linear" keyframe at scene_start_of_next  with the NEW position
    This produces an instantaneous cut with no smooth pan between scenes.
    """
    if not decisions:
        return [], []

    keyframes: List[dict] = []
    scene_cuts: List[float] = []
    crop_w = compute_crop_width(src_w, src_h, aspect_ratio)

    def px_from_norm(crop_x_norm: float) -> float:
        return round(float(crop_x_norm * max(src_w - 1, 1)), 2)

    # Emit first keyframe at t=0
    first_px = px_from_norm(decisions[0].crop_x_norm)
    keyframes.append({
        "time_s": decisions[0].scene.start_s,
        "offset_x": first_px,
        "interpolation": "linear",
    })
    last_px = first_px

    for i, decision in enumerate(decisions):
        current_px = px_from_norm(decision.crop_x_norm)

        if i == 0:
            # First scene already emitted above
            last_px = current_px
            continue

        scene_start = decision.scene.start_s

        # Record this cut point for timeline markers
        scene_cuts.append(scene_start)

        # Only emit new keyframes if the position changed meaningfully
        if abs(current_px - last_px) < MIN_DELTA_PX:
            # Position barely changed — extend hold, no new keyframe needed
            last_px = current_px
            continue

        # Hard cut: hold at old position until just before this scene starts,
        # then jump to new position at the scene start.
        hold_time = round(scene_start - 0.001, 4)  # 1ms before cut
        if hold_time > (keyframes[-1]["time_s"] if keyframes else 0):
            keyframes.append({
                "time_s": hold_time,
                "offset_x": last_px,
                "interpolation": "hold",
            })

        keyframes.append({
            "time_s": scene_start,
            "offset_x": current_px,
            "interpolation": "linear",
        })
        last_px = current_px

    # Always include final scene end with a hold to lock position
    last_scene = decisions[-1].scene
    if keyframes and keyframes[-1]["time_s"] < last_scene.end_s - 0.1:
        keyframes.append({
            "time_s": round(last_scene.end_s, 4),
            "offset_x": last_px,
            "interpolation": "hold",
        })

    print(
        f"[CropCalculator] {len(decisions)} scenes → {len(keyframes)} keyframes, "
        f"{len(scene_cuts)} cut markers"
    )
    return keyframes, scene_cuts
