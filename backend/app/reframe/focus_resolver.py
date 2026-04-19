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
import statistics
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
    3. Resolve the target position using PER-SHOT subject positions
       (not Gemini's global left/right which breaks on camera angle changes)
    """
    # Gemini's global position assignment — used as a fallback and identity anchor
    global_subject_positions: dict[str, str] = {s.id: s.position for s in plan.subjects}

    # Per-shot position remapping: at each shot boundary, look at the actual face
    # X positions detected in that shot and re-derive which subject is left/right.
    # This handles reverse angles (camera flip) where global left/right is wrong.
    per_shot_positions: dict[int, dict[str, str]] = _compute_per_shot_positions(
        plan, frames, shots, global_subject_positions,
    )

    importance_weights = {"high": 1.0, "medium": 0.7, "low": 0.4}

    focus_points: list[FocusPoint] = []

    # Look-back: last known face position per shot index
    # When faces temporarily disappear (profile angle), hold the last known position
    last_known_x: dict[int, float] = {}
    last_known_y: dict[int, float] = {}

    # Per-directive track_id lock: key = (shot_idx, directive_start_s) → track_id
    # At the start of each directive, pick the track_id closest to the target position
    # and hold it for the entire directive. Prevents frame-by-frame YOLO jitter when
    # multiple faces are on screen (e.g. 5-person wide shot).
    directive_track_lock: dict[tuple, int] = {}

    for frame in frames:
        shot = _get_shot_at(frame.time_s, shots)
        if shot is None:
            continue

        shot_idx = shots.index(shot) if shot in shots else frame.shot_index
        shot_type = shot.shot_type

        # Use per-shot position mapping so camera angle changes don't corrupt tracking
        subject_positions = per_shot_positions.get(shot_idx, global_subject_positions)

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
                weight=0.3, shot_index=shot_idx, subject_id="",
            ))

        elif not frame.faces:
            # No faces detected (profile angle, occlusion, etc.)
            # Priority 1: last known position from this shot (look-back)
            # Priority 2: per-shot Gemini position hint
            active_subject_id = directive.subject_id if directive else ""
            if shot_idx in last_known_x:
                x = last_known_x[shot_idx]
                y = last_known_y[shot_idx]
                logger.debug(
                    "[FocusResolver] t=%.2fs: no faces, holding last known (%.2f, %.2f)",
                    frame.time_s, x, y,
                )
            else:
                target_pos = subject_positions.get(active_subject_id, "")
                x = _position_to_x(target_pos)
                y = 0.35
                logger.debug(
                    "[FocusResolver] t=%.2fs: no faces, no history, hint '%s' → x=%.2f",
                    frame.time_s, target_pos, x,
                )
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=x, y=y,
                weight=0.4, shot_index=shot_idx, subject_id=active_subject_id,
            ))

        elif shot_type == SHOT_CLOSEUP:
            active_subject_id = directive.subject_id if directive else ""
            if len(frame.faces) == 1:
                # True closeup: one face in frame, just use it
                face = frame.faces[0]
            else:
                # Multiple faces in a "closeup" — most likely a misclassified two-shot.
                # Apply per-shot subject directive so the right person is chosen.
                target_pos = subject_positions.get(active_subject_id, "")
                face = _pick_face_by_position(frame.faces, target_pos)
                logger.debug(
                    "[FocusResolver] t=%.2fs: CLOSEUP with %d faces — target '%s' → x=%.2f",
                    frame.time_s, len(frame.faces), target_pos, face.face_x,
                )
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
            # Wide shot: use per-shot subject positions to select the right face
            active_subject_id = directive.subject_id if directive else ""
            target_pos = subject_positions.get(active_subject_id, "")

            # Per-directive track_id lock: at the first frame of each directive,
            # pick the track_id closest to target_pos and hold it for the full directive.
            # This prevents YOLO from oscillating between multiple faces each frame.
            directive_start_s = directive.start_s if directive else 0.0
            lock_key = (shot_idx, directive_start_s)
            locked_track_id = directive_track_lock.get(lock_key)

            if locked_track_id is None and frame.faces:
                # First frame of this directive in this shot — pick and lock a track_id
                best = _pick_face_by_position(frame.faces, target_pos)
                locked_track_id = best.track_id if best.track_id != -1 else None
                if locked_track_id is not None:
                    directive_track_lock[lock_key] = locked_track_id
                    logger.debug(
                        "[FocusResolver] t=%.2fs: locked track_id=%d for directive %s (subject=%s, pos=%s)",
                        frame.time_s, locked_track_id, lock_key, active_subject_id, target_pos,
                    )

            # Use locked track_id if available, otherwise fall back to position-based pick
            if locked_track_id is not None:
                locked_faces = [f for f in frame.faces if f.track_id == locked_track_id]
                face = locked_faces[0] if locked_faces else _pick_face_by_position(frame.faces, target_pos)
            else:
                face = _pick_face_by_position(frame.faces, target_pos)

            # If only 1 face found and it's clearly on the wrong side,
            # don't lock onto the wrong person — hold last known position instead.
            if (len(frame.faces) == 1
                    and shot_idx in last_known_x
                    and not _face_matches_position(face, target_pos)):
                x = last_known_x[shot_idx]
                y = last_known_y[shot_idx]
                logger.debug(
                    "[FocusResolver] t=%.2fs: single face on wrong side (x=%.2f, target=%s), holding",
                    frame.time_s, face.face_x, target_pos,
                )
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


# --- Per-shot position remapping ---------------------------------------------

def _compute_per_shot_positions(
    plan: DirectorPlan,
    frames: list[Frame],
    shots: list[Shot],
    global_positions: dict[str, str],
) -> dict[int, dict[str, str]]:
    """
    For each shot, derive a subject_id → position mapping from the actual
    face X coordinates detected in that shot's frames.

    Gemini's global left/right assignments are correct for the first wide shot
    but break when the camera switches to a reverse angle (left/right flips).

    Algorithm for shots with 2+ face clusters:
      1. Group face detections by track_id (stable within a shot).
      2. Compute median X per track_id cluster.
      3. Match each cluster to a Gemini subject by finding the cluster whose
         median X is closest to that subject's globally-expected X.
      4. If the mapping differs from Gemini's global assignment, log the flip.

    For shots with <2 clusters (closeups, b-roll), global positions are kept.
    """
    result: dict[int, dict[str, str]] = {}

    # Subjects with explicit left/right placement — these are the ones to remap
    positioned = sorted(
        [s for s in plan.subjects if s.position in ("left", "right")],
        key=lambda s: 0 if s.position == "left" else 1,
    )

    if len(positioned) < 2:
        # 0 or 1 positioned subjects → per-shot remapping not applicable
        for shot_idx in range(len(shots)):
            result[shot_idx] = dict(global_positions)
        logger.debug("[FocusResolver] Per-shot remapping skipped: <2 positioned subjects")
        return result

    for shot_idx, shot in enumerate(shots):
        # Collect frames with 2+ face detections in this shot
        wide_frames = [
            f for f in frames
            if f.shot_index == shot_idx and len(f.faces) >= 2
        ]

        if not wide_frames:
            result[shot_idx] = dict(global_positions)
            continue

        # Group face detections by track_id to form stable intra-shot clusters.
        # track_id is reset at shot boundaries, so each shot starts fresh.
        clusters: dict[int, list[float]] = {}  # track_id → [face_x, ...]
        for frame in wide_frames:
            for face in frame.faces:
                tid = face.track_id if face.track_id is not None else -1
                clusters.setdefault(tid, []).append(face.face_x)

        if len(clusters) < 2:
            result[shot_idx] = dict(global_positions)
            continue

        # Compute median X for each cluster; keep the two most populated clusters
        cluster_medians = {
            tid: statistics.median(xs)
            for tid, xs in clusters.items()
        }
        top_two = sorted(
            cluster_medians.items(),
            key=lambda item: -len(clusters[item[0]]),
        )[:2]
        # Sort the two clusters left→right
        top_two.sort(key=lambda item: item[1])  # ascending median X
        left_cluster_x = top_two[0][1]
        right_cluster_x = top_two[1][1]

        # Match each positioned subject to a cluster using expected X as the anchor.
        # The subject whose global expected X is closest to the left cluster median
        # is the one physically on the left in this shot — even if the camera flipped.
        shot_positions = dict(global_positions)
        assigned: list[tuple[str, str]] = []  # [(subject_id, new_position)]

        for subj in positioned:
            expected_x = _position_to_x(subj.position)
            dist_to_left = abs(left_cluster_x - expected_x)
            dist_to_right = abs(right_cluster_x - expected_x)
            new_pos = "left" if dist_to_left <= dist_to_right else "right"
            shot_positions[subj.id] = new_pos
            assigned.append((subj.id, new_pos))

        # Detect and log camera flips
        flipped = any(
            shot_positions[s.id] != global_positions.get(s.id)
            for s in positioned
        )
        if flipped:
            logger.info(
                "[FocusResolver] Shot %d (%.1f-%.1fs): CAMERA FLIP detected — "
                "remapped %s. left_cluster_x=%.2f, right_cluster_x=%.2f",
                shot_idx, shot.start_s, shot.end_s,
                ", ".join(f"{sid}={pos}" for sid, pos in assigned),
                left_cluster_x, right_cluster_x,
            )
        else:
            logger.debug(
                "[FocusResolver] Shot %d: normal layout confirmed "
                "(left_x=%.2f, right_x=%.2f)",
                shot_idx, left_cluster_x, right_cluster_x,
            )

        result[shot_idx] = shot_positions

    return result


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


def _face_matches_position(face: FaceDetection, target_position: str) -> bool:
    """True if the face is roughly on the expected side."""
    if target_position == "left":
        return face.face_x < 0.5
    elif target_position == "right":
        return face.face_x > 0.5
    return True  # center or unknown — accept any face


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
