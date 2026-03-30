"""
Reframe V2 — Konuşmacı-Kişi Eşleştirme

Deepgram diarization verisindeki konuşmacıları (speaker 0, 1, ...)
YOLOv8'in tespit ettiği kişilerle eşleştirir.

Strateji: Pozisyon bazlı eşleştirme.
  - Tüm sahnelerdeki kişilerin ortalama X pozisyonları hesaplanır
  - Kişiler soldan sağa sıralanır
  - Konuşmacılar ID sırasına göre (0, 1, 2...) bu kişilere atanır
  - Podcast düzeninde: solda HOST (speaker 0), sağda GUEST (speaker 1)

Bu basit heuristic bile mevcut sistemden 10x daha iyi çünkü:
  Eski sistem → sadece zaman overlap'i, kişi-konuşmacı bağlantısı yok
  Yeni sistem → her konuşmacı segmenti için doğru kişi pozisyonu belirlenir
"""
from ..models.types import (
    SceneAnalysis,
    SpeakerPersonMapping,
)


def match_speakers_to_persons(
    scene_analyses: list[SceneAnalysis],
    diarization_segments: list[dict],
    src_w: int,
) -> list[SpeakerPersonMapping]:
    """
    Konuşmacıları tespit edilen kişilerle eşleştir.

    Algoritma:
    1. Diarization segmentlerinden unique konuşmacıları bul
    2. Tüm sahnelerdeki kişi trajectory'lerinden global ortalama X hesapla
    3. Kişileri soldan sağa sırala
    4. Konuşmacıları (küçük ID'den büyüğe) sırayla kişilere ata
    5. Güvenilirlik skoru: kişi sayısı == konuşmacı sayısı → 0.90, değilse → 0.60

    Returns:
        SpeakerPersonMapping listesi. Diarization veya person yoksa boş liste.
    """
    if not diarization_segments or not scene_analyses:
        return []

    # Unique konuşmacı ID'lerini bul (sıralı)
    unique_speakers = sorted(set(
        seg.get("speaker", 0) for seg in diarization_segments
        if seg.get("speaker") is not None
    ))

    if not unique_speakers:
        return []

    # Tüm sahnelerdeki kişilerin global ortalama X pozisyonlarını hesapla
    # person_id → [mean_x değerleri]
    global_person_xs: dict[int, list[float]] = {}

    for sa in scene_analyses:
        for traj in sa.trajectories:
            pid = traj.person_id
            if pid not in global_person_xs:
                global_person_xs[pid] = []
            global_person_xs[pid].append(traj.mean_x)

    if not global_person_xs:
        return []

    # Her kişinin global ortalama X pozisyonu
    person_avg_x: dict[int, float] = {
        pid: sum(xs) / len(xs)
        for pid, xs in global_person_xs.items()
    }

    # Kişileri soldan sağa sırala (küçük X = solda)
    sorted_persons = sorted(person_avg_x.items(), key=lambda item: item[1])

    # Eşleştirme güvenilirliği:
    # Kişi sayısı tam olarak konuşmacı sayısına eşitse → yüksek güven
    confidence = 0.90 if len(unique_speakers) == len(sorted_persons) else 0.60

    mappings: list[SpeakerPersonMapping] = []
    for i, speaker_id in enumerate(unique_speakers):
        if i >= len(sorted_persons):
            break  # Fazla konuşmacı var, eşleştirilecek kişi kalmadı
        person_id, avg_x = sorted_persons[i]
        mappings.append(SpeakerPersonMapping(
            speaker_id=speaker_id,
            person_id=person_id,
            confidence=confidence,
            avg_position_x=avg_x,
        ))

    print(
        f"[SpeakerAnalyzer] {len(unique_speakers)} konuşmacı, "
        f"{len(sorted_persons)} kişi → {len(mappings)} eşleşme "
        f"(güven: {confidence:.2f})"
    )
    return mappings


def build_speaker_timeline(
    diarization_segments: list[dict],
    speaker_person_map: list[SpeakerPersonMapping],
    min_speech_duration_s: float = 1.5,
    min_segment_gap_s: float = 0.3,
) -> list[dict]:
    """
    Diarization segmentlerinden temizlenmiş konuşmacı timeline'ı oluştur.

    Kurallar:
    - min_speech_duration_s'den kısa segmentleri filtrele (çok kısa konuşmalar)
    - Aynı konuşmacının ardışık ve yakın segmentlerini birleştir
    - Speaker ID → Person ID eşleştirmesini uygula

    Returns:
        dict listesi: {"start", "end", "speaker_id", "person_id"}
    """
    if not diarization_segments:
        return []

    # Speaker → Person ID mapping dict
    sp_map: dict[int, int] = {m.speaker_id: m.person_id for m in speaker_person_map}

    # Adım 1: Çok kısa segmentleri filtrele
    filtered: list[dict] = []
    for seg in diarization_segments:
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        speaker_id = seg.get("speaker", 0)
        duration = end - start
        if duration >= min_speech_duration_s:
            filtered.append({
                "start": float(start),
                "end": float(end),
                "speaker_id": int(speaker_id),
                "person_id": sp_map.get(int(speaker_id)),
            })

    if not filtered:
        return []

    # Adım 2: Aynı konuşmacının ardışık segmentlerini birleştir
    # (aralarındaki boşluk min_segment_gap_s'den azsa)
    merged: list[dict] = [dict(filtered[0])]
    for seg in filtered[1:]:
        prev = merged[-1]
        same_speaker = prev["speaker_id"] == seg["speaker_id"]
        small_gap = (seg["start"] - prev["end"]) < min_segment_gap_s
        if same_speaker and small_gap:
            merged[-1]["end"] = seg["end"]
        else:
            merged.append(dict(seg))

    print(f"[SpeakerAnalyzer] Timeline: {len(diarization_segments)} segment → {len(merged)} birleştirilmiş")
    return merged


def get_active_speaker_at(
    time_s: float,
    speaker_timeline: list[dict],
    fallback_to_last: bool = True,
) -> int | None:
    """
    Belirli bir zamanda aktif konuşmacıyı bul.

    Args:
        time_s: Sorgulanacak zaman (saniye)
        speaker_timeline: build_speaker_timeline() çıktısı
        fallback_to_last: True ise zaman aralığında konuşmacı yoksa
                          önceki konuşmacıyı döndür (sessizlik = önceki kişide kal)

    Returns:
        speaker_id veya None (hiç konuşmacı bulunamazsa)
    """
    if not speaker_timeline:
        return None

    # Aktif segmenti bul
    for seg in speaker_timeline:
        if seg["start"] <= time_s <= seg["end"]:
            return seg["speaker_id"]

    if not fallback_to_last:
        return None

    # Zaman aralığında konuşmacı yok → en yakın önceki konuşmacıyı döndür
    past_segments = [s for s in speaker_timeline if s["end"] <= time_s]
    if past_segments:
        return past_segments[-1]["speaker_id"]

    # Hiç geçmiş segment yok → gelecekteki ilk konuşmacıyı döndür
    future_segments = [s for s in speaker_timeline if s["start"] > time_s]
    if future_segments:
        return future_segments[0]["speaker_id"]

    return None


def get_person_id_for_speaker(
    speaker_id: int,
    speaker_person_map: list[SpeakerPersonMapping],
) -> int | None:
    """Speaker ID'ye karşılık gelen person ID'yi döndür."""
    for mapping in speaker_person_map:
        if mapping.speaker_id == speaker_id:
            return mapping.person_id
    return None
