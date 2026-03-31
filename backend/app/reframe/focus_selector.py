"""
Odak secimi — her frame icin kameranin nereye bakacagini belirler.

Karar hiyerarsisi:
  0 kisi  → onceki pozisyonu koru (shot basiysa merkez)
  1 kisi  → o kisiye odaklan
  2+ kisi → diarization'dan aktif konusmacinin tarafindaki kisiye odaklan

Konusmaci degisimlerinde pre-roll (150ms once) ve hard cut uygulanir.
"""
import logging
from typing import Optional

from .config import FocusSelectionConfig
from .types import FocusPoint, FrameAnalysis, PersonDetection, Shot

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
) -> list[FocusPoint]:
    """
    Frame analizleri + diarization'dan her frame icin odak noktasi belirle.
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

    # 3. Her frame icin odak noktasi belirle
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

        # Konusmaci degisimi mi? (hard cut gerekir)
        speaker_changed = (
            active_speaker is not None
            and prev_speaker is not None
            and active_speaker != prev_speaker
            and n_persons >= 2
        )
        is_hard_cut = is_boundary or speaker_changed

        if n_persons == 0:
            target_x = _DEFAULT_X if is_boundary else prev_x
            target_y = _DEFAULT_Y if is_boundary else prev_y
            reason = "no_person"

        elif n_persons == 1:
            p = fa.persons[0]
            target_x = p.center_x
            target_y = _headroom_y(p)
            reason = "single_person"

        else:
            # 2+ kisi: konusmacinin tarafindaki kisiye odaklan
            if active_speaker is not None and active_speaker in speaker_sides:
                side = speaker_sides[active_speaker]
                p = _pick_person_on_side(fa.persons, side)
                target_x = p.center_x
                target_y = _headroom_y(p)
                reason = f"speaker_{active_speaker}_{side}"
            else:
                # Fallback: en buyuk kisi
                p = max(fa.persons, key=lambda pp: pp.area)
                target_x = p.center_x
                target_y = _headroom_y(p)
                reason = "largest_person"

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

    logger.info("[FocusSelector] %d focus point uretildi", len(focus_points))
    return focus_points


# --- Speaker side learning ----------------------------------------------------

def _learn_speaker_sides(
    frame_analyses: list[FrameAnalysis],
    diarization_segments: list[dict],
) -> dict[int, str]:
    """
    Ilk multi-person frame'den konusmacilarin taraflarini ogren.
    Soldaki kisi = speaker_0, sagdaki = speaker_1.

    Diarization yoksa bos dict doner (tum kararlar gorsel-bazli olur).
    """
    if not diarization_segments:
        return {}

    # Unique konusmacilari bul
    unique_speakers = sorted(set(
        s.get("speaker", 0) for s in diarization_segments
    ))
    if len(unique_speakers) < 2:
        return {}

    # Ilk 2+ kisi olan frame'i bul
    for fa in frame_analyses:
        if len(fa.persons) >= 2:
            # X'e gore sirala (soldan saga)
            sorted_persons = sorted(fa.persons, key=lambda p: p.center_x)
            sides: dict[int, str] = {}
            for i, spk in enumerate(unique_speakers):
                if i == 0:
                    sides[spk] = "left"
                elif i == 1:
                    sides[spk] = "right"
                # 3+ konusmaci: sadece ilk 2'si atanir
            return sides

    return {}


# --- Yardimcilar -------------------------------------------------------------

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
    """
    Belirli taraftaki kisileri filtrele, en buyugunu sec.
    Tarafta kimse yoksa en buyuk kisiyi dondur.
    """
    if side == "left":
        candidates = [p for p in persons if p.center_x < 0.5]
    else:
        candidates = [p for p in persons if p.center_x >= 0.5]

    if not candidates:
        candidates = persons  # Tarafta kimse yok, hepsine bak

    return max(candidates, key=lambda p: p.area)


def _headroom_y(p: PersonDetection) -> float:
    """
    Kisi icin headroom uygulanmis Y hedefi.
    Bbox merkezini hafif yukari kaydir → yuz crop'un ust 1/3'unde olur.
    """
    return p.center_y - p.bbox_height * 0.15
