"""
Reframe sistemi veri tipleri.
Moduller arasi veri akisini bu tipler tanimlar.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Shot:
    """Bir sahne/shot — kesintisiz bir kamera acisi"""
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class PersonDetection:
    """Bir frame'deki bir kisi tespiti"""
    center_x: float      # 0.0-1.0 normalize
    center_y: float      # 0.0-1.0 normalize
    bbox_width: float    # 0.0-1.0 normalize
    bbox_height: float   # 0.0-1.0 normalize
    confidence: float
    face_x: Optional[float] = None   # Nose keypoint X (normalize), None if not detected
    face_y: Optional[float] = None   # Nose keypoint Y (normalize), None if not detected
    stable_id: int = -1              # Position-based ID within shot (0=leftmost, 1=next...)

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
    """Bir frame'in analiz sonucu"""
    time_s: float
    shot_index: int              # Bu frame hangi shot'a ait
    persons: list[PersonDetection] = field(default_factory=list)


@dataclass
class FocusPoint:
    """Bir frame icin belirlenmis odak noktasi"""
    time_s: float
    target_x: float              # Crop merkezinin hedefi (normalize 0-1)
    target_y: float              # Crop merkezinin hedefi (normalize 0-1)
    is_shot_boundary: bool       # Shot sinirinda mi? (hard cut gerekir)
    reason: str = ""             # Debug: neden bu pozisyon secildi


@dataclass
class SmoothedPoint:
    """Smoothing sonrasi crop pozisyonu"""
    time_s: float
    center_x: float
    center_y: float
    is_hard_cut: bool


@dataclass
class ReframeKeyframe:
    """Frontend'e gonderilecek keyframe"""
    time_s: float
    offset_x: float              # Pixel cinsinden
    offset_y: float              # Pixel cinsinden
    interpolation: str           # "linear" veya "hold"


@dataclass
class DecisionPoint:
    """A moment where Gemini should evaluate framing"""
    time_s: float
    trigger: str           # "shot_boundary", "speaker_change", "speech_start", "long_scene_check"
    shot_index: int
    persons: list[PersonDetection] = field(default_factory=list)
    active_speaker: Optional[int] = None


@dataclass
class GeminiDecision:
    """Gemini's framing decision for a decision point"""
    time_s: float
    target_person_index: int    # Which person to focus on (0-based index in persons list)
    reason: str                 # Why this person was chosen
    confidence: float = 1.0


@dataclass
class ReframeResult:
    """Pipeline'in nihai ciktisi"""
    keyframes: list[ReframeKeyframe] = field(default_factory=list)
    scene_cuts: list[float] = field(default_factory=list)
    src_w: int = 0
    src_h: int = 0
    fps: float = 30.0
    duration_s: float = 0.0
    content_type: str = "podcast"
    tracking_mode: str = "x_only"
    metadata: dict = field(default_factory=dict)
