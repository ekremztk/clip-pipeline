from typing import Optional


async def fetch_youtube_captions(video_id: str) -> Optional[str]:
    """
    YouTube video'sunun transkriptini alır.
    youtube-transcript-api kütüphanesini kullanır (YouTube API kotası HARCAMAZ).

    Öncelik sırası:
    1. Manuel İngilizce altyazı (daha doğru)
    2. Otomatik oluşturulan İngilizce altyazı
    3. None (altyazı yoksa)

    Kütüphane: youtube-transcript-api (pip install youtube-transcript-api)

    Args:
        video_id: YouTube video ID'si (URL değil, sadece ID)

    Returns:
        Düz metin transkript (timestamp'siz, sadece metin) veya None

    Note:
        Bu fonksiyon YouTube Data API kullanmaz, kota harcamaz.
        Bazı videolarda altyazı devre dışı olabilir, bu durumda None döner.
    """
    raise NotImplementedError("TODO")


async def fetch_youtube_captions_with_timestamps(video_id: str) -> Optional[list[dict]]:
    """
    YouTube video'sunun transkriptini timestamp'lerle birlikte alır.

    Args:
        video_id: YouTube video ID'si

    Returns:
        [{"text": "hello", "start": 0.0, "duration": 2.5}, ...] veya None

    Note:
        Deep analysis'te approximate location tespiti için kullanılabilir.
    """
    raise NotImplementedError("TODO")
