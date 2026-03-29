from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class SceneInterval:
    """A scene with float-second boundaries (never frame numbers)."""
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class Keypoint:
    """Single COCO pose keypoint (normalized 0-1)."""
    x_norm: float
    y_norm: float
    confidence: float


@dataclass
class PersonDetection:
    """
    One person detected by YOLOv8 in a frame.
    All coordinates are normalized [0.0, 1.0] relative to frame dimensions.
    """
    cx_norm: float       # bounding box center X
    cy_norm: float       # bounding box center Y
    width_norm: float    # bounding box width
    height_norm: float   # bounding box height
    confidence: float    # detection confidence
    gaze_direction: Literal["left", "right", "center", "unknown"] = "unknown"
    keypoints: Optional[List[Keypoint]] = field(default=None)  # 17 COCO keypoints or None


@dataclass
class SceneAnalysis:
    """YOLOv8 detection result for one scene (first-frame sampling)."""
    scene: SceneInterval
    persons: List[PersonDetection]  # may be empty


@dataclass
class ReframeDecision:
    """
    Crop decision for one scene produced by the strategy layer.
    crop_x_norm: normalized crop window start X in [0.0, 1.0]
    """
    scene: SceneInterval
    crop_x_norm: float          # 0.0 = leftmost crop, 1.0 = rightmost
    target_person_idx: int      # index into SceneAnalysis.persons (-1 = no person)
    reasoning: str              # human-readable debug string


@dataclass
class ReframeResult:
    """Final output returned by the processor."""
    keyframes: List[dict]       # [{time_s, offset_x, interpolation}]
    scene_cuts: List[float]     # scene boundary timestamps in seconds
    src_w: int
    src_h: int
    fps: float
    duration_s: float
