"""
Focus Resolver — merges Gemini's creative plan with face detections.

Takes:
  - DirectorPlan (who to focus on, when, and why)
  - Frame list (face detections per frame)
  - Shot list (camera angle boundaries)

Produces:
  - FocusPoint list (per-frame weighted targets for the path solver)

Key principle: Gemini says WHO (by track_id number), detections say WHERE.
  - Wide shots: look up subject's track_id for this shot → find matching face
  - Closeup shots: use the single visible face directly
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
    Merge Gemini directives with face detections into focus points.

    For each analyzed frame:
    1. Find which Gemini directive covers this timestamp
    2. Find which shot this frame belongs to
    3. Look up the track_id Gemini assigned to this subject in this shot
    4. Find the face with that track_id; fallback to largest face
    """
    # Build: subject_id → shot_idx(int) → track_id(int)
    subject_track_map: dict[str, dict[int, int]] = {}
    for s in plan.subjects:
        subject_track_map[s.id] = {int(k): int(v) for k, v in s.scene_track_ids.items()}

    importance_weights = {"high": 1.0, "medium": 0.7, "low": 0.4}

    focus_points: list[FocusPoint] = []

    # Last known face position per shot index — held when faces disappear temporarily
    last_known_x: dict[int, float] = {}
    last_known_y: dict[int, float] = {}

    # Pre-compute per-shot face position medians as fallback for first-frame misses
    shot_median_x: dict[int, float] = {}
    shot_median_y: dict[int, float] = {}
    import statistics as _stats
    for shot_idx_pre in set(f.shot_index for f in frames):
        xs = [face.face_x for f in frames if f.shot_index == shot_idx_pre for face in f.faces]
        ys = [face.face_y for f in frames if f.shot_index == shot_idx_pre for face in f.faces]
        if xs:
            shot_median_x[shot_idx_pre] = _stats.median(xs)
            shot_median_y[shot_idx_pre] = _stats.median(ys)

    for frame in frames:
        shot = _get_shot_at(frame.time_s, shots)
        if shot is None:
            continue

        shot_idx = shots.index(shot) if shot in shots else frame.shot_index
        shot_type = shot.shot_type

        directive = _get_directive_at(frame.time_s, plan.directives)
        weight = importance_weights.get(
            directive.importance if directive else "medium", 0.7,
        )
        active_subject_id = directive.subject_id if directive else ""

        if shot_type == SHOT_BROLL:
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=0.5, y=0.4,
                weight=0.3, shot_index=shot_idx, subject_id="",
            ))

        elif not frame.faces:
            # No faces — hold last known position for this shot
            if shot_idx in last_known_x:
                x = last_known_x[shot_idx]
                y = last_known_y[shot_idx]
            else:
                x = shot_median_x.get(shot_idx, 0.5)
                y = shot_median_y.get(shot_idx, 0.35)
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=x, y=y,
                weight=0.4, shot_index=shot_idx, subject_id=active_subject_id,
            ))

        elif shot_type == SHOT_CLOSEUP and len(frame.faces) == 1:
            face = frame.faces[0]
            last_known_x[shot_idx] = face.face_x
            last_known_y[shot_idx] = face.face_y
            focus_points.append(FocusPoint(
                time_s=frame.time_s,
                x=face.face_x,
                y=face.face_y,
                weight=weight,
                shot_index=shot_idx,
                subject_id=active_subject_id,
            ))

        else:
            # Wide shot or closeup with multiple faces:
            # look up the track_id Gemini assigned to this subject in this shot
            face = _pick_face_by_track_id(
                frame.faces,
                subject_track_map.get(active_subject_id, {}),
                shot_idx,
            )
            if face is None:
                # Track ID lost for this frame — hold last known position
                # instead of jumping to wrong person
                if shot_idx in last_known_x:
                    x = last_known_x[shot_idx]
                    y = last_known_y[shot_idx]
                else:
                    x = shot_median_x.get(shot_idx, 0.5)
                    y = shot_median_y.get(shot_idx, 0.35)
                focus_points.append(FocusPoint(
                    time_s=frame.time_s, x=x, y=y,
                    weight=0.4, shot_index=shot_idx, subject_id=active_subject_id,
                ))
            else:
                last_known_x[shot_idx] = face.face_x
                last_known_y[shot_idx] = face.face_y
                focus_points.append(FocusPoint(
                    time_s=frame.time_s,
                    x=face.face_x,
                    y=face.face_y,
                    weight=weight,
                    shot_index=shot_idx,
                    subject_id=active_subject_id,
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


def _pick_face_by_track_id(
    faces: list[FaceDetection],
    shot_track_map: dict[int, int],
    shot_idx: int,
) -> Optional[FaceDetection]:
    """
    Find the face matching the track_id Gemini assigned to this subject
    in this shot. Returns None if not found — caller holds last known position.
    """
    target_track_id = shot_track_map.get(shot_idx)

    if target_track_id is not None:
        matches = [f for f in faces if f.track_id == target_track_id]
        if matches:
            return matches[0]
        logger.debug(
            "[FocusResolver] track_id=%d not found in shot %d (have: %s), holding last position",
            target_track_id, shot_idx,
            [f.track_id for f in faces],
        )
        return None

    # No track_id mapping for this shot — largest face
    return max(faces, key=lambda f: f.face_width * f.face_height)
