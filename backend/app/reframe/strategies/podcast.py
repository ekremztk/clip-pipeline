"""
Reframe V2 — Podcast/Interview Stratejisi

Podcast ve röportaj formatı için optimize edilmiş reframe stratejisi.

Özellikler:
- 2+ kişi genellikle sabit pozisyonlarda oturuyor
- Konuşmacı değişiminde SERT KESİM (hard cut)
- Pre-roll: konuşmacı sesi başlamadan 150ms önce kes
- Minimum segment süresi: 2 saniye (daha kısa geçiş yapılmaz)
- Büyük dead zone: kişi hafif hareket etse bile crop kıpırdamaz
- Tek kişili sahnelerde kişiyi takip et
"""
from .base import BaseStrategy
from ..models.types import (
    ReframeDecision,
    ReframeSegment,
    SceneAnalysis,
    SceneInterval,
    SmoothingConfig,
    SpeakerPersonMapping,
    TrackingMode,
    TransitionType,
)


class PodcastStrategy(BaseStrategy):
    """
    Podcast/Interview stratejisi.

    En yaygın kullanım senaryosu: iki kişinin karşılıklı konuştuğu
    video formatı. Konuşmacı değişiminde sert kesim yapılır.
    """

    def _default_config(self) -> SmoothingConfig:
        return SmoothingConfig(
            ema_alpha=0.15,               # Çok yumuşak — podcast sakin
            dead_zone_x=0.10,            # Geniş dead zone — crop titremez
            dead_zone_y=0.06,
            min_segment_duration_s=2.0,  # En az 2 saniye bir konuşmacıda kal
            min_speech_duration_s=1.5,   # 1.5s altı konuşma → geçiş yapma
            pre_roll_s=0.15,             # 150ms pre-roll
            max_pan_speed=0.20,
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
        Her sahne için reframe kararı üret.

        0 kişi → merkez crop
        1 kişi → kişiyi takip et (static ise sabit, hareket ediyorsa smooth)
        2+ kişi → konuşmacı timeline'a göre hard cut ile geçiş
        """
        from ..utils.coord_utils import compute_crop_width, clamp_crop_target

        crop_w = compute_crop_width(src_w, src_h, aspect_ratio)

        # Speaker ID → person_id lookup dict
        sp_to_person: dict[int, int] = {
            m.speaker_id: m.person_id for m in speaker_person_map
        }

        decisions: list[ReframeDecision] = []

        for sa in scene_analyses:
            scene = sa.scene

            if sa.person_count == 0:
                # Kimse tespit edilemedi → merkez crop
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="no_person_detected",
                )]

            elif sa.person_count == 1:
                # Tek kişi → kişiyi takip et
                traj = sa.trajectories[0]
                segments = self._single_person_segments(traj, scene, crop_w, src_w)

            else:
                # 2+ kişi → speaker timeline'a göre hard cut
                segments = self._multi_person_segments(
                    sa, speaker_timeline, sp_to_person, scene, crop_w, src_w
                )

            # Minimum segment süresi kuralını uygula
            segments = self._enforce_min_duration(segments)

            # Boş segment listesi kontrolü
            if not segments:
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="empty_segments_fallback",
                )]

            decisions.append(ReframeDecision(scene=scene, segments=segments))

        return decisions

    def _single_person_segments(
        self,
        trajectory,
        scene: SceneInterval,
        crop_w: int,
        src_w: int,
    ) -> list[ReframeSegment]:
        """
        Tek kişili sahne için segment üret.

        Kişi statikse → sabit crop (tek segment, NONE transition)
        Kişi hareket ediyorsa → trajectory pozisyonlarından segment listesi
        """
        from ..utils.coord_utils import clamp_crop_target

        if trajectory.is_static:
            target_x = clamp_crop_target(trajectory.mean_x, crop_w, src_w)
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=target_x,
                target_y=trajectory.mean_y,
                transition_in=TransitionType.NONE,
                focused_person_id=trajectory.person_id,
                reason="static_single_person",
            )]

        # Hareket eden kişi → pozisyon değişimlerinden segment oluştur
        positions = trajectory.positions  # (time_s, x, y)

        if len(positions) < 2:
            target_x = clamp_crop_target(trajectory.mean_x, crop_w, src_w)
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=target_x,
                target_y=trajectory.mean_y,
                transition_in=TransitionType.NONE,
                focused_person_id=trajectory.person_id,
                reason="single_position_fallback",
            )]

        segments: list[ReframeSegment] = []
        prev_x = clamp_crop_target(positions[0][1], crop_w, src_w)
        segment_start = scene.start_s

        for i in range(1, len(positions)):
            time_s, raw_x, raw_y = positions[i]
            curr_x = clamp_crop_target(raw_x, crop_w, src_w)

            # Dead zone kontrolü
            curr_x = self._apply_dead_zone(prev_x, curr_x, self.config.dead_zone_x)

            if abs(curr_x - prev_x) > self.config.dead_zone_x:
                segments.append(ReframeSegment(
                    start_s=segment_start,
                    end_s=time_s,
                    target_x=prev_x,
                    target_y=trajectory.mean_y,
                    transition_in=TransitionType.SMOOTH if segments else TransitionType.NONE,
                    focused_person_id=trajectory.person_id,
                    reason="person_tracking",
                ))
                segment_start = time_s
                prev_x = curr_x

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
                reason="person_tracking_final",
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
                reason="single_person_no_movement",
            )]

        return segments

    def _multi_person_segments(
        self,
        scene_analysis: SceneAnalysis,
        speaker_timeline: list[dict],
        sp_to_person: dict[int, int],
        scene: SceneInterval,
        crop_w: int,
        src_w: int,
    ) -> list[ReframeSegment]:
        """
        Çok kişili sahne — konuşmacı timeline'a göre hard cut ile geçiş.

        Algoritma:
        1. Bu sahne aralığındaki konuşmacı segmentlerini filtrele
        2. Her segment için konuşmacının kişisini bul (sp_to_person)
        3. O kişinin trajectory'sindeki ortalama X pozisyonunu kullan
        4. Segment başlangıcında pre_roll_s önce HARD_CUT yap
        5. Konuşmacılar arası sessizlikte → önceki pozisyonda kal
        """
        from ..utils.coord_utils import clamp_crop_target

        scene_speaker_segs = [
            s for s in speaker_timeline
            if s["end"] > scene.start_s and s["start"] < scene.end_s
        ]

        if not scene_speaker_segs:
            return self._visual_only_segments(scene_analysis, scene, crop_w, src_w)

        segments: list[ReframeSegment] = []
        prev_end = scene.start_s

        for i, sp_seg in enumerate(scene_speaker_segs):
            speaker_id = sp_seg.get("speaker_id", 0)
            person_id = sp_to_person.get(speaker_id)

            # Kişinin pozisyonunu bul
            target_x = 0.5  # Fallback: merkez
            if person_id is not None:
                traj = self._get_trajectory_for_person(scene_analysis, person_id)
                if traj is not None:
                    target_x = clamp_crop_target(traj.mean_x, crop_w, src_w)

            # Pre-roll: konuşma başlamadan pre_roll_s önce kes
            seg_start = max(
                prev_end,
                max(scene.start_s, sp_seg["start"] - self.config.pre_roll_s),
            )
            seg_end = min(scene.end_s, sp_seg["end"])

            if seg_end <= seg_start:
                continue

            transition = TransitionType.HARD_CUT if i > 0 else TransitionType.NONE

            segments.append(ReframeSegment(
                start_s=seg_start,
                end_s=seg_end,
                target_x=target_x,
                target_y=0.5,
                transition_in=transition,
                active_speaker_id=speaker_id,
                focused_person_id=person_id,
                reason="speaker_focus",
            ))
            prev_end = seg_end

        if not segments:
            return self._visual_only_segments(scene_analysis, scene, crop_w, src_w)

        # Sahne başında boşluk varsa ilk segmenti geri uzat
        if segments[0].start_s > scene.start_s:
            first = segments[0]
            segments[0] = ReframeSegment(
                start_s=scene.start_s,
                end_s=first.end_s,
                target_x=first.target_x,
                target_y=first.target_y,
                transition_in=TransitionType.NONE,
                active_speaker_id=first.active_speaker_id,
                focused_person_id=first.focused_person_id,
                reason=first.reason + "_prepended",
            )

        # Sahne sonunda boşluk varsa son segmenti öne uzat
        if segments[-1].end_s < scene.end_s:
            last = segments[-1]
            segments[-1] = ReframeSegment(
                start_s=last.start_s,
                end_s=scene.end_s,
                target_x=last.target_x,
                target_y=last.target_y,
                transition_in=last.transition_in,
                active_speaker_id=last.active_speaker_id,
                focused_person_id=last.focused_person_id,
                reason=last.reason + "_extended",
            )

        return segments

    def _visual_only_segments(
        self,
        scene_analysis: SceneAnalysis,
        scene: SceneInterval,
        crop_w: int,
        src_w: int,
    ) -> list[ReframeSegment]:
        """
        Diarization yoksa veya sahnede konuşmacı segmenti yoksa:
        En belirgin kişiye odaklan veya merkez crop yap.
        """
        from ..utils.coord_utils import clamp_crop_target

        if not scene_analysis.trajectories:
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=0.5,
                target_y=0.5,
                transition_in=TransitionType.NONE,
                reason="visual_only_no_person",
            )]

        if len(scene_analysis.trajectories) == 1:
            traj = scene_analysis.trajectories[0]
            target_x = clamp_crop_target(traj.mean_x, crop_w, src_w)
            return [ReframeSegment(
                start_s=scene.start_s,
                end_s=scene.end_s,
                target_x=target_x,
                target_y=traj.mean_y,
                transition_in=TransitionType.NONE,
                focused_person_id=traj.person_id,
                reason="visual_only_single",
            )]

        # Birden fazla kişi — ortalama X/Y
        avg_x = sum(t.mean_x for t in scene_analysis.trajectories) / len(scene_analysis.trajectories)
        avg_y = sum(t.mean_y for t in scene_analysis.trajectories) / len(scene_analysis.trajectories)
        target_x = clamp_crop_target(avg_x, crop_w, src_w)

        return [ReframeSegment(
            start_s=scene.start_s,
            end_s=scene.end_s,
            target_x=target_x,
            target_y=avg_y,
            transition_in=TransitionType.NONE,
            reason="visual_only_multi_avg",
        )]
