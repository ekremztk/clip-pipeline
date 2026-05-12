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
    5. Validate position consistency — reject track_id swaps
    """
    # Build: subject_id → shot_idx(int) → track_id(int)
    subject_track_map: dict[str, dict[int, int]] = {}
    for s in plan.subjects:
        subject_track_map[s.id] = {int(k): int(v) for k, v in s.scene_track_ids.items()}

    importance_weights = {"high": 1.0, "medium": 0.7, "low": 0.4}

    focus_points: list[FocusPoint] = []

    # Last known face positions scoped by shot+subject/track. A shot-level
    # fallback is too broad in panel shows: it can borrow another guest's face.
    last_known_subject_x: dict[tuple[int, str], float] = {}
    last_known_subject_y: dict[tuple[int, str], float] = {}
    last_known_track_x: dict[tuple[int, int], float] = {}
    last_known_track_y: dict[tuple[int, int], float] = {}

    # Per-subject position tracking — catches track_id swaps that spatial matching
    # misassigns. If a "matched" face is far from where this subject was last seen,
    # it's a YOLO track_id swap, not actual movement. Hold position instead.
    subject_last_x: dict[str, float] = {}
    subject_last_y: dict[str, float] = {}
    subject_last_shot_idx: dict[str, int] = {}
    # Max allowed per-sample jump (at 5fps = 200ms interval). Seated speakers move
    # ~2-5% of frame per sample. 8% catches fast head turns; anything above that
    # is almost certainly a track_id that swapped to the other person's face.
    MAX_SUBJECT_JUMP = 0.08
    INITIAL_TRACK_MEDIAN_MAX_DIST = 0.12
    # After N consecutive holds, accept the new position (genuine movement, not swap)
    MAX_CONSECUTIVE_HOLDS = 3
    subject_hold_count: dict[str, int] = {}

    # Pre-compute per-shot face position medians as fallback for first-frame misses
    shot_median_x: dict[int, float] = {}
    shot_median_y: dict[int, float] = {}
    shot_track_median_x: dict[tuple[int, int], float] = {}
    shot_track_median_y: dict[tuple[int, int], float] = {}
    import statistics as _stats
    for shot_idx_pre in set(f.shot_index for f in frames):
        xs = [face.face_x for f in frames if f.shot_index == shot_idx_pre for face in f.faces]
        ys = [face.face_y for f in frames if f.shot_index == shot_idx_pre for face in f.faces]
        if xs:
            shot_median_x[shot_idx_pre] = _stats.median(xs)
            shot_median_y[shot_idx_pre] = _stats.median(ys)
        track_ids = {
            face.track_id
            for f in frames if f.shot_index == shot_idx_pre
            for face in f.faces
            if face.track_id >= 0
        }
        for track_id in track_ids:
            txs = [
                face.face_x
                for f in frames if f.shot_index == shot_idx_pre
                for face in f.faces
                if face.track_id == track_id
            ]
            tys = [
                face.face_y
                for f in frames if f.shot_index == shot_idx_pre
                for face in f.faces
                if face.track_id == track_id
            ]
            if txs:
                shot_track_median_x[(shot_idx_pre, track_id)] = _stats.median(txs)
                shot_track_median_y[(shot_idx_pre, track_id)] = _stats.median(tys)

    def _fallback_position(
        shot_idx: int,
        subject_id: str,
        target_track_id: Optional[int],
    ) -> tuple[float, float]:
        """Return a scoped fallback that avoids borrowing another panelist."""
        subject_key = (shot_idx, subject_id)
        if subject_id and subject_key in last_known_subject_x:
            return last_known_subject_x[subject_key], last_known_subject_y[subject_key]

        if target_track_id is not None:
            track_key = (shot_idx, target_track_id)
            if track_key in last_known_track_x:
                return last_known_track_x[track_key], last_known_track_y[track_key]
            if track_key in shot_track_median_x:
                return shot_track_median_x[track_key], shot_track_median_y[track_key]

        if subject_id and subject_last_shot_idx.get(subject_id) == shot_idx:
            return subject_last_x[subject_id], subject_last_y[subject_id]

        return shot_median_x.get(shot_idx, 0.5), shot_median_y.get(shot_idx, 0.35)

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
        target_track_id = subject_track_map.get(active_subject_id, {}).get(shot_idx)

        if shot_type == SHOT_BROLL:
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=0.5, y=0.4,
                weight=0.3, shot_index=shot_idx, subject_id="",
            ))

        elif not frame.faces:
            # No faces — hold the active subject/track, not a shot-wide fallback.
            x, y = _fallback_position(shot_idx, active_subject_id, target_track_id)
            focus_points.append(FocusPoint(
                time_s=frame.time_s, x=x, y=y,
                weight=0.4, shot_index=shot_idx, subject_id=active_subject_id,
            ))

        elif shot_type == SHOT_CLOSEUP and len(frame.faces) == 1:
            face = frame.faces[0]
            if active_subject_id:
                last_known_subject_x[(shot_idx, active_subject_id)] = face.face_x
                last_known_subject_y[(shot_idx, active_subject_id)] = face.face_y
            if face.track_id >= 0:
                last_known_track_x[(shot_idx, face.track_id)] = face.face_x
                last_known_track_y[(shot_idx, face.track_id)] = face.face_y
            if active_subject_id:
                subject_last_x[active_subject_id] = face.face_x
                subject_last_y[active_subject_id] = face.face_y
                subject_last_shot_idx[active_subject_id] = shot_idx
                subject_hold_count[active_subject_id] = 0
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

            # New-shot guard: the first sampled frame of a cut is the most likely
            # place for tracker IDs to be missing or momentarily wrong. If the
            # first matched face for this subject in this shot is far from that
            # target track's shot median, ignore it and seed from the median.
            subject_key = (shot_idx, active_subject_id)
            track_key = (shot_idx, target_track_id) if target_track_id is not None else None
            if (
                face is not None
                and active_subject_id
                and subject_key not in last_known_subject_x
                and track_key is not None
                and track_key in shot_track_median_x
            ):
                median_dist = (
                    (face.face_x - shot_track_median_x[track_key]) ** 2
                    + (face.face_y - shot_track_median_y[track_key]) ** 2
                ) ** 0.5
                if median_dist > INITIAL_TRACK_MEDIAN_MAX_DIST:
                    logger.debug(
                        "[FocusResolver] t=%.3fs: first match for %s in shot %d is far "
                        "from target track median (dist=%.3f > %.3f), using median fallback",
                        frame.time_s, active_subject_id, shot_idx,
                        median_dist, INITIAL_TRACK_MEDIAN_MAX_DIST,
                    )
                    face = None

            # Position consistency gate: if we have a prior position for this
            # subject and the matched face jumped too far, it's a track_id swap.
            # Only compare within the same shot. Across scene cuts, the same
            # subject can legitimately appear at a very different screen position.
            same_subject_shot = subject_last_shot_idx.get(active_subject_id) == shot_idx
            if face is not None and active_subject_id and active_subject_id in subject_last_x and same_subject_shot:
                dist = ((face.face_x - subject_last_x[active_subject_id]) ** 2
                        + (face.face_y - subject_last_y[active_subject_id]) ** 2) ** 0.5
                if dist > MAX_SUBJECT_JUMP:
                    holds = subject_hold_count.get(active_subject_id, 0)
                    if holds < MAX_CONSECUTIVE_HOLDS:
                        logger.debug(
                            "[FocusResolver] t=%.3fs: track_id swap suspected for %s "
                            "(jump=%.3f > %.3f, hold #%d), holding position",
                            frame.time_s, active_subject_id, dist, MAX_SUBJECT_JUMP, holds + 1,
                        )
                        subject_hold_count[active_subject_id] = holds + 1
                        face = None  # reject → hold last known
                    else:
                        # Held too many times — accept new position (genuine movement)
                        logger.debug(
                            "[FocusResolver] t=%.3fs: accepting new position for %s "
                            "after %d holds (dist=%.3f)",
                            frame.time_s, active_subject_id, holds, dist,
                        )
                        subject_hold_count[active_subject_id] = 0
                else:
                    subject_hold_count[active_subject_id] = 0

            if face is None:
                # Track ID lost or swap rejected — hold the active subject/track.
                x, y = _fallback_position(shot_idx, active_subject_id, target_track_id)
                focus_points.append(FocusPoint(
                    time_s=frame.time_s, x=x, y=y,
                    weight=0.4, shot_index=shot_idx, subject_id=active_subject_id,
                ))
            else:
                if active_subject_id:
                    last_known_subject_x[(shot_idx, active_subject_id)] = face.face_x
                    last_known_subject_y[(shot_idx, active_subject_id)] = face.face_y
                if face.track_id >= 0:
                    last_known_track_x[(shot_idx, face.track_id)] = face.face_x
                    last_known_track_y[(shot_idx, face.track_id)] = face.face_y
                if active_subject_id:
                    subject_last_x[active_subject_id] = face.face_x
                    subject_last_y[active_subject_id] = face.face_y
                    subject_last_shot_idx[active_subject_id] = shot_idx
                focus_points.append(FocusPoint(
                    time_s=frame.time_s,
                    x=face.face_x,
                    y=face.face_y,
                    weight=weight,
                    shot_index=shot_idx,
                    subject_id=active_subject_id,
                ))

    # Diagnostic: per-shot track_id stability summary
    total_holds = sum(1 for fp in focus_points if fp.weight == 0.4 and fp.shot_index >= 0)
    total_tracked = sum(1 for fp in focus_points if fp.weight > 0.4)
    if total_holds > 0:
        logger.info(
            "[FocusResolver] Track stability: %d tracked, %d held (%.0f%% hold rate — "
            "high rate indicates frequent track_id swaps)",
            total_tracked, total_holds,
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
