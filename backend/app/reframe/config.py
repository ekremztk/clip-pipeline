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


# --- Stage 2: Face Tracker --------------------------------------------------

@dataclass
class FaceTrackerConfig:
    """YOLO face detection + tracking parameters."""
    sample_fps: float = 5.0                     # How many frames per second to sample
    min_detection_confidence: float = 0.55      # Detection confidence threshold
    max_faces: int = 4                          # Max faces to track per frame
    person_height_multiplier: float = 3.5       # Estimate person height from face height
    yolo_imgsz: int = 1280                      # YOLO inference resolution


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
    # Three-zone model (motion_threshold < stationary_threshold < subject_switch_threshold):
    #   [0, motion_threshold)         → noise, skip this frame's movement entirely
    #   [motion_threshold, stationary_threshold) → micro-tracking zone: track per-frame but
    #                                   classify the whole shot as STATIONARY (stable crop)
    #   [stationary_threshold, subject_switch_threshold) → genuine motion → TRACKING
    #   [subject_switch_threshold, 1]  → person changed → teleport
    #
    # stationary_threshold = 0.15 (15% of frame width):
    #   Podcast closeup — person nods/leans but stays roughly in place → spread 0.03-0.12
    #   → STATIONARY → single stable crop (no jitter from chasing micro-movements).
    #   Subject walking across frame → spread > 0.15 → TRACKING.
    # motion_threshold = 0.005 (0.5% = ~10px at 1920px):
    #   Filters sensor/detection noise. Catches genuine micro-movements within a TRACKING shot.
    stationary_threshold: float = 0.15          # Max spread to use stationary mode (15% of frame)
    # Raised back from 0.10: podcast speakers (seated) have head spread of 0.03-0.12.
    # At 0.10 threshold, subtle leans/nods trigger TRACKING mode → jitter.
    # At 0.15, only genuine position changes trigger tracking; median filter absorbs noise.
    # (The "face leaving crop" concern at 0.158 only applies to walking/standing content,
    # not seated podcast speakers. For those cases use a custom config or content type.)
    panning_linearity_threshold: float = 0.85   # Min R^2 for linear fit to use panning

    # Kinematic constraints
    max_velocity: float = 1.5                   # Max crop movement per second (normalized)
    max_acceleration: float = 2.0               # Max velocity change per second (normalized)

    # Smoothing
    median_filter_window: int = 5               # Median filter size for jitter removal
    motion_threshold: float = 0.005             # Ignore motion smaller than this (hysteresis)
    # At 1920px wide: 0.005 * 1920 = ~10px — catches subtle head nods in podcasts

    # Subject switch detection — large jump in focus means directive changed persons
    # Path solver teleports (bypasses velocity limit) when jump > this threshold (normalized 0-1)
    # Keyframe emitter emits hold+hold hard cut when pixel jump > threshold * src_w
    subject_switch_threshold: float = 0.22
    # Lowered from 0.30: speakers at x=0.35 and x=0.65 are 0.30 apart — the old
    # threshold barely caught this. 0.22 reliably triggers hard cut for any
    # meaningful speaker-to-speaker jump while staying above typical single-person
    # movement (<0.15 for most seated podcast content).

    # Headroom
    headroom_ratio: float = 0.15                # How much above face center to place crop center


# --- Stage 5: Keyframe Emitter ----------------------------------------------

@dataclass
class KeyframeEmitterConfig:
    """Keyframe generation parameters."""
    dedup_threshold_px: float = 5.0             # Skip keyframes with < N px movement
    y_headroom_zoom: float = 1.12               # Extra zoom for Y panning room
    # Subject switch: emit hold+hold hard cut when X offset jumps > threshold * src_w
    # Matches PathSolverConfig.subject_switch_threshold so both layers agree on what's a switch
    subject_switch_threshold: float = 0.22


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
