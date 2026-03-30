"""
Reframe V2 — Keyframe Generator

ReframeDecision listesini frontend'e gönderilecek ReframeKeyframe listesine dönüştürür.
Bu, pipeline'ın son adımıdır — strateji kararları keyframe'e çevrilir.

Keyframe format:
  time_s       → Video içindeki mutlak zaman (saniye)
  offset_x     → Kaynak piksel cinsinden sol kenar X offset'i
  offset_y     → Kaynak piksel cinsinden üst kenar Y offset'i (x_only modda 0.0)
  interpolation → "linear" (yumuşak) veya "hold" (hard cut öncesi bekle)

Hard cut mekanizması:
  Konuşmacı A pozisyonunda beklerken konuşmacı B'ye hard cut yapılacaksa:
  1. Hold keyframe: t = (yeni_segment_başı - 1/fps) → A pozisyonu, interpolation="hold"
  2. Linear keyframe: t = yeni_segment_başı → B pozisyonu, interpolation="linear"
  Bu ikili, editörde "A'da dur → anında B'ye geç" davranışı oluşturur.
"""
from ..models.types import (
    ContentType,
    ReframeDecision,
    ReframeKeyframe,
    ReframeResult,
    SmoothingConfig,
    TrackingMode,
    TransitionType,
)
from ..utils.coord_utils import (
    compute_crop_width,
    compute_crop_height,
    normalize_x_to_offset,
    normalize_y_to_offset,
)


def generate_keyframes(
    decisions: list[ReframeDecision],
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    content_type: ContentType,
    tracking_mode: TrackingMode,
    aspect_ratio: tuple[int, int],
    config: SmoothingConfig,
) -> ReframeResult:
    """
    ReframeDecision listesinden nihai keyframe listesi üret.

    Args:
        decisions: Strateji katmanının ürettiği kararlar
        src_w, src_h: Kaynak video boyutları
        fps: Video frame rate
        duration_s: Video toplam süresi
        content_type: Tespit edilen içerik türü
        tracking_mode: X_ONLY veya DYNAMIC_XY
        aspect_ratio: Hedef aspect ratio (örn. (9, 16))
        config: Smoothing konfigürasyonu

    Returns:
        ReframeResult — keyframes, scene_cuts ve metadata içerir
    """
    crop_w = compute_crop_width(src_w, src_h, aspect_ratio)
    crop_h = compute_crop_height(src_w, src_h, aspect_ratio)
    frame_duration = 1.0 / fps if fps > 0 else 1.0 / 30.0

    keyframes: list[ReframeKeyframe] = []
    scene_cuts: list[float] = []

    for decision_idx, decision in enumerate(decisions):
        scene = decision.scene

        # İlk sahne hariç tüm sahne başlangıçları → scene cut marker
        if decision_idx > 0:
            scene_cuts.append(scene.start_s)

        for seg_idx, seg in enumerate(decision.segments):
            # Normalize X → piksel offset
            offset_x = normalize_x_to_offset(seg.target_x, src_w, crop_w)

            # Y offset (x_only modda daima 0.0)
            offset_y = 0.0
            if tracking_mode == TrackingMode.DYNAMIC_XY:
                offset_y = normalize_y_to_offset(seg.target_y, src_h, crop_h)

            if seg.transition_in == TransitionType.HARD_CUT and keyframes:
                # Hard cut: önceki pozisyonda hold keyframe yaz, sonra yeni pozisyon
                hold_time = max(
                    keyframes[-1].time_s + 0.001,
                    seg.start_s - frame_duration,
                )
                # Hold — önceki pozisyon değişmez
                keyframes.append(ReframeKeyframe(
                    time_s=round(hold_time, 4),
                    offset_x=keyframes[-1].offset_x,
                    offset_y=keyframes[-1].offset_y,
                    interpolation="hold",
                ))
                # Yeni pozisyon — anında geçiş
                keyframes.append(ReframeKeyframe(
                    time_s=round(seg.start_s, 4),
                    offset_x=round(offset_x, 2),
                    offset_y=round(offset_y, 2),
                    interpolation="linear",
                ))

            elif seg.transition_in == TransitionType.SMOOTH:
                # Smooth: doğrudan linear keyframe
                keyframes.append(ReframeKeyframe(
                    time_s=round(seg.start_s, 4),
                    offset_x=round(offset_x, 2),
                    offset_y=round(offset_y, 2),
                    interpolation="linear",
                ))

            else:
                # NONE: ilk segment veya pozisyon değişmez
                keyframes.append(ReframeKeyframe(
                    time_s=round(seg.start_s, 4),
                    offset_x=round(offset_x, 2),
                    offset_y=round(offset_y, 2),
                    interpolation="linear",
                ))

    # Duplicate ve gereksiz keyframe'leri temizle
    keyframes = _deduplicate_keyframes(keyframes)

    # Video bitişine son pozisyonu sabitle (eğer eksikse)
    if keyframes and keyframes[-1].time_s < duration_s - frame_duration:
        last = keyframes[-1]
        keyframes.append(ReframeKeyframe(
            time_s=round(duration_s, 4),
            offset_x=last.offset_x,
            offset_y=last.offset_y,
            interpolation="linear",
        ))

    total_segments = sum(len(d.segments) for d in decisions)

    print(
        f"[KeyframeGenerator] {len(decisions)} sahne, "
        f"{total_segments} segment → "
        f"{len(keyframes)} keyframe, {len(scene_cuts)} scene cut"
    )

    return ReframeResult(
        keyframes=keyframes,
        scene_cuts=scene_cuts,
        src_w=src_w,
        src_h=src_h,
        fps=fps,
        duration_s=duration_s,
        content_type=content_type,
        tracking_mode=tracking_mode,
        metadata={
            "total_scenes": len(decisions),
            "total_segments": total_segments,
            "crop_w": crop_w,
            "crop_h": crop_h,
            "aspect_ratio": f"{aspect_ratio[0]}:{aspect_ratio[1]}",
        },
    )


def _deduplicate_keyframes(
    keyframes: list[ReframeKeyframe],
) -> list[ReframeKeyframe]:
    """
    Gereksiz keyframe'leri temizle:
    - Aynı zaman ve aynı pozisyon → ilkini tut
    - Çok küçük pozisyon farkı (< 1px) ve aynı interpolation → ikincisini atla

    Hold keyframe'ler hiçbir zaman silinmez.
    """
    if not keyframes:
        return []

    deduped: list[ReframeKeyframe] = [keyframes[0]]

    for kf in keyframes[1:]:
        prev = deduped[-1]

        # Hold keyframe'leri her zaman koru
        if kf.interpolation == "hold" or prev.interpolation == "hold":
            deduped.append(kf)
            continue

        # Aynı zaman → atla
        if abs(kf.time_s - prev.time_s) < 0.001:
            continue

        # Çok küçük fark → atla (jitter önleme)
        if (
            abs(kf.offset_x - prev.offset_x) < 1.0
            and abs(kf.offset_y - prev.offset_y) < 1.0
            and kf.interpolation == prev.interpolation
        ):
            continue

        deduped.append(kf)

    return deduped
