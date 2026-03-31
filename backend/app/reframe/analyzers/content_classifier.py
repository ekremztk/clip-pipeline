"""
Reframe V2 — İçerik Türü Otomatik Sınıflandırma

Analiz sonuçlarına bakarak videonun hangi türde olduğunu otomatik tespit eder.
Kullanıcı açıkça bir tür belirtmişse otomatik tespit atlanır.

İçerik Türleri:
  PODCAST     — 1-3 kişi, sabit kamera, konuşma ağırlıklı (en yaygın)
  SINGLE      — 1 kişi, hafif hareket, vlog/sunum/eğitim
  GAMING      — Oyun ekranı + küçük webcam overlay
  GENERIC     — Hiçbirine uymadığında güvenli merkez-crop modu
"""
from ..models.types import ContentType, SceneAnalysis


def classify_content(
    scene_analyses: list[SceneAnalysis],
    diarization_segments: list[dict],
    user_hint: str | None = None,
) -> ContentType:
    """
    Video içerik türünü belirle.

    Öncelik sırası:
    1. Kullanıcı hint vermişse → doğrudan kullan
    2. Analiz verisi yoksa → GENERIC
    3. İstatistiklere göre karar ağacı uygula

    Karar ağacı:
      avg_persons >= 1.5 AND az hareket AND uzun sahneler → PODCAST
      avg_persons <= 1.2 AND az-orta hareket               → SINGLE_SPEAKER
      az kişi (küçük webcam) AND çok hareket               → GAMING
      Diğer                                                 → GENERIC
    """
    # Kullanıcı hint'i → doğrudan kullan
    if user_hint and user_hint.lower() not in ("auto", ""):
        try:
            content_type = ContentType(user_hint.lower())
            print(f"[ContentClassifier] Kullanıcı seçimi: {content_type.value}")
            return content_type
        except ValueError:
            print(f"[ContentClassifier] Geçersiz hint '{user_hint}' — otomatik tespite devam")

    if not scene_analyses:
        print("[ContentClassifier] Analiz verisi yok — GENERIC")
        return ContentType.GENERIC

    # İstatistikleri hesapla
    movement_values: list[float] = []
    scene_durations: list[float] = []

    for sa in scene_analyses:
        scene_durations.append(sa.scene.duration_s)
        for traj in sa.trajectories:
            movement_values.append(traj.x_range)

    # avg_persons: diarization speaker sayısını kullan (trajectory fragmentasyonundan etkilenmez)
    # Fallback: scene trajectory ortalaması
    num_speakers = len(set(
        seg.get("speaker", 0) for seg in diarization_segments
        if seg.get("speaker") is not None
    )) if diarization_segments else 0

    if num_speakers > 0:
        avg_persons = float(num_speakers)
    else:
        # Diarization yoksa scene'lerdeki benzersiz trajectory sayılarını kullan
        person_counts = [sa.person_count for sa in scene_analyses]
        avg_persons = sum(person_counts) / len(person_counts) if person_counts else 0.0
    avg_movement = sum(movement_values) / len(movement_values) if movement_values else 0.0
    avg_scene_duration = sum(scene_durations) / len(scene_durations) if scene_durations else 0.0

    print(
        f"[ContentClassifier] avg_persons={avg_persons:.2f}, "
        f"avg_movement={avg_movement:.3f}, "
        f"avg_scene_dur={avg_scene_duration:.1f}s, "
        f"num_speakers={num_speakers}"
    )

    # ─── Karar Ağacı ──────────────────────────────────────────────────────────

    # PODCAST: birden fazla kişi, az hareket, uzun sahneler
    # (sabit kamera, oturarak konuşma formatı)
    if (
        avg_persons >= 1.5
        and avg_movement < 0.10
        and avg_scene_duration > 3.0
    ):
        print("[ContentClassifier] → PODCAST")
        return ContentType.PODCAST

    # Diarization 2+ konuşmacı gösteriyorsa ve kişi var → PODCAST
    if num_speakers >= 2 and avg_persons >= 1.0 and avg_movement < 0.15:
        print("[ContentClassifier] → PODCAST (diarization bazlı)")
        return ContentType.PODCAST

    # SINGLE_SPEAKER: tek kişi, az veya orta hareket
    if avg_persons <= 1.2 and avg_movement < 0.15:
        print("[ContentClassifier] → SINGLE_SPEAKER")
        return ContentType.SINGLE_SPEAKER

    # GAMING: çok az veya hiç kişi YOK (küçük webcam), çok hareket
    # (oyun ekranı = büyük hareket, webcam = küçük bbox → person filter onu kesiyor)
    if avg_persons <= 0.5 and avg_movement > 0.20:
        print("[ContentClassifier] → GAMING")
        return ContentType.GAMING

    # GENERIC: diğer tüm durumlar
    print("[ContentClassifier] → GENERIC")
    return ContentType.GENERIC
