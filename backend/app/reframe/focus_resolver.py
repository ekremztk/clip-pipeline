"""
Focus Resolver — merges Gemini's creative plan with MediaPipe detections.

Takes:
  - DirectorPlan (who to focus on, when, and why)
  - Frame list (MediaPipe face detections per frame)
  - Shot list (camera angle boundaries)

Produces:
  - FocusPoint list (per-frame weighted targets for the path solver)

Key principle: Gemini says WHO, MediaPipe says WHERE.
  - Wide shots: Gemini picks the subject, MediaPipe provides the position
  - Closeup shots: ignore Gemini target, center on whoever is visible
  - B-roll: center crop
"""
import logging
from typing import Optional

from .types import (
    DirectorPlan,
    FaceDetection,
    FocusDirective,
    FocusPoint,
    Frame,
    Shot,
    SubjectInfo,
    SHOT_CLOSEUP,
    SHOT_BROLL,
)

logger = logging.getLogger(__name__)


def resolve_focus(
    plan: DirectorPlan,
    frames: list[Frame],
    shots: list[Shot],
) -> list[FocusPoint]:
    """
    Merge Gemini directives with MediaPipe detections into focus points.

    For each analyzed frame:
    1. Find which Gemini directive covers this timestamp
    2. Find which shot this frame belongs to
    3. Based on shot type, resolve the target position
    """
    # Build subject position map: subject_id → typical visual position ("left", "right", etc.)
    subject_positions: dict[str, str] = {}
    for subj in plan.subjects:
        subject_positions[subj.id] = subj.position

    # Importance → weight mapping
    importance_weights = {"high": 1.0, "medium": 0.7, "low": 0.4}

    focus_points: list[FocusPoint] = []

    for frame in frames:
        shot = _get_shot_at(frame.time_s, shots)
        if shot is None:
            continue

        shot_idx = shots.index(shot) if shot in shots else frame.shot_index
        shot_type = shot.shot_type

        # Find the active Gemini directive for this timestamp
        directive = _get_directive_at(frame.time_s, plan.directives)
        weight = importance_weights.get(
            directive.importance if directive else "medium", 0.7,
        )

        # Resolve position based on shot type
        if shot_type == SHOT_BROLL:
            # B-roll: center crop — no subject to track
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=0.5, y=0.4,
                weight=0.3, shot_index=shot_idx,
            ))

        elif not frame.faces:
            # No faces detected (profile angle, occlusion, etc.)
            # Use Gemini's subject position hint instead of blindly centering
            target_pos = subject_positions.get(
                directive.subject_id if directive else "", "",
            )
            x = _position_to_x(target_pos)
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=x, y=0.35,
                weight=0.4, shot_index=shot_idx,
            ))
            logger.debug(
                "[FocusResolver] t=%.2fs: no faces, using Gemini hint '%s' → x=%.2f",
                frame.time_s, target_pos, x,
            )

        elif shot_type == SHOT_CLOSEUP:
            # Closeup: center on the largest/most prominent face
            # Ignore Gemini's subject pick — only 1 person visible
            face = max(frame.faces, key=lambda f: f.face_width * f.face_height)
            focus_points.append(FocusPoint(
                time_s=frame.time_s,
                x=face.face_x,
                y=face.face_y,
                weight=weight,
                shot_index=shot_idx,
            ))

        else:
            # Wide shot: use Gemini's subject pick to select the right face
            target_pos = subject_positions.get(
                directive.subject_id if directive else "", "",
            )
            face = _pick_face_by_position(frame.faces, target_pos)
            focus_points.append(FocusPoint(
                time_s=frame.time_s,
                x=face.face_x,
                y=face.face_y,
                weight=weight,
                shot_index=shot_idx,
            ))

    logger.info(
        "[FocusResolver] %d focus points from %d frames (%d directives)",
        len(focus_points), len(frames), len(plan.directives),
    )
    return focus_points


# --- Helpers -----------------------------------------------------------------

def _get_shot_at(time_s: float, shots: list[Shot]) -> Optional[Shot]:
    """Find the shot containing this timestamp."""
    for shot in shots:
        if shot.start_s <= time_s < shot.end_s:
            return shot
    # Edge case: last frame at exact end time
    if shots and time_s >= shots[-1].start_s:
        return shots[-1]
    return None


def _get_directive_at(
    time_s: float,
    directives: list[FocusDirective],
) -> Optional[FocusDirective]:
    """Find the active Gemini directive at this timestamp."""
    for d in directives:
        if d.start_s <= time_s < d.end_s:
            return d
    return None


def _position_to_x(position: str) -> float:
    """Convert Gemini subject position hint to normalized X coordinate."""
    if position == "left":
        return 0.25
    elif position == "right":
        return 0.75
    elif position == "center":
        return 0.5
    return 0.5


def _pick_face_by_position(
    faces: list[FaceDetection],
    target_position: str,
) -> FaceDetection:
    """
    Pick the face matching the target position.

    "left" → leftmost face, "right" → rightmost face,
    "center" → closest to center, else → largest face.

    If only 1 face detected, always return it regardless of target.
    """
    if len(faces) == 1:
        return faces[0]

    sorted_by_x = sorted(faces, key=lambda f: f.face_x)

    if target_position == "left":
        return sorted_by_x[0]
    elif target_position == "right":
        return sorted_by_x[-1]
    elif target_position == "center":
        return min(faces, key=lambda f: abs(f.face_x - 0.5))
    else:
        # Unknown position — return largest face
        return max(faces, key=lambda f: f.face_width * f.face_height)
