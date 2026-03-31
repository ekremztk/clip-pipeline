"""
Reframe V2 — Veri Tipleri

Tüm modüllerin paylaştığı ortak veri yapıları.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── Enum'lar ─────────────────────────────────────────────────────────────────

class ContentType(str, Enum):
    PODCAST = "podcast"           # 1-3 kişi, sabit kamera, konuşma ağırlıklı
    SINGLE_SPEAKER = "single"     # 1 kişi, hafif hareket, vlog/sunum
    GAMING = "gaming"             # Oyun ekranı + webcam overlay
    GENERIC = "generic"           # Hiçbirine uymuyorsa güvenli mod


class TrackingMode(str, Enum):
    X_ONLY = "x_only"             # Sadece yatay takip
    DYNAMIC_XY = "dynamic_xy"     # Yatay + dikey takip


class TransitionType(str, Enum):
    HARD_CUT = "hard_cut"         # Anında geçiş (konuşmacı değişimi)
    SMOOTH = "smooth"             # Yumuşak pan (kişi hareketi takibi)
    NONE = "none"                 # Pozisyon değişmez (ilk segment)


# ─── Temel Geometri ────────────────────────────────────────────────────────────

@dataclass
class BBox:
    """
    Normalize edilmiş bounding box (0.0 - 1.0 arası).
    x, y: sol üst köşe; w, h: genişlik ve yükseklik.
    """
    x: float
    y: float
    w: float
    h: float

    @property
    def center_x(self) -> float:
        return self.x + self.w / 2

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h

    def iou(self, other: "BBox") -> float:
        """Intersection over Union — frame'ler arası kişi eşleştirme için."""
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.w, other.x + other.w)
        y2 = min(self.y + self.h, other.y + other.h)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        intersection = (x2 - x1) * (y2 - y1)
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0


# ─── Kişi Tespiti ─────────────────────────────────────────────────────────────

@dataclass
class PersonDetection:
    """
    Tek bir frame'deki tek bir kişi tespiti.
    pose_keypoints: COCO 17 keypoint formatı — (x, y, conf) × 17.
    person_id: Sahne içi tracking ID (IoU eşleştirmesi sonrası atanır).
    """
    bbox: BBox
    confidence: float
    pose_keypoints: list[tuple[float, float, float]]  # (x, y, conf) × 17
    person_id: Optional[int] = None

    @property
    def head_center_x(self) -> float:
        """
        Kafa merkezi X — burun (idx 0), yoksa göz ortası, yoksa bbox merkezi.
        Crop hedefleme için bbox merkezinden daha doğru.
        """
        if len(self.pose_keypoints) > 0:
            nose = self.pose_keypoints[0]
            if nose[2] > 0.3:
                return nose[0]
        if len(self.pose_keypoints) > 2:
            left_eye = self.pose_keypoints[1]
            right_eye = self.pose_keypoints[2]
            if left_eye[2] > 0.3 and right_eye[2] > 0.3:
                return (left_eye[0] + right_eye[0]) / 2
        return self.bbox.center_x

    @property
    def head_center_y(self) -> float:
        """Kafa merkezi Y."""
        if len(self.pose_keypoints) > 0:
            nose = self.pose_keypoints[0]
            if nose[2] > 0.3:
                return nose[1]
        if len(self.pose_keypoints) > 2:
            left_eye = self.pose_keypoints[1]
            right_eye = self.pose_keypoints[2]
            if left_eye[2] > 0.3 and right_eye[2] > 0.3:
                return (left_eye[1] + right_eye[1]) / 2
        return self.bbox.center_y

    @property
    def is_frontal(self) -> bool:
        """Kişi kameraya dönük mü? İki göz de görünüyorsa frontal."""
        if len(self.pose_keypoints) > 2:
            left_eye = self.pose_keypoints[1]
            right_eye = self.pose_keypoints[2]
            return left_eye[2] > 0.3 and right_eye[2] > 0.3
        return False

    @property
    def facing_direction(self) -> str:
        """
        Kişinin baktığı yön: 'left', 'right', 'center'.
        Kulak görünürlüğüne göre belirlenir.
        Sadece sol kulak görünüyorsa sağa bakıyor (ve tersi).
        """
        if len(self.pose_keypoints) > 4:
            left_ear = self.pose_keypoints[3]
            right_ear = self.pose_keypoints[4]
            if left_ear[2] > 0.3 and right_ear[2] < 0.3:
                return "right"
            if right_ear[2] > 0.3 and left_ear[2] < 0.3:
                return "left"
        return "center"


# ─── Frame ve Trajectory ──────────────────────────────────────────────────────

@dataclass
class FrameAnalysis:
    """Tek bir frame'in YOLOv8 analiz sonucu."""
    time_s: float
    persons: list[PersonDetection]
    frame_index: int


@dataclass
class PersonTrajectory:
    """
    Bir kişinin sahne boyunca hareket yolu.
    positions: (time_s, center_x, center_y) tuple listesi — kafa merkezi kullanılır.
    """
    person_id: int
    positions: list[tuple[float, float, float]]  # (time_s, x, y)

    @property
    def mean_x(self) -> float:
        if not self.positions:
            return 0.5
        return sum(p[1] for p in self.positions) / len(self.positions)

    @property
    def mean_y(self) -> float:
        if not self.positions:
            return 0.5
        return sum(p[2] for p in self.positions) / len(self.positions)

    @property
    def x_range(self) -> float:
        """Yatay hareket miktarı (0-1 normalize). Trajectory boyunca max - min X."""
        if len(self.positions) < 2:
            return 0.0
        xs = [p[1] for p in self.positions]
        return max(xs) - min(xs)

    @property
    def is_static(self) -> bool:
        """
        Kişi yerinde mi duruyor?
        %5'ten az yatay hareket → statik sayılır.
        Podcast'lerde oturan kişiler statiktir.
        """
        return self.x_range < 0.05

    def position_at(self, time_s: float) -> tuple[float, float]:
        """
        Belirli bir zamandaki pozisyonu döndür.
        En yakın kayıtlı frame zamanını kullanır.
        """
        if not self.positions:
            return (0.5, 0.5)
        closest = min(self.positions, key=lambda p: abs(p[0] - time_s))
        return (closest[1], closest[2])


# ─── Sahne Analizi ────────────────────────────────────────────────────────────

@dataclass
class SceneInterval:
    """Bir sahne aralığı — FFmpeg scene detection çıktısı."""
    start_s: float
    end_s: float
    scene_type: str = "unknown"  # "wide", "closeup", "transition", "unknown"

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class SceneAnalysis:
    """
    Bir sahnenin tam analiz sonucu.
    frame_analyses: Her örneklenen frame'in sonucu.
    trajectories: Sahne boyunca kişi hareket yolları (IoU tracking ile).
    person_count: Sahnede tespit edilen unique kişi sayısı.
    """
    scene: SceneInterval
    frame_analyses: list[FrameAnalysis]
    trajectories: list[PersonTrajectory]
    person_count: int
    dominant_speaker_id: Optional[int] = None
    speaker_segments: list[dict] = field(default_factory=list)


# ─── Konuşmacı Eşleştirme ─────────────────────────────────────────────────────

@dataclass
class SpeakerPersonMapping:
    """
    Deepgram konuşmacı ID → YOLOv8 kişi ID eşleştirmesi.
    Pozisyon bazlı: soldaki kişi = küçük speaker_id (podcast konvansiyonu).
    """
    speaker_id: int           # Deepgram speaker ID (0, 1, ...)
    person_id: int            # YOLOv8 tracking ID
    confidence: float         # Eşleştirme güvenilirliği (0.0 - 1.0)
    avg_position_x: float     # Kişinin tüm sahnelerdeki ortalama X pozisyonu


# ─── Reframe Kararları ─────────────────────────────────────────────────────────

@dataclass
class ReframeSegment:
    """
    Reframe planındaki bir segment — kesintisiz bir crop pozisyonu bloğu.
    target_x, target_y: Normalize (0.0-1.0) crop merkez pozisyonu.
    transition_in: Bu segmente geçiş tipi.
    reason: Debug için açıklama.
    """
    start_s: float
    end_s: float
    target_x: float                     # Normalize crop merkezi X (0.0-1.0)
    target_y: float                     # Normalize crop merkezi Y (0.0-1.0)
    transition_in: TransitionType
    active_speaker_id: Optional[int] = None
    focused_person_id: Optional[int] = None
    reason: str = ""

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class ReframeDecision:
    """Bir sahne için reframe kararı — segment listesi içerir."""
    scene: SceneInterval
    segments: list[ReframeSegment]


# ─── Smoothing Konfigürasyonu ─────────────────────────────────────────────────

@dataclass
class SmoothingConfig:
    """
    Temporal smoothing parametreleri.
    İçerik türüne göre her strateji farklı varsayılan değerler kullanır.
    """
    ema_alpha: float = 0.2            # EMA katsayısı (düşük = daha yumuşak)
    dead_zone_x: float = 0.08         # Yatay dead zone (normalize)
    dead_zone_y: float = 0.05         # Dikey dead zone (normalize)
    min_segment_duration_s: float = 2.0   # Minimum segment süresi (saniye)
    min_speech_duration_s: float = 1.5   # Minimum konuşma süresi (geçiş için)
    pre_roll_s: float = 0.15          # Konuşmacı değişiminde önceden kesim
    max_pan_speed: float = 0.3        # Maksimum pan hızı (normalize/saniye)


# ─── Keyframe ve Sonuç ────────────────────────────────────────────────────────

@dataclass
class ReframeKeyframe:
    """
    Frontend'e gönderilecek tek bir keyframe.
    offset_x: Kaynak pixel cinsinden sol kenar X offset'i.
    offset_y: Kaynak pixel cinsinden üst kenar Y offset'i (x_only modda 0.0).
    interpolation: "linear" (yumuşak geçiş) veya "hold" (anında kesim öncesi).
    """
    time_s: float
    offset_x: float
    offset_y: float
    interpolation: str   # "linear" | "hold"


@dataclass
class ReframeResult:
    """
    Reframe pipeline'ının nihai çıktısı.
    keyframes: Timeline'a uygulanacak keyframe listesi.
    scene_cuts: Timeline marker olarak gösterilecek sahne kesim noktaları.
    metadata: Debug bilgileri (segment sayısı, sahne sayısı vb.).
    """
    keyframes: list[ReframeKeyframe]
    scene_cuts: list[float]
    src_w: int
    src_h: int
    fps: float
    duration_s: float
    content_type: ContentType
    tracking_mode: TrackingMode
    metadata: dict = field(default_factory=dict)
