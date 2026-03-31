"""
Reframe V2 — Sahne Tespiti

FFmpeg scene filter + SSIM doğrulama ile sahne geçişlerini tespit eder.

Mevcut sistemden farklar:
- SSIM ile yanlış pozitif temizleme (el hareketi, ışık değişimi gibi durumlar)
- İçerik türüne göre ayarlanabilir threshold (podcast daha hassas, gaming daha gevşek)
- Minimum sahne süresi filtresi (0.5s altını birleştir)
- Birden fazla doğrulama katmanı
"""
import re
import subprocess
from typing import Optional

import cv2
import numpy as np

from ..models.types import SceneInterval


# ─── Sabitler ─────────────────────────────────────────────────────────────────

# İçerik türüne göre varsayılan scene threshold değerleri
DEFAULT_THRESHOLDS: dict[str, float] = {
    "podcast": 0.08,    # Stüdyo ortamı: düşük eşik = daha hassas tespit
    "gaming": 0.25,     # Oyun ekranı sürekli değişir: yüksek eşik = daha az kesim
    "single": 0.12,     # Tek kişi: orta eşik
    "generic": 0.10,    # Genel fallback
}

MIN_SCENE_DURATION_S = 0.5      # Bu süreden kısa sahneleri öncekiyle birleştir
MIN_CUT_GAP_S = 0.5             # Bu süreden yakın kesimleri tek kesim say
SSIM_HARD_CUT_THRESHOLD = 0.75  # SSIM bu değerin altında → kesin sahne geçişi
SSIM_SOFT_CUT_THRESHOLD = 0.92  # Bu aralıkta → geniş bağlamla doğrula
SKIP_OPENING_S = 0.5            # İlk 0.5 saniyeyi atla (açılış artefaktları)


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def detect_scenes(
    video_path: str,
    threshold: Optional[float] = None,
    content_hint: str = "generic",
    fps: float = 30.0,
) -> list[SceneInterval]:
    """
    Video dosyasındaki sahne geçişlerini tespit et.

    Adımlar:
    1. FFmpeg scene filter ile aday kesim noktaları bul
    2. SSIM ile doğrula (yanlış pozitifleri temizle)
    3. Çok yakın kesimleri birleştir
    4. Sahne aralıklarını oluştur
    5. Çok kısa sahneleri birleştir

    Returns:
        SceneInterval listesi — video başından sonuna kadar tüm sahneler.
        Hiçbir sahne tespit edilemezse tüm video tek sahne olarak döner.
    """
    try:
        if threshold is None:
            threshold = DEFAULT_THRESHOLDS.get(content_hint, 0.10)

        duration = _get_duration(video_path)
        if duration <= 0:
            return [SceneInterval(start_s=0.0, end_s=0.0)]

        # Adım 1: FFmpeg scene detection
        cut_times = _ffmpeg_scene_detect(video_path, threshold)
        print(f"[SceneAnalyzer] FFmpeg ham kesim sayısı: {len(cut_times)}")

        # Açılış bölgesini atla
        cut_times = [t for t in cut_times if t >= SKIP_OPENING_S]

        # Adım 2: SSIM doğrulama (eğer aday kesim varsa)
        if cut_times:
            validated = _validate_with_ssim(video_path, cut_times, fps)
            print(
                f"[SceneAnalyzer] SSIM doğrulama: {len(cut_times)} → {len(validated)} kesim"
            )
            cut_times = validated

        # Adım 3: Yakın kesimleri birleştir
        cut_times = _merge_nearby_cuts(cut_times, MIN_CUT_GAP_S)

        # Adım 4: Kesimlerden sahne aralıkları oluştur
        scenes = _cuts_to_intervals(cut_times, duration)

        # Adım 5: Çok kısa sahneleri birleştir
        scenes = _merge_short_scenes(scenes, MIN_SCENE_DURATION_S)

        print(f"[SceneAnalyzer] Nihai sahne sayısı: {len(scenes)}")
        return scenes

    except Exception as e:
        print(f"[SceneAnalyzer] Hata: {e}")
        # Hata durumunda tüm videoyu tek sahne olarak döndür
        try:
            duration = _get_duration(video_path)
            return [SceneInterval(start_s=0.0, end_s=duration)]
        except Exception:
            return [SceneInterval(start_s=0.0, end_s=0.0)]


# ─── FFmpeg Scene Detection ───────────────────────────────────────────────────

def _ffmpeg_scene_detect(video_path: str, threshold: float) -> list[float]:
    """
    FFmpeg scene filter ile sahne geçiş zamanlarını bul.
    showinfo filtresi pts_time değerlerini stderr'e yazar.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "0",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        times = []
        for match in re.finditer(r"pts_time:(\d+\.?\d*)", result.stderr):
            times.append(float(match.group(1)))
        return sorted(set(times))
    except subprocess.TimeoutExpired:
        print("[SceneAnalyzer] FFmpeg timeout — sahne tespiti atlanıyor")
        return []
    except Exception as e:
        print(f"[SceneAnalyzer] FFmpeg hatası: {e}")
        return []


# ─── SSIM Doğrulama ───────────────────────────────────────────────────────────

def _validate_with_ssim(
    video_path: str,
    cut_times: list[float],
    fps: float,
) -> list[float]:
    """
    Her aday kesim noktasını SSIM ile doğrula.

    Mantık:
    - Düşük SSIM (<0.40) → Kesin sahne geçişi, kabul et
    - Orta SSIM (0.40-0.70) → Geniş bağlamla tekrar kontrol et
    - Yüksek SSIM (>0.70) → Yanlış alarm, reddet
    """
    if not cut_times:
        return []

    validated = []
    frame_duration = 1.0 / fps if fps > 0 else 1.0 / 30.0

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("[SceneAnalyzer] VideoCapture açılamadı — SSIM atlanıyor")
        return cut_times  # SSIM olmadan ham listeyi döndür

    try:
        for cut_time in cut_times:
            before_time = max(0.0, cut_time - frame_duration)
            after_time = cut_time + frame_duration

            frame_before = _extract_frame(cap, before_time)
            frame_after = _extract_frame(cap, after_time)

            # Frame alınamazsa güvenli tarafta kal → kabul et
            if frame_before is None or frame_after is None:
                print(f"[SceneAnalyzer] t={cut_time:.2f}s: Frame alınamadı → kabul edildi")
                validated.append(cut_time)
                continue

            ssim = _compute_ssim_small(frame_before, frame_after)
            print(f"[SceneAnalyzer] t={cut_time:.2f}s: SSIM={ssim:.4f} (hard<{SSIM_HARD_CUT_THRESHOLD}, soft<{SSIM_SOFT_CUT_THRESHOLD})")

            if ssim < SSIM_HARD_CUT_THRESHOLD:
                # Kesin geçiş
                print(f"[SceneAnalyzer]   → KABUL (hard cut)")
                validated.append(cut_time)
            elif ssim < SSIM_SOFT_CUT_THRESHOLD:
                # Şüpheli — geniş bağlamla doğrula (0.5s önce/sonra)
                before_wide = _extract_frame(cap, max(0.0, cut_time - 0.5))
                after_wide = _extract_frame(cap, cut_time + 0.5)
                if before_wide is not None and after_wide is not None:
                    wide_ssim = _compute_ssim_small(before_wide, after_wide)
                    print(f"[SceneAnalyzer]   → Soft — wide SSIM={wide_ssim:.4f}")
                    if wide_ssim < SSIM_SOFT_CUT_THRESHOLD:
                        print(f"[SceneAnalyzer]   → KABUL (soft cut)")
                        validated.append(cut_time)
                    else:
                        print(f"[SceneAnalyzer]   → REDDEDİLDİ (wide SSIM yüksek)")
                else:
                    print(f"[SceneAnalyzer]   → KABUL (wide frame alınamadı)")
                    validated.append(cut_time)
            else:
                # Yüksek SSIM → yanlış alarm
                print(f"[SceneAnalyzer]   → REDDEDİLDİ (SSIM çok yüksek → aynı sahne)")
    finally:
        cap.release()

    return validated


def _extract_frame(
    cap: cv2.VideoCapture, time_s: float
) -> Optional[np.ndarray]:
    """VideoCapture'dan belirli zamandaki frame'i al."""
    cap.set(cv2.CAP_PROP_POS_MSEC, time_s * 1000)
    ret, frame = cap.read()
    return frame if ret else None


def _compute_ssim_small(
    img1: np.ndarray, img2: np.ndarray, size: tuple[int, int] = (160, 90)
) -> float:
    """
    İki frame arasındaki SSIM değerini hesapla.
    Hız için küçük boyuta indir ve gri tonlamaya çevir.
    """
    try:
        # Küçült
        small1 = cv2.resize(img1, size)
        small2 = cv2.resize(img2, size)

        # Gri tonlamaya çevir
        gray1 = cv2.cvtColor(small1, cv2.COLOR_BGR2GRAY).astype(np.float64)
        gray2 = cv2.cvtColor(small2, cv2.COLOR_BGR2GRAY).astype(np.float64)

        # SSIM sabitleri
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2

        mu1 = cv2.GaussianBlur(gray1, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(gray2, (11, 11), 1.5)

        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2

        sigma1_sq = cv2.GaussianBlur(gray1 ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(gray2 ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(gray1 * gray2, (11, 11), 1.5) - mu1_mu2

        ssim_map = (
            (2 * mu1_mu2 + C1) * (2 * sigma12 + C2)
        ) / (
            (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
        )

        return float(ssim_map.mean())
    except Exception as e:
        print(f"[SceneAnalyzer] SSIM hesaplama hatası: {e}")
        return 0.0  # Hata durumunda → kesim olarak kabul et


# ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def _merge_nearby_cuts(cuts: list[float], min_gap: float) -> list[float]:
    """MIN_CUT_GAP_S'den yakın kesimleri birleştir (ilkini tut)."""
    if not cuts:
        return []
    merged = [cuts[0]]
    for cut in cuts[1:]:
        if cut - merged[-1] >= min_gap:
            merged.append(cut)
    return merged


def _cuts_to_intervals(cuts: list[float], duration: float) -> list[SceneInterval]:
    """Kesim noktası listesinden SceneInterval listesi oluştur."""
    boundaries = [0.0] + cuts + [duration]
    intervals = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        if end > start:
            intervals.append(SceneInterval(start_s=start, end_s=end))
    return intervals if intervals else [SceneInterval(start_s=0.0, end_s=duration)]


def _merge_short_scenes(
    scenes: list[SceneInterval], min_duration: float
) -> list[SceneInterval]:
    """MIN_SCENE_DURATION_S'den kısa sahneleri önceki sahneyle birleştir."""
    if not scenes:
        return []

    merged = [SceneInterval(
        start_s=scenes[0].start_s,
        end_s=scenes[0].end_s,
        scene_type=scenes[0].scene_type,
    )]

    for scene in scenes[1:]:
        if scene.duration_s < min_duration:
            # Önceki sahnenin sonuna ekle
            prev = merged[-1]
            merged[-1] = SceneInterval(
                start_s=prev.start_s,
                end_s=scene.end_s,
                scene_type=prev.scene_type,
            )
        else:
            merged.append(SceneInterval(
                start_s=scene.start_s,
                end_s=scene.end_s,
                scene_type=scene.scene_type,
            ))

    return merged


def _get_duration(video_path: str) -> float:
    """FFprobe ile video süresini al."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[SceneAnalyzer] Süre alınamadı: {e}")
        raise
