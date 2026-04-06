import os
import uuid
import asyncio
from typing import Optional
from pathlib import Path

import yt_dlp


class VideoDownloader:
    """
    yt-dlp wrapper for downloading YouTube videos.
    Routes traffic through Cloudflare WARP proxy when WARP_PRIVATE_KEY is configured.
    """

    def __init__(self):
        self.output_dir = Path(os.getenv("UPLOAD_DIR", "temp_uploads"))
        # Set by start.sh when wireproxy is running
        self.proxy = os.getenv("WARP_PROXY_URL", "socks5h://127.0.0.1:1080") if os.getenv("WARP_PRIVATE_KEY") else ""

    def _build_ydl_opts(self, output_template: str, max_quality: str = "1080") -> dict:
        height = int(max_quality)
        opts = {
            # Prefer mp4 video + m4a audio; fall back to best available
            "format": (
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={height}]+bestaudio"
                f"/best[height<={height}]/best"
            ),
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            # TV client avoids SABR (YouTube's new streaming protocol that breaks downloads)
            # Android client as fallback
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv", "android"],
                }
            },
            # Use Node.js for n-parameter decipher (required since yt-dlp v2025.11)
            "allow_multiple_video_streams": False,
            "allow_multiple_audio_streams": False,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
            print(f"[VideoDownloader] Using WARP proxy: {self.proxy}")
        else:
            print("[VideoDownloader] No proxy configured (local dev mode)")
        return opts

    async def download(
        self,
        youtube_url: str,
        output_dir: Optional[str] = None,
        max_quality: str = "1080",
    ) -> str:
        """
        Downloads a YouTube video and returns the local file path.

        Args:
            youtube_url: Full YouTube URL (watch, shorts, youtu.be)
            output_dir: Directory to save into; defaults to temp_uploads
            max_quality: Max vertical resolution ("720" | "1080" | "1440")

        Returns:
            Absolute path to the downloaded mp4 file

        Raises:
            RuntimeError: if yt-dlp fails
            FileNotFoundError: if downloaded file not found after success
        """
        target_dir = Path(output_dir) if output_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        file_id = str(uuid.uuid4())
        output_template = str(target_dir / f"{file_id}.%(ext)s")

        ydl_opts = self._build_ydl_opts(output_template, max_quality)
        loop = asyncio.get_event_loop()

        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])

        try:
            await loop.run_in_executor(None, _run)
        except Exception as e:
            raise RuntimeError(f"yt-dlp download failed: {e}")

        # Find the output file (extension may vary before merging)
        for f in target_dir.iterdir():
            if f.stem == file_id:
                return str(f)

        raise FileNotFoundError(f"Downloaded file not found for id {file_id}")

    async def get_info(self, youtube_url: str) -> dict:
        """
        Returns video metadata without downloading.
        Used to pre-fill title and validate URL before job creation.
        """
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 20,
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv", "android"],
                }
            },
        }
        if self.proxy:
            ydl_opts["proxy"] = self.proxy

        loop = asyncio.get_event_loop()

        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(youtube_url, download=False)

        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, _run),
                timeout=30,
            )
            return info or {}
        except asyncio.TimeoutError:
            # Proxy timed out — retry without proxy to at least get metadata
            if self.proxy:
                print("[VideoDownloader] get_info proxy timeout, retrying without proxy for metadata")
                ydl_opts_noproxy = {**ydl_opts}
                del ydl_opts_noproxy["proxy"]
                def _run_noproxy():
                    with yt_dlp.YoutubeDL(ydl_opts_noproxy) as ydl:
                        return ydl.extract_info(youtube_url, download=False)
                try:
                    info = await asyncio.wait_for(
                        loop.run_in_executor(None, _run_noproxy),
                        timeout=20,
                    )
                    return info or {}
                except Exception as e2:
                    raise RuntimeError(f"yt-dlp get_info failed (proxy + direct): {e2}")
            raise RuntimeError("Timed out fetching video info (30s).")
        except Exception as e:
            raise RuntimeError(f"yt-dlp get_info failed: {e}")
