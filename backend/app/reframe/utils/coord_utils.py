"""
Reframe V2 — Koordinat ve Aspect Ratio Yardımcıları

Aspect ratio string ↔ tuple dönüşümleri ve crop penceresi hesaplamaları.
"""


def parse_aspect_ratio(ratio_str: str) -> tuple[int, int]:
    """
    Aspect ratio string'ini (w, h) tuple'ına çevir.

    Örnekler:
        "9:16"  → (9, 16)
        "1:1"   → (1, 1)
        "4:5"   → (4, 5)
        "16:9"  → (16, 9)

    Geçersiz format durumunda (9, 16) döndürür.
    """
    try:
        parts = ratio_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"Geçersiz format: {ratio_str}")
        w = int(parts[0])
        h = int(parts[1])
        if w <= 0 or h <= 0:
            raise ValueError(f"Negatif değer: {ratio_str}")
        return (w, h)
    except Exception as e:
        print(f"[CoordUtils] Aspect ratio parse hatası ({ratio_str}): {e} — (9,16) kullanılıyor")
        return (9, 16)


def compute_crop_width(src_w: int, src_h: int, aspect_ratio: tuple[int, int]) -> int:
    """
    Kaynak video boyutları ve hedef aspect ratio'ya göre
    crop penceresinin piksel genişliğini hesapla.

    Crop penceresi her zaman kaynak video yüksekliğini kullanır
    ve istenilen aspect ratio'yu sağlayacak genişliği hesaplar.

    Örnek: 1920x1080 kaynak, 9:16 hedef
      crop_h = 1080 (tam yükseklik)
      crop_w = 1080 * (9/16) = 607 px

    Örnek: 1920x1080 kaynak, 1:1 hedef
      crop_h = 1080
      crop_w = 1080 * (1/1) = 1080 px (kaynak genişliğini geçemez)
    """
    out_w, out_h = aspect_ratio
    crop_w = int(src_h * (out_w / out_h))
    return min(crop_w, src_w)  # Kaynak genişliğini aşamaz


def compute_crop_height(src_w: int, src_h: int, aspect_ratio: tuple[int, int]) -> int:
    """
    Crop penceresinin piksel yüksekliğini hesapla.

    16:9 → 9:16 gibi "yatay kaynak → dikey hedef" dönüşümlerinde crop_h = src_h
    olursa Y hareketi için sıfır alan kalır. Bu durumda src_h'nin %88'ini kullanarak
    ±6% dikey hareket alanı açarız (kafa leaning-back durumlarında kaybolmasın).

    Kaynak zaten dikey veya kare ise tam src_h kullan.
    """
    out_w, out_h = aspect_ratio
    target_is_taller = out_h > out_w   # 9:16, 4:5, 1:1 gibi
    source_is_wider = src_w > src_h    # 1920x1080 gibi

    if target_is_taller and source_is_wider:
        # Dikey crop + geniş kaynak → %88 yükseklik kullan, Y hareketi için alan aç
        return int(src_h * 0.88)
    return src_h


def normalize_x_to_offset(
    target_x_norm: float,
    src_w: int,
    crop_w: int,
) -> float:
    """
    Normalize hedef X pozisyonunu (0.0-1.0) piksel offset'e çevir.

    target_x_norm: Kişinin normalize X pozisyonu (crop merkezine gelecek)
    src_w: Kaynak video genişliği (piksel)
    crop_w: Crop penceresi genişliği (piksel)

    Returns:
        offset_x: Crop penceresinin sol kenarının piksel pozisyonu.
                  0 = tamamen solda, (src_w - crop_w) = tamamen sağda.
    """
    # Kişiyi crop merkezine al
    offset_x = target_x_norm * src_w - crop_w / 2
    # Sınır kontrolü: crop frame dışına taşmasın
    return max(0.0, min(float(src_w - crop_w), offset_x))


def normalize_y_to_offset(
    target_y_norm: float,
    src_h: int,
    crop_h: int,
) -> float:
    """
    Normalize hedef Y pozisyonunu piksel offset'e çevir.
    X ile aynı mantık, dikey eksen için.
    """
    offset_y = target_y_norm * src_h - crop_h / 2
    return max(0.0, min(float(src_h - crop_h), offset_y))


def clamp_crop_target(
    target_x_norm: float,
    crop_w: int,
    src_w: int,
) -> float:
    """
    Normalize crop hedefini crop penceresinin sınırları içine kısıtla.
    Kişinin ekran kenarına çok yakın olduğu durumlarda crop frame dışına taşmaz.

    Returns: Kısıtlanmış normalize X değeri
    """
    half_crop_norm = (crop_w / 2) / src_w
    min_x = half_crop_norm
    max_x = 1.0 - half_crop_norm
    return max(min_x, min(max_x, target_x_norm))
