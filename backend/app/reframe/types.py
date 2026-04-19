"""
Reframe V5 data types.

Data flow:
  Shot                    → shot_detector (FFmpeg scene cuts)
  FaceDetection, Frame    → face_tracker (MediaPipe per-frame detections)
  SubjectInfo, FocusPlan  → gemini_director (high-level creative plan)
  FocusPoint              → focus_resolver (merged Gemini + detections)
  SmoothPath              → path_solver (AutoFlip-style kinematic path)
  ReframeKeyframe, Result → keyframe_emitter (pixel offsets for frontend)
"""
from dataclasses import dataclass, field
from typing import Optional


# --- Shot Detection ----------------------------------------------------------

SHOT_WIDE = "wide"
SHOT_CLOSEUP = "closeup"
SHOT_BROLL = "b_roll"


@dataclass
class Shot:
    """A continuous camera angle / scene."""
    start_s: float
    end_s: float
    shot_type: str = SHOT_WIDE

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


# --- Face Tracker (MediaPipe) -----------------------------------------------

@dataclass
class FaceDetection:
    """Single face detected in one frame by MediaPipe."""
    face_x: float           # 0.0-1.0 normalized face center X
    face_y: float           # 0.0-1.0 normalized face center Y
    face_width: float       # 0.0-1.0 normalized face bbox width
    face_height: float      # 0.0-1.0 normalized face bbox height
    confidence: float       # Detection confidence 0.0-1.0
    person_x: float         # 0.0-1.0 estimated person center X (from pose or face)
    person_y: float         # 0.0-1.0 estimated person center Y
    person_height: float    # 0.0-1.0 estimated person height (face-based heuristic or pose)
    track_id: int = -1      # Stable tracking ID across frames (-1 = unassigned)


@dataclass
class Frame:
    """Analysis result for one sampled frame."""
    time_s: float
    shot_index: int
    faces: list[FaceDetection] = field(default_factory=list)


# --- Gemini Director (creative plan) ----------------------------------------

@dataclass
class SubjectInfo:
    """A subject identified by Gemini in the video."""
    id: str                 # "A", "B", "C" etc.
    position: str           # "left", "right", "center" — visual position in wide shots
    description: str        # Brief visual description


@dataclass
class FocusDirective:
    """One focus directive from Gemini's creative plan."""
    start_s: float
    end_s: float
    subject_id: str         # References SubjectInfo.id
    importance: str         # "high", "medium", "low"
    reason: str = ""


@dataclass
class DirectorPlan:
    """Complete output from Gemini video analysis."""
    content_type: str
    layout: str
    subjects: list[SubjectInfo] = field(default_factory=list)
    directives: list[FocusDirective] = field(default_factory=list)


# --- Focus Resolver (merged) ------------------------------------------------

@dataclass
class FocusPoint:
    """A single weighted focus target — input to path solver."""
    time_s: float
    x: float                # 0.0-1.0 normalized target center X
    y: float                # 0.0-1.0 normalized target center Y
    weight: float = 1.0     # Importance weight (higher = path solver prioritizes more)
    shot_index: int = 0
    subject_id: str = ""    # Gemini subject ID — used to detect person changes (hard cut)


# --- Path Solver (AutoFlip-style) -------------------------------------------

# Strategy constants
STRATEGY_STATIONARY = "stationary"
STRATEGY_PANNING = "panning"
STRATEGY_TRACKING = "tracking"


@dataclass
class PathPoint:
    """A single point on the smooth camera path."""
    time_s: float
    x: float                # 0.0-1.0 smooth crop center X
    y: float                # 0.0-1.0 smooth crop center Y
    subject_id: str = ""    # Gemini subject ID — used for hard cut detection in keyframe emitter


@dataclass
class ShotPath:
    """Smooth camera path for one shot."""
    shot_index: int
    strategy: str           # stationary / panning / tracking
    points: list[PathPoint] = field(default_factory=list)


# --- Final Output ------------------------------------------------------------

@dataclass
class ReframeKeyframe:
    """Keyframe sent to the frontend editor."""
    time_s: float
    offset_x: float         # Pixel offset from left edge of source
    offset_y: float         # Pixel offset from top edge of source
    interpolation: str      # "linear" or "hold"


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
