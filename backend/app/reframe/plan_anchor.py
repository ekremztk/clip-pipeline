"""
Plan Anchor — snaps Gemini's focus plan to real frame data.

Takes the DirectorPlan (semantic: "focus left person from 3.2s to 8.1s") and
produces AnchoredSegments (pixel-precise: validated positions from YOLO).

Three-step anchoring per segment boundary:
  1. Diarization snap  — align to nearest speaker/word boundary
  2. Frame snap        — round to nearest 1/fps frame boundary
  3. YOLO validation   — verify target person exists, get pixel position

Within each segment, YOLO positions are sampled and smoothed with a simple
moving average to eliminate detection jitter.
"""
import logging
from typing import Optional

from .config import AnchorConfig
from .types import (
    AnchoredSegment,
    DirectorPlan,
    FocusSegment,
    FrameAnalysis,
    PersonDetection,
    PositionSample,
)

logger = logging.getLogger(__name__)


def anchor_plan(
    plan: DirectorPlan,
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
    fps: float,
    duration_s: float,
    config: AnchorConfig,
) -> list[AnchoredSegment]:
    """
    Anchor all focus segments from the DirectorPlan to YOLO frame data.

    For each segment:
    1. Snap boundaries to diarization + frame times
    2. Find YOLO frames within the segment
    3. Resolve "left"/"right"/"center" to actual person positions
    4. Smooth positions with moving average
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
            # Snap start to diarization boundary, then to frame
            snapped_start = _snap_to_diarization(
                seg.start_s, diar_boundaries, config.diarization_snap_tolerance_s,
            )
            snapped_start = _snap_to_frame(snapped_start, frame_dur)

        # Ensure contiguity: this segment starts where previous ended
        if anchored:
            snapped_start = anchored[-1].end_s

        # Last segment ends exactly at duration
        if i == len(plan.segments) - 1:
            snapped_end = duration_s
        else:
            snapped_end = _snap_to_frame(snapped_end, frame_dur)

        # Ensure minimum duration
        if snapped_end - snapped_start < 0.5:
            snapped_end = snapped_start + 0.5

        # 2. Collect YOLO positions for this segment
        positions = _resolve_segment_positions(
            seg.target, snapped_start, snapped_end,
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


# --- Position Resolution -----------------------------------------------------

def _resolve_segment_positions(
    target: str,
    start_s: float,
    end_s: float,
    frame_analyses: list[FrameAnalysis],
    config: AnchorConfig,
) -> list[PositionSample]:
    """
    Resolve a target position ("left", "right", "center") to actual
    YOLO-validated coordinates for all frames within the segment.
    """
    # Collect relevant frames
    relevant_frames = [
        fa for fa in frame_analyses
        if start_s - 0.05 <= fa.time_s <= end_s + 0.05
    ]

    if not relevant_frames:
        # No YOLO data for this segment — extrapolate from nearest frames
        nearest = _find_nearest_frame(frame_analyses, (start_s + end_s) / 2)
        if nearest and nearest.persons:
            person = _pick_person_by_position(nearest.persons, target)
            x, y = _get_framing_position(person, config.headroom_ratio)
            return [PositionSample(time_s=(start_s + end_s) / 2, x=x, y=y)]
        # Absolute fallback: center
        return [PositionSample(time_s=(start_s + end_s) / 2, x=0.5, y=0.4)]

    # Extract position for target person in each frame
    raw_positions: list[PositionSample] = []

    for fa in relevant_frames:
        if not fa.persons:
            continue

        person = _pick_person_by_position(fa.persons, target)
        x, y = _get_framing_position(person, config.headroom_ratio)
        raw_positions.append(PositionSample(time_s=fa.time_s, x=x, y=y))

    if not raw_positions:
        return [PositionSample(time_s=(start_s + end_s) / 2, x=0.5, y=0.4)]

    # Apply moving average to smooth YOLO jitter
    smoothed = _smooth_positions(raw_positions, config.position_smoothing_window)

    return smoothed


def _pick_person_by_position(
    persons: list[PersonDetection],
    target: str,
) -> PersonDetection:
    """
    Pick the person matching the target position.

    "left"   → person with smallest center_x (stable_id 0)
    "right"  → person with largest center_x (stable_id max)
    "center" → person closest to center_x = 0.5

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
        # Unknown target — return largest person
        return max(persons, key=lambda p: p.area)


def _get_framing_position(
    person: PersonDetection,
    headroom_ratio: float,
) -> tuple[float, float]:
    """
    Get the ideal crop center position for a person.
    Uses face keypoint if available, with headroom adjustment for Y.
    """
    x = person.framing_x

    if person.face_y is not None:
        # Face detected: slight upward shift for headroom
        y = person.face_y - person.bbox_height * headroom_ratio
    else:
        # No face: use bbox center shifted up more aggressively
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
    """
    Simple moving average over X and Y positions.
    Eliminates YOLO detection jitter without the complexity of EMA/dead zones.
    """
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
