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

    @property
    def area(self) -> float:
        return self.bbox_width * self.bbox_height


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
