"""
Reframe V4 (Director's Cut) data types.

Data flow:
  Shot, FrameAnalysis, PersonDetection  → shared (shot_detector, frame_analyzer)
  FocusSegment, DirectorPlan            → video_director output
  AnchoredSegment                       → plan_anchor output
  ReframeKeyframe, ReframeResult        → keyframe_converter output
"""
from dataclasses import dataclass, field
from typing import Optional


# --- Shared types (shot_detector + frame_analyzer) ---------------------------

@dataclass
class Shot:
    """A continuous camera angle / scene."""
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class PersonDetection:
    """Single person detection in one frame (from YOLO)."""
    center_x: float      # 0.0-1.0 normalized bbox center
    center_y: float
    bbox_width: float     # 0.0-1.0 normalized
    bbox_height: float
    confidence: float
    face_x: Optional[float] = None   # Nose keypoint X (normalized)
    face_y: Optional[float] = None   # Nose keypoint Y (normalized)
    stable_id: int = -1              # Position-based: 0=leftmost, 1=next...

    @property
    def area(self) -> float:
        return self.bbox_width * self.bbox_height

    @property
    def framing_x(self) -> float:
        """Best X for crop centering: face if available, else bbox center."""
        return self.face_x if self.face_x is not None else self.center_x

    @property
    def framing_y(self) -> float:
        """Best Y for crop centering: face if available, else bbox center."""
        return self.face_y if self.face_y is not None else self.center_y


@dataclass
class FrameAnalysis:
    """YOLO analysis result for one sampled frame."""
    time_s: float
    shot_index: int
    persons: list[PersonDetection] = field(default_factory=list)


# --- Video Director types (Gemini output) ------------------------------------

@dataclass
class SpeakerInfo:
    """A speaker identified by Gemini in the video."""
    position: str          # "left", "right", "center"
    description: str       # Brief visual description from Gemini


@dataclass
class FocusSegment:
    """One focus segment from Gemini's director plan (raw, not yet anchored)."""
    start_s: float
    end_s: float
    target: str            # "left", "right", "center" — matches SpeakerInfo.position
    transition_in: str     # "cut" or "smooth"
    reason: str = ""


@dataclass
class DirectorPlan:
    """Complete output from Gemini video analysis."""
    content_type: str                          # "podcast", "interview", etc.
    layout: str                                # "side_by_side", "single", etc.
    speakers: list[SpeakerInfo] = field(default_factory=list)
    segments: list[FocusSegment] = field(default_factory=list)


# --- Plan Anchor types (YOLO-validated) --------------------------------------

@dataclass
class PositionSample:
    """A single YOLO-validated position within a segment."""
    time_s: float
    x: float               # Normalized framing X (face or bbox center)
    y: float               # Normalized framing Y with headroom


@dataclass
class AnchoredSegment:
    """Focus segment after timestamp snapping + YOLO position validation."""
    start_s: float                     # Frame-snapped start time
    end_s: float                       # Frame-snapped end time
    transition_in: str                 # "cut" or "smooth"
    positions: list[PositionSample] = field(default_factory=list)
    reason: str = ""


# --- Final output types ------------------------------------------------------

@dataclass
class ReframeKeyframe:
    """Keyframe sent to the frontend editor."""
    time_s: float
    offset_x: float        # Pixel offset from left edge of source
    offset_y: float        # Pixel offset from top edge of source
    interpolation: str     # "linear" or "hold"


@dataclass
class ReframeResult:
    """Final pipeline output."""
    keyframes: list[ReframeKeyframe] = field(default_factory=list)
    scene_cuts: list[float] = field(default_factory=list)
    src_w: int = 0
    src_h: int = 0
    fps: float = 30.0
    duration_s: float = 0.0
    content_type: str = ""
    tracking_mode: str = "dynamic_xy"
    metadata: dict = field(default_factory=dict)
