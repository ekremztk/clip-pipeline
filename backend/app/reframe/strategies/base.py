"""
Reframe V2 — BaseStrategy

Tüm reframe stratejilerinin temel sınıfı.
Ortak davranışlar burada tanımlanır (dead zone, EMA, sınır kontrolü).
Türe özgü davranışlar alt sınıflarda override edilir.
"""
from abc import ABC, abstractmethod
from typing import Optional

from ..models.types import (
    ReframeDecision,
    SceneAnalysis,
    SmoothingConfig,
    SpeakerPersonMapping,
    TrackingMode,
)


class BaseStrategy(ABC):
    """
    Abstract base class for all reframe strategies.

    Alt sınıflar şunları implement etmeli:
    - _default_config(): Türe özgü SmoothingConfig değerleri
    - generate_decisions(): Ana karar üretim mantığı
    """

    def __init__(
        self,
        tracking_mode: TrackingMode = TrackingMode.X_ONLY,
        smoothing_config: Optional[SmoothingConfig] = None,
    ):
        self.tracking_mode = tracking_mode
        self.config = smoothing_config if smoothing_config is not None else self._default_config()

    @abstractmethod
    def _default_config(self) -> SmoothingConfig:
        """Türe özgü varsayılan smoothing ayarları."""
        ...

    @abstractmethod
    def generate_decisions(
        self,
        scene_analyses: list[SceneAnalysis],
        speaker_person_map: list[SpeakerPersonMapping],
        speaker_timeline: list[dict],
        src_w: int,
        src_h: int,
        aspect_ratio: tuple[int, int],
    ) -> list[ReframeDecision]:
        """
        Tüm sahneler için reframe kararlarını üret.

        Args:
            scene_analyses: Sahne analiz sonuçları (trajectories dahil)
            speaker_person_map: Konuşmacı → Kişi eşleştirmesi
            speaker_timeline: Temizlenmiş konuşmacı segmentleri
            src_w, src_h: Kaynak video boyutları
            aspect_ratio: Hedef aspect ratio (örn. (9, 16))

        Returns:
            Her sahne için bir ReframeDecision içeren liste.
        """
        ...

    # ─── Ortak Yardımcı Metodlar ──────────────────────────────────────────────

    def _apply_dead_zone(
        self,
        current_x: float,
        target_x: float,
        dead_zone: float,
    ) -> float:
        """
        Dead zone uygula: hedef mevcut pozisyondan dead_zone kadar
        uzakta değilse hareket etme.

        Bu sayede kişi hafif sallandığında crop titremez.
        Podcast'lerde büyük dead zone (0.10) → çok kararlı görüntü.
        """
        if abs(target_x - current_x) < dead_zone:
            return current_x  # Hareket etme
        return target_x

    def _apply_ema(
        self,
        current: float,
        previous: float,
        alpha: float,
    ) -> float:
        """
        Exponential Moving Average.
        alpha düşükse → daha yumuşak (geç tepki)
        alpha yüksekse → daha hızlı (hemen takip)
        """
        return alpha * current + (1.0 - alpha) * previous

    def _clamp_crop_x(
        self,
        target_x_norm: float,
        crop_w: int,
        src_w: int,
    ) -> float:
        """
        Crop hedef X'ini frame sınırları içinde tut.
        Kişi ekran kenarına yakınken crop frame dışına taşmaz.
        """
        half_crop_norm = (crop_w / 2.0) / src_w
        min_x = half_crop_norm
        max_x = 1.0 - half_crop_norm
        return max(min_x, min(max_x, target_x_norm))

    def _clamp_crop_y(
        self,
        target_y_norm: float,
        crop_h: int,
        src_h: int,
    ) -> float:
        """Crop hedef Y'yi frame sınırları içinde tut."""
        half_crop_norm = (crop_h / 2.0) / src_h
        min_y = half_crop_norm
        max_y = 1.0 - half_crop_norm
        return max(min_y, min(max_y, target_y_norm))

    def _get_trajectory_for_person(
        self,
        scene_analysis: SceneAnalysis,
        person_id: Optional[int],
    ):
        """Scene analysis'ten belirli bir kişinin trajectory'sini bul."""
        if person_id is None:
            return None
        for traj in scene_analysis.trajectories:
            if traj.person_id == person_id:
                return traj
        return None

    def _enforce_min_duration(
        self, segments: list
    ) -> list:
        """
        Minimum segment süresi kuralını uygula.
        min_segment_duration_s'den kısa segmentleri öncekiyle birleştir
        (önceki konuşmacı/kişi pozisyonunda kal).

        Bu kural çok kısa geçişleri ortadan kaldırır —
        profesyonel yapımlarda 2 saniyeden kısa shot olmaz.
        """
        from ..models.types import ReframeSegment

        if len(segments) <= 1:
            return segments

        merged: list[ReframeSegment] = [segments[0]]

        for seg in segments[1:]:
            duration = seg.end_s - seg.start_s
            if duration < self.config.min_segment_duration_s:
                # Önceki segmentin sonunu uzat (pozisyon değişmez)
                prev = merged[-1]
                merged[-1] = ReframeSegment(
                    start_s=prev.start_s,
                    end_s=seg.end_s,
                    target_x=prev.target_x,
                    target_y=prev.target_y,
                    transition_in=prev.transition_in,
                    active_speaker_id=prev.active_speaker_id,
                    focused_person_id=prev.focused_person_id,
                    reason=prev.reason + "_merged_short",
                )
            else:
                merged.append(seg)

        return merged
