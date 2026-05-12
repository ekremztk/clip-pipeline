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

from .config import FocusResolverConfig
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
    config: Optional[FocusResolverConfig] = None,
) -> list[FocusPoint]:
    """
    Merge Gemini directives with face detections into focus points.

    For each analyzed frame:
    1. Find which Gemini directive covers this timestamp
    2. Find which shot this frame belongs to
    3. Look up the track_id Gemini assigned to this subject in this shot
    4. Find the face with that track_id; fallback to largest face
    5. Validate position consistency — reject track_id swaps
    """
    resolver_config = config or FocusResolverConfig()

    # Build: subject_id -> shot_idx(int) -> track_id(int)
    subject_track_map: dict[str, dict[int, int]] = {}
    for s in plan.subjects:
        subject_track_map[s.id] = {int(k): int(v) for k, v in s.scene_track_ids.items()}

    importance_weights = {"high": 1.0, "medium": 0.7, "low": 0.4}

    focus_points: list[FocusPoint] = []

    # Last known face position per shot index — held when faces disappear temporarily
    last_known_x: dict[int, float] = {}
    last_known_y: dict[int, float] = {}

    # Per-subject position tracking catches same-shot ID swaps. Scene cuts are
    # allowed to jump because the same person can appear at a different x position.
    subject_last_x: dict[str, float] = {}
    subject_last_y: dict[str, float] = {}
    subject_last_time: dict[str, float] = {}
    subject_last_shot: dict[str, int] = {}
    rejected_jump_count = 0

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

    def remember_subject(subject_id: str, shot_idx_local: int, face: FaceDetection, time_s: float) -> None:
        last_known_x[shot_idx_local] = face.face_x
        last_known_y[shot_idx_local] = face.face_y
        if subject_id:
            subject_last_x[subject_id] = face.face_x
            subject_last_y[subject_id] = face.face_y
            subject_last_time[subject_id] = time_s
            subject_last_shot[subject_id] = shot_idx_local

    def held_position(subject_id: str, shot_idx_local: int, time_s: float) -> tuple[float, float, float]:
        if subject_id and subject_last_shot.get(subject_id) == shot_idx_local:
            age_s = max(0.0, time_s - subject_last_time.get(subject_id, time_s))
            weight = (
                resolver_config.locked_hold_weight
                if age_s <= resolver_config.target_lock_ttl_s
                else resolver_config.stale_hold_weight
            )
            return subject_last_x[subject_id], subject_last_y[subject_id], weight
        if shot_idx_local in last_known_x:
            return last_known_x[shot_idx_local], last_known_y[shot_idx_local], 0.4
        return shot_median_x.get(shot_idx_local, 0.5), shot_median_y.get(shot_idx_local, 0.35), 0.4

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
            # No faces: hold the active subject if it was recently seen in this shot.
            x, y, hold_weight = held_position(active_subject_id, shot_idx, frame.time_s)
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=x, y=y,
                weight=hold_weight, shot_index=shot_idx, subject_id=active_subject_id,
            ))

        elif shot_type == SHOT_CLOSEUP and len(frame.faces) == 1:
            face = frame.faces[0]
            target_track_id = _target_track_id(
                subject_track_map.get(active_subject_id, {}),
                shot_idx,
            )
            if target_track_id is not None and face.track_id != target_track_id:
                x, y, hold_weight = held_position(active_subject_id, shot_idx, frame.time_s)
                focus_points.append(FocusPoint(
                    time_s=frame.time_s,
                    x=x,
                    y=y,
                    weight=hold_weight,
                    shot_index=shot_idx,
                    subject_id=active_subject_id,
                ))
                continue

            remember_subject(active_subject_id, shot_idx, face, frame.time_s)
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

            # Position consistency gate: reject large same-shot jumps. Scene cuts
            # can legitimately move the same person to a different screen position.
            if (
                face is not None
                and active_subject_id
                and active_subject_id in subject_last_x
                and subject_last_shot.get(active_subject_id) == shot_idx
            ):
                dist = ((face.face_x - subject_last_x[active_subject_id]) ** 2
                        + (face.face_y - subject_last_y[active_subject_id]) ** 2) ** 0.5
                if dist > resolver_config.max_subject_jump:
                    rejected_jump_count += 1
                    logger.debug(
                        "[FocusResolver] t=%.3fs: same-shot jump rejected for %s "
                        "(track_id=%s gap=%.2fs jump=%.3f > %.3f)",
                        frame.time_s,
                        active_subject_id,
                        getattr(face, "track_id", "?"),
                        getattr(face, "track_gap_s", 0.0),
                        dist,
                        resolver_config.max_subject_jump,
                    )
                    face = None

            if face is None:
                # Track ID lost or swap rejected — hold last known position
                x, y, hold_weight = held_position(active_subject_id, shot_idx, frame.time_s)
                focus_points.append(FocusPoint(
                    time_s=frame.time_s, x=x, y=y,
                    weight=hold_weight, shot_index=shot_idx, subject_id=active_subject_id,
                ))
            else:
                remember_subject(active_subject_id, shot_idx, face, frame.time_s)
                focus_points.append(FocusPoint(
                    time_s=frame.time_s,
                    x=face.face_x,
                    y=face.face_y,
                    weight=weight,
                    shot_index=shot_idx,
                    subject_id=active_subject_id,
                ))

    # Diagnostic: per-shot track_id stability summary
    total_holds = sum(
        1
        for fp in focus_points
        if fp.shot_index >= 0 and fp.weight <= resolver_config.locked_hold_weight
    )
    total_tracked = sum(1 for fp in focus_points if fp.weight > resolver_config.locked_hold_weight)
    if total_holds > 0:
        logger.info(
            "[FocusResolver] Track stability: %d tracked, %d held, %d rejected jumps (%.0f%% hold rate)",
            total_tracked, total_holds,
            rejected_jump_count,
            100 * total_holds / (total_tracked + total_holds) if (total_tracked + total_holds) > 0 else 0,
        )

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
    target_track_id = _target_track_id(shot_track_map, shot_idx)

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


def _target_track_id(
    shot_track_map: dict[int, int],
    shot_idx: int,
) -> Optional[int]:
    return shot_track_map.get(shot_idx)
