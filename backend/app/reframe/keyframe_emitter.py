"""
Keyframe uretimi — SmoothedPoint'leri frontend'in anlayacagi
pixel offset keyframe'lerine donusturur.

Hard cut: hold (eski poz) + linear (yeni poz) cifti.
Smooth:   sadece linear keyframe'ler.
Dedup:    < 5px degisim varsa keyframe uretilmez.
Clamp:    offset'ler asla video siniri disina cikamaz.
"""
import logging

from .config import ReframeConfig
from .types import ReframeKeyframe, ReframeResult, SmoothedPoint, Shot

logger = logging.getLogger(__name__)

# Ayni pozisyondaki ardisik keyframe'leri atlamak icin piksel esigi
_DEDUP_THRESHOLD_PX = 5.0


def emit_keyframes(
    smooth_points: list[SmoothedPoint],
    shots: list[Shot],
    src_w: int,
    src_h: int,
    fps: float,
    duration_s: float,
    config: ReframeConfig,
) -> ReframeResult:
    """
    Smoothed kamera pozisyonlarindan frontend keyframe'leri uret.
    """
    ar_w, ar_h = config.aspect_ratio
    crop_w = min(int(src_h * (ar_w / ar_h)), src_w)
    crop_h = src_h  # x_only: tam yukseklik

    frame_dur = 1.0 / fps if fps > 0 else 1.0 / 30.0

    logger.info(
        "[KeyframeEmitter] crop=%dx%d, src=%dx%d, mode=%s",
        crop_w, crop_h, src_w, src_h, config.tracking_mode,
    )

    keyframes: list[ReframeKeyframe] = []
    last_ox: float | None = None
    last_oy: float | None = None

    for sp in smooth_points:
        ox = _clamp(_to_offset_x(sp.center_x, src_w, crop_w), 0.0, src_w - crop_w)
        oy = 0.0
        if config.tracking_mode == "dynamic_xy":
            oy = _clamp(_to_offset_y(sp.center_y, src_h, crop_h), 0.0, src_h - crop_h)

        ox = round(ox, 1)
        oy = round(oy, 1)

        if sp.is_hard_cut and keyframes:
            # Hard cut: hold (onceki poz) + linear (yeni poz)
            hold_time = max(
                keyframes[-1].time_s + 0.001,
                sp.time_s - frame_dur,
            )
            keyframes.append(ReframeKeyframe(
                time_s=round(hold_time, 4),
                offset_x=last_ox if last_ox is not None else ox,
                offset_y=last_oy if last_oy is not None else oy,
                interpolation="hold",
            ))
            keyframes.append(ReframeKeyframe(
                time_s=round(sp.time_s, 4),
                offset_x=ox,
                offset_y=oy,
                interpolation="linear",
            ))

        elif last_ox is None:
            # Ilk keyframe
            keyframes.append(ReframeKeyframe(
                time_s=round(sp.time_s, 4),
                offset_x=ox,
                offset_y=oy,
                interpolation="linear",
            ))

        elif (abs(ox - last_ox) >= _DEDUP_THRESHOLD_PX
              or abs(oy - last_oy) >= _DEDUP_THRESHOLD_PX):
            # Anlamli pozisyon degisimi
            keyframes.append(ReframeKeyframe(
                time_s=round(sp.time_s, 4),
                offset_x=ox,
                offset_y=oy,
                interpolation="linear",
            ))

        else:
            # Ayni pozisyon, atla
            continue

        last_ox = ox
        last_oy = oy

    # Video bitisine son pozisyonu sabitle
    if keyframes and keyframes[-1].time_s < duration_s - frame_dur:
        keyframes.append(ReframeKeyframe(
            time_s=round(duration_s, 4),
            offset_x=keyframes[-1].offset_x,
            offset_y=keyframes[-1].offset_y,
            interpolation="linear",
        ))

    # Fallback: en az 1 keyframe (merkez crop)
    if not keyframes:
        center_ox = _clamp(_to_offset_x(0.5, src_w, crop_w), 0.0, src_w - crop_w)
        keyframes = [ReframeKeyframe(
            time_s=0.0,
            offset_x=round(center_ox, 1),
            offset_y=0.0,
            interpolation="linear",
        )]

    # Scene cut'lar = ilk shot haric tum shot baslangiclarinin zamanlari
    scene_cuts = [s.start_s for s in shots[1:]]

    for kf in keyframes:
        logger.info(
            "[KeyframeEmitter] KF t=%.3fs ox=%.1f oy=%.1f interp=%s",
            kf.time_s, kf.offset_x, kf.offset_y, kf.interpolation,
        )

    logger.info(
        "[KeyframeEmitter] %d keyframe, %d scene cut",
        len(keyframes), len(scene_cuts),
    )

    return ReframeResult(
        keyframes=keyframes,
        scene_cuts=scene_cuts,
        src_w=src_w,
        src_h=src_h,
        fps=fps,
        duration_s=duration_s,
        content_type="podcast",
        tracking_mode=config.tracking_mode,
        metadata={
            "crop_w": crop_w,
            "crop_h": crop_h,
            "total_shots": len(shots),
            "aspect_ratio": f"{ar_w}:{ar_h}",
        },
    )


# --- Koordinat donusumleri ----------------------------------------------------

def _to_offset_x(center_x_norm: float, src_w: int, crop_w: int) -> float:
    """Normalize merkez X → piksel offset (crop sol kenari)."""
    return center_x_norm * src_w - crop_w / 2


def _to_offset_y(center_y_norm: float, src_h: int, crop_h: int) -> float:
    """Normalize merkez Y → piksel offset (crop ust kenari)."""
    return center_y_norm * src_h - crop_h / 2


def _clamp(value: float, lo: float, hi: float) -> float:
    """Degeri [lo, hi] araligina kisitla."""
    if hi < lo:
        return lo
    return max(lo, min(hi, value))
