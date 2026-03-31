"""
Reframe sistemi konfigurasyonu.
Tum parametreler burada. Hicbir modulde hardcoded deger yok.
"""
from dataclasses import dataclass, field


@dataclass
class ShotDetectionConfig:
    """FFmpeg sahne tespiti parametreleri"""
    threshold: float = 0.08          # FFmpeg scene filter threshold
    min_shot_duration_s: float = 0.3 # Bu sureden kisa shot'lari birlestir
    min_cut_gap_s: float = 0.5       # Bu kadar yakin kesimleri birlestir


@dataclass
class FrameAnalysisConfig:
    """YOLOv8 frame analizi parametreleri"""
    model_path: str = "yolov8s-pose.pt"  # Small model
    confidence_threshold: float = 0.40
    analysis_resolution: tuple[int, int] = (640, 360)  # Analiz icin kucultme
    sample_fps: float = 5.0              # Saniyede kac frame ornekle
    max_persons_per_frame: int = 4


@dataclass
class FocusSelectionConfig:
    """Odak secimi parametreleri"""
    min_speech_duration_s: float = 1.0   # Bu sureden kisa konusmada gecis yapma
    speaker_change_pre_roll_s: float = 0.15  # Konusmaci degisiminde pre-roll


@dataclass
class CameraPathConfig:
    """Kamera yolu ve smoothing parametreleri"""
    dead_zone_x: float = 0.05           # X ekseninde %5'ten az hareket -> kipirdama
    dead_zone_y: float = 0.04           # Y ekseninde %4'ten az hareket -> kipirdama
    smoothing_strength: float = 0.3      # EMA alpha (dusuk = daha yumusak)
    # AutoFlip'in stationary/tracking karari icin:
    motion_stability_threshold: float = 0.5  # Hareket bu oranin altindaysa -> stationary
    min_segment_duration_s: float = 1.5  # Bir pozisyonda minimum kalma suresi


@dataclass
class GeminiDirectorConfig:
    """Gemini semantic decision layer parameters"""
    enabled: bool = True
    model: str = ""  # Empty = use settings.GEMINI_MODEL_FLASH at runtime
    long_scene_check_interval_s: float = 4.0   # Check every N seconds in long scenes
    max_batch_size: int = 8                     # Max decision points per Gemini call
    annotation_resolution: tuple[int, int] = (640, 360)  # Frame size for annotation
    timeout_s: float = 15.0                     # Gemini API timeout


@dataclass
class ReframeConfig:
    """Ana konfigurasyon — tum alt config'leri barindirir"""
    shot_detection: ShotDetectionConfig = field(default_factory=ShotDetectionConfig)
    frame_analysis: FrameAnalysisConfig = field(default_factory=FrameAnalysisConfig)
    focus_selection: FocusSelectionConfig = field(default_factory=FocusSelectionConfig)
    camera_path: CameraPathConfig = field(default_factory=CameraPathConfig)
    gemini_director: GeminiDirectorConfig = field(default_factory=GeminiDirectorConfig)

    # Genel ayarlar
    aspect_ratio: tuple[int, int] = (9, 16)
    tracking_mode: str = "x_only"  # "x_only" veya "dynamic_xy"
