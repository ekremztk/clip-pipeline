"""
Reframe V5 configuration.

All tunable parameters live here. Modules read from config, never hardcode values.
"""
from dataclasses import dataclass, field


# --- Stage 1: Shot Detection ------------------------------------------------

@dataclass
class ShotDetectionConfig:
    """FFmpeg scene detection parameters."""
    threshold: float = 0.08
    min_shot_duration_s: float = 0.3
    min_cut_gap_s: float = 0.5


# --- Stage 2: Face Tracker (MediaPipe) --------------------------------------

@dataclass
class FaceTrackerConfig:
    """MediaPipe face detection + tracking parameters."""
    sample_fps: float = 5.0                     # How many frames per second to sample
    min_detection_confidence: float = 0.5       # MediaPipe face detection threshold
    max_faces: int = 4                          # Max faces to track per frame
    person_height_multiplier: float = 3.5       # Estimate person height from face height
    analysis_resolution: tuple[int, int] = (640, 360)   # Downscale for speed


# --- Stage 3: Gemini Director -----------------------------------------------

@dataclass
class GeminiDirectorConfig:
    """Gemini video analysis parameters."""
    model: str = ""                             # Empty = use settings.GEMINI_MODEL_PRO
    content_type_hint: str = "auto"             # Hint only — Gemini decides for itself
    min_segment_duration_s: float = 1.5
    timeout_s: float = 60.0


# --- Stage 4: Path Solver (AutoFlip-style) ----------------------------------

@dataclass
class PathSolverConfig:
    """Kinematic path solver parameters (ported from AutoFlip)."""
    # Strategy selection thresholds
    stationary_threshold: float = 0.02          # Max spread to use stationary mode
    panning_linearity_threshold: float = 0.85   # Min R^2 for linear fit to use panning

    # Kinematic constraints
    max_velocity: float = 0.8                   # Max crop movement per second (normalized)
    max_acceleration: float = 2.0               # Max velocity change per second (normalized)

    # Smoothing
    median_filter_window: int = 5               # Median filter size for jitter removal
    motion_threshold: float = 0.02              # Ignore motion smaller than this (hysteresis)

    # Headroom
    headroom_ratio: float = 0.15                # How much above face center to place crop center


# --- Stage 5: Keyframe Emitter ----------------------------------------------

@dataclass
class KeyframeEmitterConfig:
    """Keyframe generation parameters."""
    dedup_threshold_px: float = 5.0             # Skip keyframes with < N px movement
    y_headroom_zoom: float = 1.12               # Extra zoom for Y panning room


# --- Top-level config --------------------------------------------------------

@dataclass
class ReframeConfig:
    """Main configuration — nests all sub-configs."""
    shot_detection: ShotDetectionConfig = field(default_factory=ShotDetectionConfig)
    face_tracker: FaceTrackerConfig = field(default_factory=FaceTrackerConfig)
    gemini_director: GeminiDirectorConfig = field(default_factory=GeminiDirectorConfig)
    path_solver: PathSolverConfig = field(default_factory=PathSolverConfig)
    keyframe_emitter: KeyframeEmitterConfig = field(default_factory=KeyframeEmitterConfig)

    # Global settings
    aspect_ratio: tuple[int, int] = (9, 16)
    tracking_mode: str = "dynamic_xy"
