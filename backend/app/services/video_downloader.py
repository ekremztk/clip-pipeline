import os
from typing import Optional


class VideoDownloader:
    """
    yt-dlp wrapper. YouTube videolarını indirir.
    Content Finder -> Clip Extractor entegrasyonu için kullanılır.
    """

    def __init__(self):
        self.output_dir = os.getenv("UPLOAD_DIR", "uploads")

    async def download(
        self,
        youtube_url: str,
        output_dir: Optional[str] = None,
        max_quality: str = "1080"
    ) -> str:
        """
        YouTube videosunu indirir.

        Args:
            youtube_url: YouTube video URL'si
            output_dir: İndirme dizini (varsayılan: self.output_dir)
            max_quality: Maksimum video kalitesi ("720" | "1080" | "1440" | "2160")

        Returns:
            İndirilen dosyanın tam yolu (str)

        Raises:
            RuntimeError: yt-dlp başarısız olursa
            FileNotFoundError: İndirilen dosya bulunamazsa
        """
        raise NotImplementedError("TODO")

    async def get_info(self, youtube_url: str) -> dict:
        """
        Video bilgilerini alır, indirmez.
        yt-dlp --dump-json kullanır.

        Args:
            youtube_url: YouTube video URL'si

        Returns:
            Video metadata dict (title, duration, formats, vs.)
        """
        raise NotImplementedError("TODO")
