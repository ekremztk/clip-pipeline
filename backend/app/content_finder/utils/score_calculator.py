def title_similarity(title_a: str, title_b: str) -> float:
    """
    İki başlık arasındaki Jaccard benzerliğini hesaplar.
    Kelime bazlı karşılaştırma yapar (lowercase, stop words çıkarılır).

    Args:
        title_a: İlk başlık
        title_b: İkinci başlık

    Returns:
        0.0 (hiç benzemez) ile 1.0 (aynı) arası float
    """
    raise NotImplementedError("TODO")


def detect_language(text: str) -> str:
    """
    Metnin dilini tespit eder.
    Basit heuristik: İngilizce karakter oranı ve yaygın kelime kontrolü.

    Args:
        text: Kontrol edilecek metin

    Returns:
        Dil kodu: "en", "tr", "unknown" vs.
    """
    raise NotImplementedError("TODO")


def format_view_count(count: int) -> str:
    """
    Görüntülenme sayısını okunabilir formata çevirir.
    Örnekler: 1234 -> "1.2K", 1500000 -> "1.5M", 2300000000 -> "2.3B"

    Args:
        count: Ham sayı

    Returns:
        Formatlanmış string
    """
    raise NotImplementedError("TODO")


def format_duration(seconds: int) -> str:
    """
    Saniyeyi okunabilir süre formatına çevirir.
    Örnekler: 3661 -> "1:01:01", 745 -> "12:25", 59 -> "0:59"

    Args:
        seconds: Saniye cinsinden süre

    Returns:
        Formatlanmış string
    """
    raise NotImplementedError("TODO")
