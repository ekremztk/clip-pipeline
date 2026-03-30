"""
Reframe V2 — Gaming/Streaming Stratejisi

Oyun yayını videoları için optimize edilmiş strateji.

Bu format genellikle:
- Büyük bir oyun ekranı (ana içerik)
- Küçük bir webcam overlay (köşede yüz kamerası)

Reframe mantığı:
- Oyun ekranı varsa → sabit merkez crop (oyun ekranı zaten hareketli)
- Webcam overlay'i tespit et (küçük bbox, genellikle köşede)
- Webcam üzerindeki konuşmacı değişiminde geçiş yap
- Varsayılan: güvenli merkez crop (9:16 format için oyun görüntüsünü yakala)
"""
from .base import BaseStrategy
from ..models.types import (
    ReframeDecision,
    ReframeSegment,
    SceneAnalysis,
    SmoothingConfig,
    SpeakerPersonMapping,
    TransitionType,
)

# Webcam overlay tespiti için maksimum bbox alanı (normalize)
# Bu değerin altındaki bbox'lar webcam overlay olarak kabul edilir
WEBCAM_MAX_AREA = 0.15  # Frame'in %15'inden küçük = muhtemelen webcam


class GamingStrategy(BaseStrategy):
    """
    Gaming/Streaming stratejisi.

    Oyun yayınlarında ana içerik oyun ekranıdır.
    Kamera hareketi yerine sabit veya çok az hareketli crop tercih edilir.
    """

    def _default_config(self) -> SmoothingConfig:
        return SmoothingConfig(
            ema_alpha=0.10,               # Çok yumuşak — oyun ekranı istikrarlı
            dead_zone_x=0.15,            # Büyük dead zone — sakin görüntü
            dead_zone_y=0.10,
            min_segment_duration_s=3.0,  # Uzun minimum süre
            min_speech_duration_s=2.0,
            pre_roll_s=0.20,
            max_pan_speed=0.10,           # Çok yavaş pan
        )

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
        Gaming için sabit veya çok az hareketli crop üret.

        Webcam overlay varsa (küçük bbox) → webcam'e odaklan
        Yoksa → sabit merkez crop
        """
        decisions: list[ReframeDecision] = []

        for sa in scene_analyses:
            scene = sa.scene

            # Webcam overlay tespiti
            webcam_traj = self._find_webcam_trajectory(sa)

            if webcam_traj is not None:
                # Webcam bulundu → webcam pozisyonuna odaklan
                from ..utils.coord_utils import compute_crop_width, clamp_crop_target
                crop_w = compute_crop_width(src_w, src_h, aspect_ratio)
                target_x = clamp_crop_target(webcam_traj.mean_x, crop_w, src_w)

                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=target_x,
                    target_y=webcam_traj.mean_y,
                    transition_in=TransitionType.NONE,
                    focused_person_id=webcam_traj.person_id,
                    reason="gaming_webcam_focus",
                )]
            else:
                # Webcam yok veya oyun ekranı dominant → merkez crop
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="gaming_center_crop",
                )]

            decisions.append(ReframeDecision(scene=scene, segments=segments))

        return decisions

    def _find_webcam_trajectory(self, scene_analysis: SceneAnalysis):
        """
        Webcam overlay trajectory'sini tespit et.
        Webcam: küçük bbox alanı + genellikle köşede.
        Bulunamazsa None döndür.
        """
        if not scene_analysis.trajectories:
            return None

        webcam_candidates = []
        for traj in scene_analysis.trajectories:
            # Trajectory'nin ilk frame'indeki bbox alanını kontrol et
            if scene_analysis.frame_analyses:
                for fa in scene_analysis.frame_analyses:
                    for person in fa.persons:
                        if person.person_id == traj.person_id:
                            if person.bbox.area < WEBCAM_MAX_AREA:
                                webcam_candidates.append(traj)
                            break

        if not webcam_candidates:
            return None

        # En küçük alanlı kişiyi webcam olarak kabul et
        return webcam_candidates[0]
