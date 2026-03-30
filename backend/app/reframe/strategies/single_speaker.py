"""
Reframe V2 — Tek Konuşmacı Stratejisi

Vlog, sunum, eğitim videoları için optimize edilmiş strateji.

Özellikler:
- Tek kişiyi sahne boyunca takip et
- EMA smoothing ile yumuşak pan hareketi
- Kişi hareket ederse crop yavaşça takip eder
- Kişi statikse crop hiç hareket etmez
- Hard cut yok — her şey smooth transition
"""
from .base import BaseStrategy
from ..models.types import (
    ReframeDecision,
    ReframeSegment,
    SceneAnalysis,
    SmoothingConfig,
    SpeakerPersonMapping,
    TrackingMode,
    TransitionType,
)


class SingleSpeakerStrategy(BaseStrategy):
    """
    Tek konuşmacı stratejisi — vlog, sunum, eğitim formatı.
    Kişiyi smooth pan ile takip eder, hard cut yapmaz.
    """

    def _default_config(self) -> SmoothingConfig:
        return SmoothingConfig(
            ema_alpha=0.25,               # Orta yumuşaklık — hareketi takip et
            dead_zone_x=0.08,            # Orta dead zone
            dead_zone_y=0.05,
            min_segment_duration_s=1.5,  # Podcast'ten daha kısa — daha dinamik
            min_speech_duration_s=1.0,
            pre_roll_s=0.10,
            max_pan_speed=0.30,           # Hızlı harekete daha çabuk tepki
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
        Tek kişiyi sahne boyunca EMA smoothing ile takip et.
        Birden fazla kişi varsa en büyük bbox'lı kişiyi (ana konuşmacı) seç.
        """
        from ..utils.coord_utils import compute_crop_width, clamp_crop_target

        crop_w = compute_crop_width(src_w, src_h, aspect_ratio)
        decisions: list[ReframeDecision] = []

        for sa in scene_analyses:
            scene = sa.scene

            if not sa.trajectories:
                # Kimse yok → merkez crop
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="no_person",
                )]
            else:
                # En büyük ortalama Y'ye sahip kişi (tipik olarak en büyük bbox = ana kişi)
                # Aslında en büyük trajectory = en çok frame'de görünen
                main_traj = max(sa.trajectories, key=lambda t: len(t.positions))
                segments = self._track_person(main_traj, scene, crop_w, src_w, src_h)

            segments = self._enforce_min_duration(segments)

            if not segments:
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="empty_fallback",
                )]

            decisions.append(ReframeDecision(scene=scene, segments=segments))

        return decisions

    def _track_person(
        self,
        trajectory,
        scene,
        crop_w: int,
        src_w: int,
        src_h: int,
    ) -> list[ReframeSegment]:
        """
        Kişiyi EMA smoothing ile takip eden segment listesi üret.

        Her trajectory pozisyonu için:
        1. Dead zone kontrolü — küçük harekette crop kıpırdamaz
        2. EMA smoothing — ani harekette yavaş takip
        3. Max pan speed limiti — çok hızlı kayma olmasın
        """
        from ..utils.coord_utils import clamp_crop_target

        positions = trajectory.positions

        if not positions:
            target_x = clamp_crop_target(trajectory.mean_x, crop_w, src_w)
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=target_x,
                target_y=trajectory.mean_y,
                transition_in=TransitionType.NONE,
                focused_person_id=trajectory.person_id,
                reason="no_positions",
            )]

        if len(positions) == 1 or trajectory.is_static:
            target_x = clamp_crop_target(trajectory.mean_x, crop_w, src_w)
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=target_x,
                target_y=trajectory.mean_y,
                transition_in=TransitionType.NONE,
                focused_person_id=trajectory.person_id,
                reason="static_tracking",
            )]

        # EMA smoothing uygula
        smoothed_positions: list[tuple[float, float, float]] = []
        prev_x = clamp_crop_target(positions[0][1], crop_w, src_w)
        prev_y = positions[0][2]

        for i, (time_s, raw_x, raw_y) in enumerate(positions):
            clamped_x = clamp_crop_target(raw_x, crop_w, src_w)

            if i == 0:
                smoothed_x = clamped_x
                smoothed_y = raw_y
            else:
                # EMA
                smoothed_x = self._apply_ema(clamped_x, prev_x, self.config.ema_alpha)
                smoothed_y = self._apply_ema(raw_y, prev_y, self.config.ema_alpha)

                # Max pan speed limiti
                dt = time_s - positions[i - 1][0]
                if dt > 0:
                    max_delta = self.config.max_pan_speed * dt
                    delta_x = smoothed_x - prev_x
                    if abs(delta_x) > max_delta:
                        smoothed_x = prev_x + max_delta * (1 if delta_x > 0 else -1)

            smoothed_positions.append((time_s, smoothed_x, smoothed_y))
            prev_x = smoothed_x
            prev_y = smoothed_y

        # Smoothed pozisyonlardan segment oluştur
        segments: list[ReframeSegment] = []
        segment_start = scene.start_s
        prev_seg_x = smoothed_positions[0][1]

        for i in range(1, len(smoothed_positions)):
            time_s, curr_x, curr_y = smoothed_positions[i]

            # Dead zone kontrolü
            if abs(curr_x - prev_seg_x) > self.config.dead_zone_x:
                segments.append(ReframeSegment(
                    start_s=segment_start,
                    end_s=time_s,
                    target_x=prev_seg_x,
                    target_y=trajectory.mean_y,
                    transition_in=TransitionType.SMOOTH if segments else TransitionType.NONE,
                    focused_person_id=trajectory.person_id,
                    reason="smooth_tracking",
                ))
                segment_start = time_s
                prev_seg_x = curr_x

        # Son segment
        if segment_start < scene.end_s:
            final_x = clamp_crop_target(trajectory.mean_x, crop_w, src_w)
            segments.append(ReframeSegment(
                start_s=segment_start,
                end_s=scene.end_s,
                target_x=final_x,
                target_y=trajectory.mean_y,
                transition_in=TransitionType.SMOOTH if segments else TransitionType.NONE,
                focused_person_id=trajectory.person_id,
                reason="smooth_tracking_final",
            ))

        if not segments:
            target_x = clamp_crop_target(trajectory.mean_x, crop_w, src_w)
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=target_x,
                target_y=trajectory.mean_y,
                transition_in=TransitionType.NONE,
                focused_person_id=trajectory.person_id,
                reason="no_movement_detected",
            )]

        return segments
