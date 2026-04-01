"""
Plan Anchor — snaps Gemini's focus plan to real frame data.

Takes the DirectorPlan (semantic: "focus left person from 3.2s to 8.1s") and
produces AnchoredSegments (pixel-precise: validated positions from YOLO).

Three-step anchoring per segment boundary:
  1. Diarization snap  — align to nearest speaker/word boundary
  2. Frame snap        — round to nearest 1/fps frame boundary
  3. YOLO validation   — verify target person exists, get pixel position

Shot-type aware positioning:
  - closeup: single median position per segment (rock-solid stable)
  - wide + stable person: single median position (no jitter)
  - wide + moving person (>5% shift): tracking keyframes (follow movement)
  - b_roll: center crop, single position
"""
import logging
import statistics
from typing import Optional

from .config import AnchorConfig
from .types import (
    AnchoredSegment,
    DirectorPlan,
    FrameAnalysis,
    PersonDetection,
    PositionSample,
    Shot,
    SHOT_CLOSEUP,
    SHOT_BROLL,
)

logger = logging.getLogger(__name__)

# Movement threshold: if median absolute deviation > this, person is moving
_MOVEMENT_THRESHOLD = 0.05  # 5% of frame width/height


def anchor_plan(
    plan: DirectorPlan,
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
    shots: list[Shot],
    fps: float,
    duration_s: float,
    config: AnchorConfig,
) -> list[AnchoredSegment]:
    """
    Anchor all focus segments from the DirectorPlan to YOLO frame data.

    For each segment:
    1. Snap boundaries to diarization + frame times
    2. Determine shot type at segment midpoint
    3. Resolve positions based on shot type (stable vs tracking)
    """
    if not plan.segments:
        return []

    frame_dur = 1.0 / fps if fps > 0 else 1.0 / 30.0

    # Build diarization boundary set for snapping
    diar_boundaries = _extract_diarization_boundaries(diarization_segments)

    anchored: list[AnchoredSegment] = []

    for i, seg in enumerate(plan.segments):
        # 1. Snap segment boundaries
        snapped_start = seg.start_s
        snapped_end = seg.end_s

        if i > 0:
            snapped_start = _snap_to_diarization(
                seg.start_s, diar_boundaries, config.diarization_snap_tolerance_s,
            )
            snapped_start = _snap_to_frame(snapped_start, frame_dur)

        # Ensure contiguity
        if anchored:
            snapped_start = anchored[-1].end_s

        # Last segment ends at duration
        if i == len(plan.segments) - 1:
            snapped_end = duration_s
        else:
            snapped_end = _snap_to_frame(snapped_end, frame_dur)

        # Ensure minimum duration
        if snapped_end - snapped_start < 0.5:
            snapped_end = snapped_start + 0.5

        # 2. Determine shot type for this segment
        shot_type = _get_shot_type_at(snapped_start, snapped_end, shots)

        # 3. Resolve positions based on shot type
        positions = _resolve_positions_for_shot_type(
            shot_type, seg.target, snapped_start, snapped_end,
            frame_analyses, config,
        )

        anchored.append(AnchoredSegment(
            start_s=round(snapped_start, 4),
            end_s=round(snapped_end, 4),
            transition_in=seg.transition_in,
            positions=positions,
            reason=seg.reason,
        ))

    logger.info(
        "[PlanAnchor] %d segments anchored, %d total position samples",
        len(anchored),
        sum(len(s.positions) for s in anchored),
    )
    return anchored


# --- Shot Type Lookup --------------------------------------------------------

def _get_shot_type_at(start_s: float, end_s: float, shots: list[Shot]) -> str:
    """Find the shot type covering the majority of [start_s, end_s]."""
    mid = (start_s + end_s) / 2
    for shot in shots:
        if shot.start_s <= mid < shot.end_s:
            return shot.shot_type
    # Fallback
    return "wide"


# --- Position Resolution (shot-type aware) -----------------------------------

def _resolve_positions_for_shot_type(
    shot_type: str,
    target: str,
    start_s: float,
    end_s: float,
    frame_analyses: list[FrameAnalysis],
    config: AnchorConfig,
) -> list[PositionSample]:
    """
    Resolve positions based on shot type.

    closeup / b_roll: single median position (rock-solid stable)
    wide: check if person moves — if stable, single median; if moving, tracking
    """
    # Collect all raw positions for target person
    raw_positions = _collect_raw_positions(
        target, start_s, end_s, frame_analyses, config,
    )

    if not raw_positions:
        # Fallback: center of frame
        mid_t = (start_s + end_s) / 2
        return [PositionSample(time_s=mid_t, x=0.5, y=0.4)]

    # Close-up and B-roll: always use single median position
    if shot_type in (SHOT_CLOSEUP, SHOT_BROLL):
        median_pos = _compute_median_position(raw_positions, start_s, end_s)
        logger.debug(
            "[PlanAnchor] %s segment %.1f-%.1fs: stable median (%.3f, %.3f)",
            shot_type, start_s, end_s, median_pos.x, median_pos.y,
        )
        return [median_pos]

    # Wide shot: check if person actually moves
    x_values = [p.x for p in raw_positions]
    y_values = [p.y for p in raw_positions]

    x_spread = max(x_values) - min(x_values) if len(x_values) > 1 else 0.0
    y_spread = max(y_values) - min(y_values) if len(y_values) > 1 else 0.0

    if x_spread < _MOVEMENT_THRESHOLD and y_spread < _MOVEMENT_THRESHOLD:
        # Person is stationary — use single median position (no jitter)
        median_pos = _compute_median_position(raw_positions, start_s, end_s)
        logger.debug(
            "[PlanAnchor] wide stable segment %.1f-%.1fs: median (%.3f, %.3f), spread=(%.4f, %.4f)",
            start_s, end_s, median_pos.x, median_pos.y, x_spread, y_spread,
        )
        return [median_pos]

    # Person is moving — return smoothed tracking positions
    smoothed = _smooth_positions(raw_positions, config.position_smoothing_window)
    logger.debug(
        "[PlanAnchor] wide tracking segment %.1f-%.1fs: %d positions, spread=(%.4f, %.4f)",
        start_s, end_s, len(smoothed), x_spread, y_spread,
    )
    return smoothed


def _collect_raw_positions(
    target: str,
    start_s: float,
    end_s: float,
    frame_analyses: list[FrameAnalysis],
    config: AnchorConfig,
) -> list[PositionSample]:
    """Collect raw YOLO positions for the target person in the time range."""
    relevant_frames = [
        fa for fa in frame_analyses
        if start_s - 0.05 <= fa.time_s <= end_s + 0.05
    ]

    if not relevant_frames:
        # Try nearest frame
        nearest = _find_nearest_frame(frame_analyses, (start_s + end_s) / 2)
        if nearest and nearest.persons:
            person = _pick_person_by_position(nearest.persons, target)
            x, y = _get_framing_position(person, config.headroom_ratio)
            return [PositionSample(time_s=(start_s + end_s) / 2, x=x, y=y)]
        return []

    raw: list[PositionSample] = []
    for fa in relevant_frames:
        if not fa.persons:
            continue
        person = _pick_person_by_position(fa.persons, target)
        x, y = _get_framing_position(person, config.headroom_ratio)
        raw.append(PositionSample(time_s=fa.time_s, x=x, y=y))

    return raw


def _compute_median_position(
    positions: list[PositionSample],
    start_s: float,
    end_s: float,
) -> PositionSample:
    """Compute a single median position from all samples. Rock-solid stable."""
    if len(positions) == 1:
        return positions[0]

    med_x = statistics.median(p.x for p in positions)
    med_y = statistics.median(p.y for p in positions)
    mid_t = (start_s + end_s) / 2

    return PositionSample(time_s=mid_t, x=round(med_x, 5), y=round(med_y, 5))


# --- Boundary Snapping -------------------------------------------------------

def _extract_diarization_boundaries(segments: list[dict]) -> list[float]:
    """Extract all start/end times from diarization as snap candidates."""
    boundaries: set[float] = set()
    for seg in segments:
        boundaries.add(seg.get("start", 0))
        boundaries.add(seg.get("end", 0))
    return sorted(boundaries)


def _snap_to_diarization(
    time_s: float,
    boundaries: list[float],
    tolerance: float,
) -> float:
    """Snap time to nearest diarization boundary if within tolerance."""
    if not boundaries:
        return time_s

    best_dist = float("inf")
    best_time = time_s

    for b in boundaries:
        dist = abs(time_s - b)
        if dist < best_dist:
            best_dist = dist
            best_time = b

    if best_dist <= tolerance:
        return best_time
    return time_s


def _snap_to_frame(time_s: float, frame_dur: float) -> float:
    """Round time to nearest frame boundary."""
    if frame_dur <= 0:
        return time_s
    frame_idx = round(time_s / frame_dur)
    return frame_idx * frame_dur


# --- Person Selection --------------------------------------------------------

def _pick_person_by_position(
    persons: list[PersonDetection],
    target: str,
) -> PersonDetection:
    """
    Pick the person matching the target position.
    If only 1 person detected, always return that person regardless of target.
    """
    if len(persons) == 1:
        return persons[0]

    sorted_by_x = sorted(persons, key=lambda p: p.center_x)

    if target == "left":
        return sorted_by_x[0]
    elif target == "right":
        return sorted_by_x[-1]
    elif target == "center":
        return min(persons, key=lambda p: abs(p.center_x - 0.5))
    else:
        return max(persons, key=lambda p: p.area)


def _get_framing_position(
    person: PersonDetection,
    headroom_ratio: float,
) -> tuple[float, float]:
    """Get ideal crop center position. Face keypoint preferred with headroom."""
    x = person.framing_x

    if person.face_y is not None:
        y = person.face_y - person.bbox_height * headroom_ratio
    else:
        y = person.center_y - person.bbox_height * 0.25

    return x, y


def _find_nearest_frame(
    frame_analyses: list[FrameAnalysis],
    target_time: float,
) -> Optional[FrameAnalysis]:
    """Find the frame analysis nearest to target_time."""
    if not frame_analyses:
        return None

    best: Optional[FrameAnalysis] = None
    best_dist = float("inf")

    for fa in frame_analyses:
        dist = abs(fa.time_s - target_time)
        if dist < best_dist:
            best = fa
            best_dist = dist

    return best


# --- Smoothing ---------------------------------------------------------------

def _smooth_positions(
    positions: list[PositionSample],
    window: int,
) -> list[PositionSample]:
    """Simple moving average for tracking mode (only used when person is moving)."""
    if window <= 1 or len(positions) <= 1:
        return positions

    n = len(positions)
    half_w = window // 2
    smoothed: list[PositionSample] = []

    for i in range(n):
        lo = max(0, i - half_w)
        hi = min(n, i + half_w + 1)
        count = hi - lo

        avg_x = sum(positions[j].x for j in range(lo, hi)) / count
        avg_y = sum(positions[j].y for j in range(lo, hi)) / count

        smoothed.append(PositionSample(
            time_s=positions[i].time_s,
            x=round(avg_x, 5),
            y=round(avg_y, 5),
        ))

    return smoothed
