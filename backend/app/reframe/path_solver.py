"""
Path Solver — AutoFlip-inspired kinematic camera path computation.

Takes weighted focus points and produces a smooth camera path per shot.

Three strategies (selected automatically per shot):
  - STATIONARY: All focus points clustered → single fixed crop position
  - PANNING:    Focus points move linearly  → constant-velocity pan
  - TRACKING:   Complex motion              → velocity-limited smooth tracking

Algorithm ported from Google AutoFlip's kinematic_path_solver.cc:
  1. Median filter — remove frame-to-frame jitter from detections
  2. Motion classification — decide strategy per shot
  3. Kinematic filtering — velocity + acceleration limits for smooth path
  4. Position clamping — ensure crop stays within video bounds

No external dependencies beyond numpy.
"""
import logging
import statistics
from typing import Optional

import numpy as np

from .config import PathSolverConfig
from .types import (
    FocusPoint,
    PathPoint,
    Shot,
    ShotPath,
    STRATEGY_STATIONARY,
    STRATEGY_PANNING,
    STRATEGY_TRACKING,
)

logger = logging.getLogger(__name__)


def solve_paths(
    focus_points: list[FocusPoint],
    shots: list[Shot],
    fps: float,
    config: PathSolverConfig,
) -> list[ShotPath]:
    """
    Compute smooth camera paths for all shots.

    Each shot is processed independently — no cross-shot smoothing
    (camera cuts between shots are intentional jumps).
    """
    frame_dur = 1.0 / fps if fps > 0 else 1.0 / 30.0
    paths: list[ShotPath] = []

    for shot_idx, shot in enumerate(shots):
        # Get focus points for this shot
        shot_points = [fp for fp in focus_points if fp.shot_index == shot_idx]

        if not shot_points:
            # No focus data — center crop for entire shot
            center_path = _make_static_path(shot, 0.5, 0.4, fps)
            paths.append(ShotPath(
                shot_index=shot_idx,
                strategy=STRATEGY_STATIONARY,
                points=center_path,
            ))
            logger.info("[PathSolver] Shot %d: STATIONARY (no focus data) → center", shot_idx)
            continue

        # Step 1: Median filter — remove jitter
        filtered = _median_filter(shot_points, config.median_filter_window)

        # Step 2: Classify motion → pick strategy
        strategy = _classify_motion(filtered, config)

        # Step 3: Compute path based on strategy
        if strategy == STRATEGY_STATIONARY:
            med_x = statistics.median(fp.x for fp in filtered)
            med_y = statistics.median(fp.y for fp in filtered)
            path_points = _make_static_path(shot, med_x, med_y, fps)
            logger.info(
                "[PathSolver] Shot %d: STATIONARY → (%.3f, %.3f)",
                shot_idx, med_x, med_y,
            )

        elif strategy == STRATEGY_PANNING:
            path_points = _compute_panning_path(filtered, shot, fps, config)
            logger.info(
                "[PathSolver] Shot %d: PANNING → %d points",
                shot_idx, len(path_points),
            )

        else:  # TRACKING
            path_points = _compute_tracking_path(filtered, shot, fps, config)
            logger.info(
                "[PathSolver] Shot %d: TRACKING → %d points",
                shot_idx, len(path_points),
            )

        paths.append(ShotPath(
            shot_index=shot_idx,
            strategy=strategy,
            points=path_points,
        ))

    logger.info(
        "[PathSolver] %d shots processed: %s",
        len(paths),
        ", ".join(f"{p.strategy}({len(p.points)}pts)" for p in paths),
    )
    return paths


# --- Median Filter -----------------------------------------------------------

def _median_filter(
    points: list[FocusPoint],
    window: int,
) -> list[FocusPoint]:
    """
    Apply median filter to focus point sequence.
    Removes frame-to-frame jitter while preserving genuine motion.
    """
    if window <= 1 or len(points) <= 1:
        return points

    n = len(points)
    half = window // 2
    filtered: list[FocusPoint] = []

    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        neighbors = points[lo:hi]

        med_x = statistics.median(fp.x for fp in neighbors)
        med_y = statistics.median(fp.y for fp in neighbors)
        # Weight = max weight in window (preserve importance)
        max_w = max(fp.weight for fp in neighbors)

        filtered.append(FocusPoint(
            time_s=points[i].time_s,
            x=round(med_x, 5),
            y=round(med_y, 5),
            weight=max_w,
            shot_index=points[i].shot_index,
            subject_id=points[i].subject_id,
        ))

    return filtered


# --- Motion Classification --------------------------------------------------

def _classify_motion(
    points: list[FocusPoint],
    config: PathSolverConfig,
) -> str:
    """
    Classify motion pattern in focus points.

    - Spread < threshold → STATIONARY
    - Linear fit R² > threshold → PANNING
    - Otherwise → TRACKING
    """
    if len(points) <= 2:
        return STRATEGY_STATIONARY

    xs = [fp.x for fp in points]
    ys = [fp.y for fp in points]

    x_spread = max(xs) - min(xs)
    y_spread = max(ys) - min(ys)
    max_spread = max(x_spread, y_spread)

    # Small motion → stationary
    if max_spread < config.stationary_threshold:
        return STRATEGY_STATIONARY

    # Check if motion is linear (panning)
    times = np.array([fp.time_s for fp in points])
    values = np.array(xs) if x_spread >= y_spread else np.array(ys)

    # Simple linear regression R²
    if len(times) >= 3:
        r_squared = _linear_r_squared(times, values)
        if r_squared > config.panning_linearity_threshold:
            return STRATEGY_PANNING

    return STRATEGY_TRACKING


def _linear_r_squared(x: np.ndarray, y: np.ndarray) -> float:
    """Compute R² of linear fit."""
    if len(x) < 2:
        return 0.0
    n = len(x)
    sum_x = np.sum(x)
    sum_y = np.sum(y)
    sum_xy = np.sum(x * y)
    sum_x2 = np.sum(x ** 2)
    sum_y2 = np.sum(y ** 2)

    denom = (n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)
    if denom <= 0:
        return 0.0

    r = (n * sum_xy - sum_x * sum_y) / (denom ** 0.5)
    return float(r ** 2)


# --- Static Path (Stationary) -----------------------------------------------

def _make_static_path(
    shot: Shot,
    x: float,
    y: float,
    fps: float,
) -> list[PathPoint]:
    """Create a constant-position path for the entire shot."""
    return [
        PathPoint(time_s=round(shot.start_s, 4), x=round(x, 5), y=round(y, 5)),
        PathPoint(time_s=round(shot.end_s, 4), x=round(x, 5), y=round(y, 5)),
    ]


# --- Panning Path ------------------------------------------------------------

def _compute_panning_path(
    points: list[FocusPoint],
    shot: Shot,
    fps: float,
    config: PathSolverConfig,
) -> list[PathPoint]:
    """
    Compute constant-velocity panning path.
    Linear interpolation from first to last focus point, velocity-clamped.
    """
    if len(points) < 2:
        return _make_static_path(shot, points[0].x, points[0].y, fps)

    start_x, start_y = points[0].x, points[0].y
    end_x, end_y = points[-1].x, points[-1].y
    duration = shot.end_s - shot.start_s

    if duration <= 0:
        return _make_static_path(shot, start_x, start_y, fps)

    # Clamp velocity
    dx = end_x - start_x
    dy = end_y - start_y
    distance = (dx ** 2 + dy ** 2) ** 0.5
    max_distance = config.max_velocity * duration

    if distance > max_distance and distance > 0:
        scale = max_distance / distance
        end_x = start_x + dx * scale
        end_y = start_y + dy * scale

    return [
        PathPoint(time_s=round(shot.start_s, 4), x=round(start_x, 5), y=round(start_y, 5)),
        PathPoint(time_s=round(shot.end_s, 4), x=round(end_x, 5), y=round(end_y, 5)),
    ]


# --- Tracking Path (Kinematic Filter) ----------------------------------------

def _compute_tracking_path(
    points: list[FocusPoint],
    shot: Shot,
    fps: float,
    config: PathSolverConfig,
) -> list[PathPoint]:
    """
    Compute velocity-limited tracking path (AutoFlip kinematic solver).

    The path follows focus points but with constraints:
    - Max velocity: prevents too-fast panning
    - Motion threshold: ignores tiny movements (hysteresis)
    - Smooth transitions: velocity changes are gradual
    """
    if not points:
        return _make_static_path(shot, 0.5, 0.4, fps)

    path: list[PathPoint] = []

    # Initialize at first focus point
    curr_x = points[0].x
    curr_y = points[0].y
    path.append(PathPoint(
        time_s=round(points[0].time_s, 4),
        x=round(curr_x, 5),
        y=round(curr_y, 5),
    ))

    for i in range(1, len(points)):
        target_x = points[i].x
        target_y = points[i].y
        dt = points[i].time_s - points[i - 1].time_s

        if dt <= 0:
            continue

        # Compute desired movement
        dx = target_x - curr_x
        dy = target_y - curr_y
        distance = (dx ** 2 + dy ** 2) ** 0.5

        # Motion threshold — ignore tiny movements (hysteresis)
        if distance < config.motion_threshold:
            path.append(PathPoint(
                time_s=round(points[i].time_s, 4),
                x=round(curr_x, 5),
                y=round(curr_y, 5),
            ))
            continue

        # Subject switch detection: Gemini changed the focus person (subject_id changed)
        # OR the position jumped beyond the distance threshold.
        # In either case bypass velocity limit and teleport — hard cut, no interpolation.
        # subject_id check takes priority: even a small positional jump triggers a hard cut
        # when the directive switched to a different person.
        prev_subject_id = points[i - 1].subject_id
        curr_subject_id = points[i].subject_id
        is_subject_change = (
            prev_subject_id != ""
            and curr_subject_id != ""
            and prev_subject_id != curr_subject_id
        )
        if is_subject_change or distance > config.subject_switch_threshold:
            curr_x = target_x
            curr_y = target_y
            if is_subject_change:
                logger.debug(
                    "[PathSolver] t=%.3fs: subject_id change (%s → %s), teleporting to (%.3f, %.3f)",
                    points[i].time_s, prev_subject_id, curr_subject_id, curr_x, curr_y,
                )
            else:
                logger.debug(
                    "[PathSolver] t=%.3fs: subject switch (dist=%.3f > %.2f), teleporting to (%.3f, %.3f)",
                    points[i].time_s, distance, config.subject_switch_threshold, curr_x, curr_y,
                )
        else:
            # Normal velocity-limited smooth tracking
            max_move = config.max_velocity * dt
            if distance > max_move:
                scale = max_move / distance
                dx *= scale
                dy *= scale
            curr_x += dx
            curr_y += dy

        # Clamp to valid range
        curr_x = max(0.0, min(1.0, curr_x))
        curr_y = max(0.0, min(1.0, curr_y))

        path.append(PathPoint(
            time_s=round(points[i].time_s, 4),
            x=round(curr_x, 5),
            y=round(curr_y, 5),
        ))

    # Ensure path covers full shot duration
    if path and path[-1].time_s < shot.end_s - 0.01:
        path.append(PathPoint(
            time_s=round(shot.end_s, 4),
            x=path[-1].x,
            y=path[-1].y,
        ))

    return path
