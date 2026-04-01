"""
Reframe V4 (Director's Cut) configuration.

All tunable parameters live here. No hardcoded values in modules.
"""
from dataclasses import dataclass, field


# --- Stage 1: Shot Detection (unchanged) ------------------------------------

@dataclass
class ShotDetectionConfig:
    """FFmpeg scene detection parameters."""
    threshold: float = 0.08
    min_shot_duration_s: float = 0.3
    min_cut_gap_s: float = 0.5


# --- Stage 2: Frame Analysis (unchanged) ------------------------------------

@dataclass
class FrameAnalysisConfig:
    """YOLOv8-pose frame analysis parameters."""
    model_path: str = "yolov8s-pose.pt"
    confidence_threshold: float = 0.40
    analysis_resolution: tuple[int, int] = (640, 360)
    sample_fps: float = 5.0
    max_persons_per_frame: int = 4


# --- Stage 3: Video Director (Gemini Pro + Video) ---------------------------

@dataclass
class VideoDirectorConfig:
    """Gemini Pro video analysis parameters."""
    model: str = ""                    # Empty = use settings.GEMINI_MODEL_PRO at runtime
    content_type: str = "auto"         # Style guide selector
    min_segment_duration_s: float = 1.5
    timeout_s: float = 60.0


# --- Stage 4: Plan Anchor (timestamp snapping + YOLO validation) ------------

@dataclass
class AnchorConfig:
    """Timestamp anchoring and YOLO validation parameters."""
    diarization_snap_tolerance_s: float = 0.5   # Max distance to snap to diarization boundary
    position_smoothing_window: int = 3          # Moving average window for YOLO jitter
    headroom_ratio: float = 0.05                # Face Y offset: face_y - bbox_h * ratio


# --- Stage 5: Keyframe Converter ---------------------------------------------

@dataclass
class KeyframeConfig:
    """Keyframe generation parameters."""
    dedup_threshold_px: float = 5.0    # Skip keyframes with < N px movement
    smooth_transition_s: float = 0.3   # Duration of "smooth" transitions
    y_headroom_zoom: float = 1.12      # Extra zoom for Y panning room


# --- Top-level config ---------------------------------------------------------

@dataclass
class ReframeConfig:
    """Main configuration — nests all sub-configs."""
    shot_detection: ShotDetectionConfig = field(default_factory=ShotDetectionConfig)
    frame_analysis: FrameAnalysisConfig = field(default_factory=FrameAnalysisConfig)
    video_director: VideoDirectorConfig = field(default_factory=VideoDirectorConfig)
    anchor: AnchorConfig = field(default_factory=AnchorConfig)
    keyframe: KeyframeConfig = field(default_factory=KeyframeConfig)

    # Global settings
    aspect_ratio: tuple[int, int] = (9, 16)
    tracking_mode: str = "dynamic_xy"
