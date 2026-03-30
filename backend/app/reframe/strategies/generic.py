"""
Reframe V2 — Generic/Fallback Stratejisi

Hiçbir spesifik içerik türüne uymayan veya sınıflandırılamayan
videolar için güvenli fallback stratejisi.

Mantık:
- Kişi varsa → en belirgin kişiyi smooth takip et
- Konuşmacı bilgisi varsa → konuşmacıya bak (ama soft transition)
- Yoksa → sabit merkez crop
- Her zaman güvenli çıktı garantisi
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


class GenericStrategy(BaseStrategy):
    """
    Generic fallback stratejisi.
    Kişi takibi yapar ama hard cut yerine smooth transition kullanır.
    Her durumda güvenli bir çıktı döndürür.
    """

    def _default_config(self) -> SmoothingConfig:
        return SmoothingConfig(
            ema_alpha=0.20,
            dead_zone_x=0.10,
            dead_zone_y=0.06,
            min_segment_duration_s=2.0,
            min_speech_duration_s=1.5,
            pre_roll_s=0.12,
            max_pan_speed=0.25,
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
        Her sahne için güvenli crop kararı üret.

        Kişi varsa → en belirgin kişiye odaklan (smooth)
        Diarization varsa → konuşmacıya bak (soft cut, hard cut değil)
        Kişi yoksa → merkez crop
        """
        from ..utils.coord_utils import compute_crop_width, clamp_crop_target

        crop_w = compute_crop_width(src_w, src_h, aspect_ratio)
        sp_to_person: dict[int, int] = {
            m.speaker_id: m.person_id for m in speaker_person_map
        }

        decisions: list[ReframeDecision] = []

        for sa in scene_analyses:
            scene = sa.scene

            if not sa.trajectories:
                # Kimse yok → merkez
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="generic_no_person",
                )]
            else:
                # Konuşmacı timeline'a bak
                scene_spk_segs = [
                    s for s in speaker_timeline
                    if s["end"] > scene.start_s and s["start"] < scene.end_s
                ]

                if scene_spk_segs and speaker_person_map:
                    segments = self._speaker_guided_segments(
                        sa, scene_spk_segs, sp_to_person, scene, crop_w, src_w
                    )
                else:
                    # Diarization yoksa → en belirgin kişiyi smooth takip et
                    main_traj = max(sa.trajectories, key=lambda t: len(t.positions))
                    target_x = clamp_crop_target(main_traj.mean_x, crop_w, src_w)
                    segments = [ReframeSegment(
                        start_s=scene.start_s,
                        end_s=scene.end_s,
                        target_x=target_x,
                        target_y=main_traj.mean_y,
                        transition_in=TransitionType.NONE,
                        focused_person_id=main_traj.person_id,
                        reason="generic_visual_focus",
                    )]

            segments = self._enforce_min_duration(segments)

            if not segments:
                segments = [ReframeSegment(
                    start_s=scene.start_s,
                    end_s=scene.end_s,
                    target_x=0.5,
                    target_y=0.5,
                    transition_in=TransitionType.NONE,
                    reason="generic_fallback",
                )]

            decisions.append(ReframeDecision(scene=scene, segments=segments))

        return decisions

    def _speaker_guided_segments(
        self,
        sa: SceneAnalysis,
        scene_spk_segs: list[dict],
        sp_to_person: dict[int, int],
        scene,
        crop_w: int,
        src_w: int,
    ) -> list[ReframeSegment]:
        """
        Konuşmacı bazlı segment üret — ama SMOOTH transition (hard cut değil).
        Generic modda keskin geçişler yerine yumuşak geçişler tercih edilir.
        """
        from ..utils.coord_utils import clamp_crop_target

        segments: list[ReframeSegment] = []
        prev_end = scene.start_s

        for i, sp_seg in enumerate(scene_spk_segs):
            speaker_id = sp_seg.get("speaker_id", 0)
            person_id = sp_to_person.get(speaker_id)

            target_x = 0.5
            if person_id is not None:
                traj = self._get_trajectory_for_person(sa, person_id)
                if traj:
                    target_x = clamp_crop_target(traj.mean_x, crop_w, src_w)

            seg_start = max(prev_end, max(scene.start_s, sp_seg["start"] - self.config.pre_roll_s))
            seg_end = min(scene.end_s, sp_seg["end"])

            if seg_end <= seg_start:
                continue

            # Generic'te SMOOTH transition (podcast'teki HARD_CUT yerine)
            transition = TransitionType.SMOOTH if i > 0 else TransitionType.NONE

            segments.append(ReframeSegment(
                start_s=seg_start,
                end_s=seg_end,
                target_x=target_x,
                target_y=0.5,
                transition_in=transition,
                active_speaker_id=speaker_id,
                focused_person_id=person_id,
                reason="generic_speaker",
            ))
            prev_end = seg_end

        if not segments:
            return []

        # Boşlukları doldur
        if segments[0].start_s > scene.start_s:
            first = segments[0]
            segments[0] = ReframeSegment(
                start_s=scene.start_s, end_s=first.end_s,
                target_x=first.target_x, target_y=first.target_y,
                transition_in=TransitionType.NONE,
                active_speaker_id=first.active_speaker_id,
                focused_person_id=first.focused_person_id,
                reason=first.reason + "_prepended",
            )

        if segments[-1].end_s < scene.end_s:
            last = segments[-1]
            segments[-1] = ReframeSegment(
                start_s=last.start_s, end_s=scene.end_s,
                target_x=last.target_x, target_y=last.target_y,
                transition_in=last.transition_in,
                active_speaker_id=last.active_speaker_id,
                focused_person_id=last.focused_person_id,
                reason=last.reason + "_extended",
            )

        return segments
