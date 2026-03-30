"""
Reframe V2 — Temporal Smoothing

EMA (Exponential Moving Average) smoothing ve max pan speed limiti.

Bu modül yalnızca SMOOTH transition tipindeki hareketler için kullanılır.
HARD_CUT geçişlerinde smoothing UYGULANMAZ — sert kesim anında gerçekleşir.

Kullanım:
  smooth_positions() → ReframeSegment listesi oluşturulmadan önce
                        ham trajectory pozisyonlarını yumuşatmak için

Not: PodcastStrategy ve SingleSpeakerStrategy kendi içinde EMA uygular.
Bu modül daha kompleks multi-segment smoothing senaryoları için
genel amaçlı fonksiyonlar sağlar.
"""
from ..models.types import SmoothingConfig


def smooth_positions(
    positions: list[tuple[float, float]],  # [(time_s, x_norm), ...]
    config: SmoothingConfig,
) -> list[tuple[float, float]]:
    """
    EMA smoothing uygula — smooth geçişler için.

    Her adımda:
    1. EMA ile önceki pozisyona ağırlık ver
    2. Max pan speed limitini uygula (ani sıçramayı önle)

    Args:
        positions: [(time_s, target_x_norm)] listesi
        config: SmoothingConfig

    Returns:
        Yumuşatılmış [(time_s, smooth_x_norm)] listesi
    """
    if len(positions) <= 1:
        return list(positions)

    smoothed: list[tuple[float, float]] = [positions[0]]

    for i in range(1, len(positions)):
        time_s, raw_x = positions[i]
        prev_time, prev_x = smoothed[i - 1]

        # EMA
        smooth_x = config.ema_alpha * raw_x + (1.0 - config.ema_alpha) * prev_x

        # Max pan speed limiti
        dt = time_s - prev_time
        if dt > 0:
            max_delta = config.max_pan_speed * dt
            delta = smooth_x - prev_x
            if abs(delta) > max_delta:
                smooth_x = prev_x + max_delta * (1.0 if delta > 0 else -1.0)

        smoothed.append((time_s, smooth_x))

    return smoothed


def smooth_xy_positions(
    positions: list[tuple[float, float, float]],  # [(time_s, x, y), ...]
    config: SmoothingConfig,
) -> list[tuple[float, float, float]]:
    """
    X ve Y eksenlerini birlikte smooth et.
    dynamic_xy tracking modu için.
    """
    if len(positions) <= 1:
        return list(positions)

    smoothed: list[tuple[float, float, float]] = [positions[0]]

    for i in range(1, len(positions)):
        time_s, raw_x, raw_y = positions[i]
        prev_time, prev_x, prev_y = smoothed[i - 1]

        # EMA her iki eksen için
        smooth_x = config.ema_alpha * raw_x + (1.0 - config.ema_alpha) * prev_x
        smooth_y = config.ema_alpha * raw_y + (1.0 - config.ema_alpha) * prev_y

        # Max pan speed limiti (X için)
        dt = time_s - prev_time
        if dt > 0:
            max_delta_x = config.max_pan_speed * dt
            delta_x = smooth_x - prev_x
            if abs(delta_x) > max_delta_x:
                smooth_x = prev_x + max_delta_x * (1.0 if delta_x > 0 else -1.0)

            # Y ekseni için daha yavaş pan (dikey hareket daha rahatsız edici)
            max_delta_y = config.max_pan_speed * 0.5 * dt
            delta_y = smooth_y - prev_y
            if abs(delta_y) > max_delta_y:
                smooth_y = prev_y + max_delta_y * (1.0 if delta_y > 0 else -1.0)

        smoothed.append((time_s, smooth_x, smooth_y))

    return smoothed


def apply_dead_zone(
    current_x: float,
    target_x: float,
    dead_zone: float,
) -> float:
    """
    Dead zone uygula.
    Hedef mevcut pozisyondan dead_zone'dan az uzaksa hareket etme.
    """
    if abs(target_x - current_x) < dead_zone:
        return current_x
    return target_x
