"""
Layer 3+4 — Crop Calculator
Converts ReframeDecisions (one per scene) into a flat keyframe list.

Key design rules:
  - All times are float seconds (never frame numbers)
  - Scene boundary → hold + linear keyframe pair (hard cut, no smooth pan)
  - Speaker switch (intra-scene) → same hard cut treatment via diarization data
  - Within a scene with no speaker change → single position held constant
  - Minimum keyframe delta: 20px (avoid micro-jitter from rounding)
"""
from typing import List, Optional, Tuple

from app.reframe.models.types import ReframeDecision, ReframeResult, SceneAnalysis, SceneInterval
from app.reframe.composition import compute_crop_width, center_crop_x, compute_crop_x


# Minimum pixel movement between keyframes to emit a new one
MIN_DELTA_PX = 20


def _dominant_speaker_in_range(
    speaker_segments: List[dict],
    start_s: float,
    end_s: float,
) -> int:
    """Returns the dominant speaker (0 or 1) in [start_s, end_s], or -1 if none."""
    speak_time = {0: 0.0, 1: 0.0}
    for seg in speaker_segments:
        spk = seg.get("speaker", -1)
        if spk not in (0, 1):
            continue
        overlap_start = max(start_s, seg.get("start", 0.0))
        overlap_end = min(end_s, seg.get("end", 0.0))
        overlap = max(0.0, overlap_end - overlap_start)
        speak_time[spk] += overlap
    if speak_time[0] == 0.0 and speak_time[1] == 0.0:
        return -1
    return 0 if speak_time[0] >= speak_time[1] else 1


def _select_person_for_speaker(persons, speaker: int):
    """
    Pick the best PersonDetection for speaker 0 (left side) or 1 (right side).
    Falls back to closest-to-center if no side preference matches.
    """
    if not persons:
        return None
    if speaker == 0:
        preferred = [p for p in persons if p.cx_norm <= 0.55]
    elif speaker == 1:
        preferred = [p for p in persons if p.cx_norm > 0.45]
    else:
        preferred = []
    if preferred:
        return max(preferred, key=lambda p: p.confidence)
    return min(persons, key=lambda p: abs(p.cx_norm - 0.5))


def _handle_intra_scene(
    scene_idx: int,
    scene: SceneInterval,
    scene_analyses: List[SceneAnalysis],
    speaker_segments: List[dict],
    src_w: int,
    src_h: int,
    aspect_ratio: str,
    current_px: float,
    keyframes: List[dict],
) -> float:
    """
    Detect speaker changes WITHIN a scene and emit hard-cut keyframes at each switch.
    Uses the same person detections from the scene's first frame (positions are stable
    in podcast footage). Returns updated last_px.
    """
    if scene_idx >= len(scene_analyses):
        return current_px

    persons = scene_analyses[scene_idx].persons
    if not persons:
        return current_px

    # Speaker active at scene start (already applied via current_px)
    last_speaker = _dominant_speaker_in_range(
        speaker_segments, scene.start_s, min(scene.end_s, scene.start_s + 2.0)
    )

    # Speaker segments that start STRICTLY within this scene (after scene start, before end)
    intra_segs = sorted(
        [
            s for s in speaker_segments
            if s.get("start", 0) > scene.start_s + 0.1
            and s.get("start", 0) < scene.end_s - 0.1
        ],
        key=lambda s: s["start"],
    )

    last_px = current_px

    for seg in intra_segs:
        spk = seg.get("speaker", -1)
        if spk not in (0, 1) or spk == last_speaker:
            last_speaker = spk
            continue

        change_t = round(seg["start"], 4)
        target = _select_person_for_speaker(persons, spk)
        if target is None:
            last_speaker = spk
            continue

        new_px = float(compute_crop_x(target, src_w, src_h, aspect_ratio))
        if abs(new_px - last_px) < MIN_DELTA_PX:
            last_speaker = spk
            continue

        # Hard cut at speaker change
        hold_t = round(change_t - 0.001, 4)
        if keyframes and hold_t <= keyframes[-1]["time_s"]:
            hold_t = round(keyframes[-1]["time_s"] + 0.001, 4)

        keyframes.append({"time_s": hold_t, "offset_x": last_px, "interpolation": "hold"})
        keyframes.append({"time_s": change_t, "offset_x": new_px, "interpolation": "linear"})
        last_px = new_px
        last_speaker = spk
        print(
            f"[CropCalculator] Intra-scene speaker switch at {change_t:.2f}s "
            f"→ speaker {spk}, x={new_px:.0f}px"
        )

    return last_px


def decisions_to_keyframes(
    decisions: List[ReframeDecision],
    src_w: int,
    src_h: int,
    aspect_ratio: str = "9:16",
    scene_analyses: Optional[List[SceneAnalysis]] = None,
    speaker_segments: Optional[List[dict]] = None,
) -> Tuple[List[dict], List[float]]:
    """
    Convert scene-level crop decisions to a timeline keyframe list.

    When scene_analyses and speaker_segments are provided, also emits
    hard-cut keyframes at intra-scene speaker changes (speaker switching
    within a camera shot without a visual cut).

    Returns:
        keyframes: [{time_s: float, offset_x: float, interpolation: "hold"|"linear"}]
        scene_cuts: [float, ...]   timestamps of scene boundaries (for timeline markers)

    Keyframe interpolation semantics:
        "hold"   = stay at this offset until the next keyframe (OUTGOING)
        "linear" = smoothly interpolate to the next keyframe value (OUTGOING)

    At each scene boundary we emit:
        1. "hold" keyframe at (scene_end - ε)  with the CURRENT position
        2. "linear" keyframe at scene_start_of_next  with the NEW position
    This produces an instantaneous cut with no smooth pan.
    """
    if not decisions:
        return [], []

    use_diarization = bool(scene_analyses and speaker_segments)

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
        scene = decision.scene

        if i == 0:
            last_px = current_px
            # Intra-scene speaker switching for the first scene
            if use_diarization:
                last_px = _handle_intra_scene(
                    i, scene, scene_analyses, speaker_segments,
                    src_w, src_h, aspect_ratio, last_px, keyframes,
                )
            continue

        scene_start = scene.start_s
        scene_cuts.append(scene_start)

        # Scene boundary hard cut (only if position changed meaningfully)
        if abs(current_px - last_px) >= MIN_DELTA_PX:
            hold_time = round(scene_start - 0.001, 4)
            last_kf_time = keyframes[-1]["time_s"] if keyframes else 0
            if hold_time > last_kf_time:
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

        # Intra-scene speaker switching
        if use_diarization:
            last_px = _handle_intra_scene(
                i, scene, scene_analyses, speaker_segments,
                src_w, src_h, aspect_ratio, last_px, keyframes,
            )

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
        + (f" (diarization enabled)" if use_diarization else "")
    )
    return keyframes, scene_cuts
