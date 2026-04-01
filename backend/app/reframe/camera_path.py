"""
Kamera yolu hesaplama — ham odak noktalarini yumusak kamera hareketine donusturur.

Iki mod (shot bazli):
  Stationary: Tum focus noktalarinin ortalamasi, crop sabit.
  Tracking:   EMA smoothing + dead zone ile yumusak takip.

Shot sinirlari ve konusmaci degisimleri (is_shot_boundary=True)
smoothing'i keser → hard cut.

Min segment suresi: Birbirine cok yakin hard cut'lar (< 1.5s) bastirilir
(gercek shot sinirlari haric).
"""
import logging

from .config import CameraPathConfig
from .types import FocusPoint, Shot, SmoothedPoint

logger = logging.getLogger(__name__)


def compute_camera_path(
    focus_points: list[FocusPoint],
    shots: list[Shot],
    config: CameraPathConfig,
) -> list[SmoothedPoint]:
    """
    Ham odak noktalarindan yumusak kamera yolu hesapla.
    Shot sinirlari smoothing'i keser.
    """
    if not focus_points:
        return []

    # 1. Segmentlere bol (hard cut noktalarinda)
    segments = _split_at_hard_cuts(focus_points)

    # 2. Her segment icin stationary/tracking uygula
    raw_points: list[SmoothedPoint] = []
    for segment in segments:
        if not segment:
            continue
        smoothed = _smooth_segment(segment, config)
        raw_points.extend(smoothed)

    # 3. Min segment suresi: cok yakin hard cut'lari bastir
    result = _enforce_min_segment_duration(raw_points, shots, config.min_segment_duration_s)

    logger.info("[CameraPath] %d focus → %d smoothed point", len(focus_points), len(result))
    return result


# --- Segment bolme ------------------------------------------------------------

def _split_at_hard_cuts(focus_points: list[FocusPoint]) -> list[list[FocusPoint]]:
    """
    is_shot_boundary=True olan noktalarda segmentlere bol.
    Her segmentin ilk elemani hard cut noktasidir (ilk segment haric).
    """
    if not focus_points:
        return []

    segments: list[list[FocusPoint]] = [[]]
    for fp in focus_points:
        if fp.is_shot_boundary and segments[-1]:
            # Yeni segment baslat
            segments.append([fp])
        else:
            segments[-1].append(fp)

    return [s for s in segments if s]


# --- Per-segment smoothing ----------------------------------------------------

def _smooth_segment(
    segment: list[FocusPoint],
    config: CameraPathConfig,
) -> list[SmoothedPoint]:
    """
    Tek bir segment icin stationary/tracking mod sec ve uygula.
    Ilk eleman her zaman hard cut (segment baslangicindan dolayi).
    """
    if not segment:
        return []

    # Mod secimi: x_range'e bak
    xs = [fp.target_x for fp in segment]
    x_range = max(xs) - min(xs) if len(xs) > 1 else 0.0

    is_first_point = True

    if x_range < config.motion_stability_threshold:
        # --- STATIONARY: dominant position (most common X region) ---
        # Instead of simple average (which drifts between speakers),
        # use the median X to pick the dominant target
        sorted_xs = sorted(xs)
        median_x = sorted_xs[len(sorted_xs) // 2]
        # Select points near the median (within dead zone) for Y average
        nearby = [fp for fp in segment if abs(fp.target_x - median_x) < config.dead_zone_x * 2]
        if not nearby:
            nearby = segment
        dom_x = sum(fp.target_x for fp in nearby) / len(nearby)
        dom_y = sum(fp.target_y for fp in nearby) / len(nearby)

        result: list[SmoothedPoint] = []
        for fp in segment:
            result.append(SmoothedPoint(
                time_s=fp.time_s,
                center_x=dom_x,
                center_y=dom_y,
                is_hard_cut=fp.is_shot_boundary,
            ))
        return result

    # --- TRACKING: EMA smoothing + dead zone ---
    alpha = config.smoothing_strength
    result = []
    prev_x = segment[0].target_x
    prev_y = segment[0].target_y

    for fp in segment:
        if fp.is_shot_boundary:
            # Hard cut: direkt pozisyon, smoothing yok
            new_x = fp.target_x
            new_y = fp.target_y
        else:
            # Dead zone + EMA
            dx = abs(fp.target_x - prev_x)
            dy = abs(fp.target_y - prev_y)

            new_x = prev_x
            if dx >= config.dead_zone_x:
                new_x = alpha * fp.target_x + (1 - alpha) * prev_x

            new_y = prev_y
            if dy >= config.dead_zone_y:
                new_y = alpha * fp.target_y + (1 - alpha) * prev_y

        result.append(SmoothedPoint(
            time_s=fp.time_s,
            center_x=new_x,
            center_y=new_y,
            is_hard_cut=fp.is_shot_boundary,
        ))
        prev_x = new_x
        prev_y = new_y

    return result


# --- Min segment suresi -------------------------------------------------------

def _enforce_min_segment_duration(
    points: list[SmoothedPoint],
    shots: list[Shot],
    min_dur: float,
) -> list[SmoothedPoint]:
    """
    Birbirine cok yakin (< min_dur) hard cut'lari bastir.
    Gercek shot sinirlari (shot.start_s zamanindaki) BASILAMAZ.
    """
    if not points:
        return []

    # Gercek shot sinirlarini biliyoruz
    shot_starts = {round(s.start_s, 2) for s in shots}

    last_hard_cut_time = -999.0
    prev_x = points[0].center_x
    prev_y = points[0].center_y

    result: list[SmoothedPoint] = []
    for sp in points:
        if sp.is_hard_cut:
            # Gercek shot sinirinda mi?
            is_real_shot_boundary = any(
                abs(sp.time_s - t) < 0.15 for t in shot_starts
            )

            time_since = sp.time_s - last_hard_cut_time
            if not is_real_shot_boundary and time_since < min_dur:
                # Bastir: onceki pozisyonda kal, hard cut'i kaldir
                result.append(SmoothedPoint(
                    time_s=sp.time_s,
                    center_x=prev_x,
                    center_y=prev_y,
                    is_hard_cut=False,
                ))
                continue
            else:
                last_hard_cut_time = sp.time_s

        result.append(sp)
        prev_x = sp.center_x
        prev_y = sp.center_y

    return result
