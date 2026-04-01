"""
Odak secimi — her frame icin kameranin nereye bakacagini belirler.

Karar hiyerarsisi:
  0 kisi  → onceki pozisyonu koru (shot basiysa merkez)
  1 kisi  → o kisiye odaklan (face_x/face_y if available)
  2+ kisi → Gemini decision varsa onu kullan, yoksa diarization fallback

Gemini persistence: bir Gemini karari, bir sonraki karara veya shot
sinirina kadar gecerli kalir (tolerance-based degil).

Hard cut: X mesafesi > threshold ise otomatik hard cut (whip pan onleme).
"""
import logging
from typing import Optional

from .config import FocusSelectionConfig, GeminiDirectorConfig
from .types import FocusPoint, FrameAnalysis, GeminiDecision, PersonDetection, Shot

logger = logging.getLogger(__name__)

# Default odak: frame merkezinin hafif ustu (headroom)
_DEFAULT_X = 0.5
_DEFAULT_Y = 0.4


def select_focus_points(
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
    shots: list[Shot],
    src_w: int,
    config: FocusSelectionConfig,
    video_path: Optional[str] = None,
    transcript_context: str = "",
    gemini_config: Optional[GeminiDirectorConfig] = None,
) -> list[FocusPoint]:
    """
    Frame analizleri + Gemini + diarization'dan her frame icin odak noktasi belirle.

    Priority: Gemini decision > diarization > largest person
    Gemini decisions persist until next decision or shot boundary.
    """
    if not frame_analyses:
        return []

    # 1. Cok kisa konusmaci segmentlerini filtrele
    filtered_diar = [
        s for s in diarization_segments
        if (s.get("end", 0) - s.get("start", 0)) >= config.min_speech_duration_s
    ]
    logger.info(
        "[FocusSelector] Diarization: %d segment, %d filtered (min=%.1fs)",
        len(diarization_segments), len(filtered_diar), config.min_speech_duration_s,
    )

    # 2. Konusmaci taraflarini ogren (ilk multi-person frame'den)
    speaker_sides = _learn_speaker_sides(frame_analyses, filtered_diar)
    logger.info("[FocusSelector] Speaker sides: %s", speaker_sides)

    # 3. Gemini semantic decisions (if enabled)
    gemini_timeline: list[GeminiDecision] = []
    if gemini_config and gemini_config.enabled and video_path:
        gemini_timeline = _run_gemini_director(
            frame_analyses, filtered_diar, shots, video_path,
            transcript_context, gemini_config,
        )

    # 4. Her frame icin odak noktasi belirle
    focus_points: list[FocusPoint] = []
    prev_shot_idx = -1
    prev_x = _DEFAULT_X
    prev_y = _DEFAULT_Y
    prev_speaker: Optional[int] = None

    for fa in frame_analyses:
        is_boundary = fa.shot_index != prev_shot_idx
        n_persons = len(fa.persons)

        # Konusmaci tespiti (pre-roll: look ahead)
        lookahead_t = fa.time_s + config.speaker_change_pre_roll_s
        active_speaker = _get_active_speaker(lookahead_t, filtered_diar)

        # Konusmaci degisimi mi?
        speaker_changed = (
            active_speaker is not None
            and prev_speaker is not None
            and active_speaker != prev_speaker
            and n_persons >= 2
        )

        if n_persons == 0:
            target_x = _DEFAULT_X if is_boundary else prev_x
            target_y = _DEFAULT_Y if is_boundary else prev_y
            reason = "no_person"

        elif n_persons == 1:
            p = fa.persons[0]
            target_x = p.framing_x
            target_y = _headroom_y(p)
            reason = "single_person"

        else:
            # 2+ persons: check persistent Gemini decision first
            gemini_decision = _get_active_gemini_decision(
                fa.time_s, fa.shot_index, gemini_timeline, shots,
            )
            if gemini_decision is not None:
                p = _pick_person_by_stable_id(fa.persons, gemini_decision.target_person_index)
                target_x = p.framing_x
                target_y = _headroom_y(p)
                reason = f"gemini:{gemini_decision.reason}"
            elif active_speaker is not None and active_speaker in speaker_sides:
                side = speaker_sides[active_speaker]
                p = _pick_person_on_side(fa.persons, side)
                target_x = p.framing_x
                target_y = _headroom_y(p)
                reason = f"speaker_{active_speaker}_{side}"
            else:
                # Fallback: en buyuk kisi
                p = max(fa.persons, key=lambda pp: pp.area)
                target_x = p.framing_x
                target_y = _headroom_y(p)
                reason = "largest_person"

        # Hard cut: shot boundary OR speaker change OR large X jump
        large_x_jump = abs(target_x - prev_x) > config.hard_cut_x_threshold
        is_hard_cut = is_boundary or speaker_changed or (large_x_jump and not is_boundary)

        focus_points.append(FocusPoint(
            time_s=fa.time_s,
            target_x=target_x,
            target_y=target_y,
            is_shot_boundary=is_hard_cut,
            reason=reason,
        ))

        prev_shot_idx = fa.shot_index
        prev_x = target_x
        prev_y = target_y
        if active_speaker is not None:
            prev_speaker = active_speaker

    # Log stats
    gemini_count = sum(1 for fp in focus_points if fp.reason.startswith("gemini:"))
    hard_cut_count = sum(1 for fp in focus_points if fp.is_shot_boundary)
    logger.info(
        "[FocusSelector] %d focus points (%d gemini, %d hard cuts)",
        len(focus_points), gemini_count, hard_cut_count,
    )
    return focus_points


# --- Gemini integration -------------------------------------------------------

def _run_gemini_director(
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
    shots: list[Shot],
    video_path: str,
    transcript_context: str,
    config: GeminiDirectorConfig,
) -> list[GeminiDecision]:
    """Run Gemini director pipeline, return sorted decision list."""
    try:
        from .gemini_director import (
            calculate_decision_points,
            build_annotated_frames,
            query_gemini_batch,
        )

        decision_points = calculate_decision_points(
            frame_analyses, diarization_segments, shots, config,
        )
        if not decision_points:
            return []

        annotated = build_annotated_frames(video_path, decision_points, config)
        decisions = query_gemini_batch(annotated, transcript_context, config)

        # Sort by time for segment-based lookup
        decisions.sort(key=lambda d: d.time_s)
        return decisions

    except Exception as e:
        logger.warning("[FocusSelector] Gemini director failed, using diarization-only: %s", e)
        return []


def _get_active_gemini_decision(
    time_s: float,
    shot_index: int,
    decisions: list[GeminiDecision],
    shots: list[Shot],
) -> Optional[GeminiDecision]:
    """
    Get the Gemini decision active at this time.
    A decision persists from its time_s until the NEXT decision or shot boundary.
    """
    if not decisions:
        return None

    # Find which shot this frame is in
    shot_start = 0.0
    shot_end = float("inf")
    if shot_index < len(shots):
        shot_start = shots[shot_index].start_s
        shot_end = shots[shot_index].end_s

    # Find the most recent decision that is in the same shot
    active: Optional[GeminiDecision] = None
    for d in decisions:
        if d.time_s > time_s:
            break  # Decisions are sorted — no need to look further
        # Only use decisions from the same shot
        if shot_start <= d.time_s < shot_end:
            active = d

    return active


def _pick_person_by_stable_id(
    persons: list[PersonDetection], stable_id: int,
) -> PersonDetection:
    """Find person by stable_id. Fallback to largest if not found."""
    for p in persons:
        if p.stable_id == stable_id:
            return p
    # Fallback: largest person
    return max(persons, key=lambda p: p.area)


# --- Speaker side learning ----------------------------------------------------

def _learn_speaker_sides(
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
) -> dict[int, str]:
    """
    Ilk multi-person frame'den konusmacilarin taraflarini ogren.
    Soldaki kisi = speaker_0, sagdaki = speaker_1.
    """
    if not diarization_segments:
        return {}

    unique_speakers = sorted(set(
        s.get("speaker", 0) for s in diarization_segments
    ))
    if len(unique_speakers) < 2:
        return {}

    for fa in frame_analyses:
        if len(fa.persons) >= 2:
            # Persons already sorted by X (stable_id order)
            sides: dict[int, str] = {}
            for i, spk in enumerate(unique_speakers):
                if i == 0:
                    sides[spk] = "left"
                elif i == 1:
                    sides[spk] = "right"
            return sides

    return {}


# --- Helpers ------------------------------------------------------------------

def _get_active_speaker(time_s: float, segments: list[dict]) -> Optional[int]:
    """Belirli zamanda aktif konusmaci. Yoksa son konusmaciya fallback."""
    last_speaker = None
    for seg in segments:
        if seg["start"] <= time_s <= seg["end"]:
            return seg.get("speaker", 0)
        if seg["end"] <= time_s:
            last_speaker = seg.get("speaker", 0)
    return last_speaker


def _pick_person_on_side(
    persons: list[PersonDetection], side: str,
) -> PersonDetection:
    """Belirli taraftaki kisileri filtrele, en buyugunu sec."""
    if side == "left":
        candidates = [p for p in persons if p.center_x < 0.5]
    else:
        candidates = [p for p in persons if p.center_x >= 0.5]

    if not candidates:
        candidates = persons

    return max(candidates, key=lambda p: p.area)


def _headroom_y(p: PersonDetection) -> float:
    """
    Kisi icin headroom uygulanmis Y hedefi.
    Face keypoint varsa onu kullan (daha dogru), yoksa bbox merkezinden kaydir.
    Hedef: yuz crop'un ust 1/3'inde olsun.
    """
    if p.face_y is not None:
        # Face Y is nose position — slight upward shift for headroom
        return p.face_y - p.bbox_height * 0.05
    # Fallback: bbox center shifted up more aggressively
    return p.center_y - p.bbox_height * 0.25
