"""
Layer 5 — Strategy: Podcast
Determines which person to follow in each scene and produces ReframeDecisions.

Podcast layout assumption:
  - Speaker 0 (HOST)  → typically left side of frame (cx_norm ≤ 0.5)
  - Speaker 1 (GUEST) → typically right side of frame (cx_norm > 0.5)

Speaker assignment comes from Deepgram diarization.
When speaker info is unavailable, follow the person closest to center.

On speaker change: hard cut (hold keyframe), no smooth transition.
"""
from typing import List, Optional

from app.reframe.models.types import (
    PersonDetection,
    ReframeDecision,
    SceneAnalysis,
    SceneInterval,
)
from app.reframe.composition import compute_crop_x, center_crop_x


def _dominant_speaker(
    speaker_segments: List[dict],
    scene: SceneInterval,
) -> int:
    """
    Returns the speaker index (0 or 1) that speaks the most during [scene.start_s, scene.end_s].
    Returns -1 if no diarization data overlaps this scene.
    """
    if not speaker_segments:
        return -1

    speak_time = {0: 0.0, 1: 0.0}
    for seg in speaker_segments:
        spk = seg.get("speaker", -1)
        if spk not in (0, 1):
            continue
        seg_start = seg.get("start", 0.0)
        seg_end = seg.get("end", 0.0)

        # Overlap with scene
        overlap_start = max(scene.start_s, seg_start)
        overlap_end = min(scene.end_s, seg_end)
        overlap = max(0.0, overlap_end - overlap_start)
        speak_time[spk] += overlap

    if speak_time[0] == 0.0 and speak_time[1] == 0.0:
        return -1

    return 0 if speak_time[0] >= speak_time[1] else 1


def _select_person_for_speaker(
    persons: List[PersonDetection],
    speaker: int,
) -> Optional[PersonDetection]:
    """
    Pick the best PersonDetection to represent speaker 0 (left) or speaker 1 (right).
    Speaker 0 → prefer person with cx_norm ≤ 0.5
    Speaker 1 → prefer person with cx_norm > 0.5
    Falls back to the highest-confidence detection if side preference yields nothing.
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

    # Fallback: highest confidence, closest to center
    return min(persons, key=lambda p: abs(p.cx_norm - 0.5))


def decide(
    scene_analyses: List[SceneAnalysis],
    speaker_segments: List[dict],
    src_w: int,
    src_h: int,
    aspect_ratio: str = "9:16",
) -> List[ReframeDecision]:
    """
    Main podcast strategy entry point.
    Returns one ReframeDecision per scene.
    """
    decisions: List[ReframeDecision] = []
    default_x = center_crop_x(src_w, src_h, aspect_ratio)

    for idx, analysis in enumerate(scene_analyses):
        scene = analysis.scene
        persons = analysis.persons

        dominant = _dominant_speaker(speaker_segments, scene)

        if not persons:
            # No one detected: hold center
            decisions.append(ReframeDecision(
                scene=scene,
                crop_x_norm=default_x / max(src_w - 1, 1),
                target_person_idx=-1,
                reasoning=f"No persons detected in scene {idx}; holding center",
            ))
            continue

        if dominant == -1:
            # No diarization: follow person closest to center
            target = min(persons, key=lambda p: abs(p.cx_norm - 0.5))
            person_idx = persons.index(target)
            reasoning = f"No diarization; following center-closest person (cx={target.cx_norm:.2f})"
        else:
            target = _select_person_for_speaker(persons, dominant)
            if target is None:
                target = persons[0]
            person_idx = persons.index(target)
            side = "left" if dominant == 0 else "right"
            reasoning = (
                f"Speaker {dominant} ({side}) dominant; "
                f"person cx={target.cx_norm:.2f} gaze={target.gaze_direction}"
            )

        crop_x_px = compute_crop_x(target, src_w, src_h, aspect_ratio)
        crop_x_norm = crop_x_px / max(src_w - 1, 1)

        decisions.append(ReframeDecision(
            scene=scene,
            crop_x_norm=crop_x_norm,
            target_person_idx=person_idx,
            reasoning=reasoning,
        ))

    return decisions
