import os
import re
import uuid
import asyncio
from typing import Optional
from pathlib import Path

import httpx
import yt_dlp

_RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "1dc730a48fmsh7906afc02af405ap1a3adejsn480eb41b8a56")
_RAPIDAPI_HOST = "youtube86.p.rapidapi.com"
_RAPIDAPI_BASE = f"https://{_RAPIDAPI_HOST}"
_RAPIDAPI_HEADERS = {
    "x-rapidapi-key": _RAPIDAPI_KEY,
    "x-rapidapi-host": _RAPIDAPI_HOST,
    "Content-Type": "application/json",
}


def _pick_download_url(links: list, max_quality: str) -> Optional[str]:
    """
    Pick the best download URL from the API response that fits within max_quality.
    Falls back to the first available URL if no quality match is found.
    """
    max_height = int(max_quality)
    best_url = None
    best_height = 0

    for link in links:
        url = (
            link.get("url")
            or link.get("link")
            or link.get("downloadUrl")
            or link.get("download_url")
        )
        if not url:
            continue

        quality_str = str(
            link.get("quality")
            or link.get("resolution")
            or link.get("label")
            or link.get("qualityLabel")
            or ""
        )
        m = re.search(r"(\d{3,4})", quality_str)
        height = int(m.group(1)) if m else 0

        if height <= max_height and height > best_height:
            best_url = url
            best_height = height

    if best_url:
        return best_url

    # Fallback: return first URL regardless of quality
    for link in links:
        url = (
            link.get("url")
            or link.get("link")
            or link.get("downloadUrl")
            or link.get("download_url")
        )
        if url:
            return url

    return None


class VideoDownloader:
    """
    Downloads YouTube videos via RapidAPI youtube86.
    Flow: POST /links → poll GET /status/{taskId} → download file.
    """

    def __init__(self):
        self.output_dir = Path(os.getenv("UPLOAD_DIR", "temp_uploads"))

    async def download(
        self,
        youtube_url: str,
        output_dir: Optional[str] = None,
        max_quality: str = "1080",
    ) -> str:
        """
        Downloads a YouTube video via RapidAPI youtube86 and returns the local file path.

        Args:
            youtube_url: Full YouTube URL (watch, shorts, youtu.be)
            output_dir: Directory to save into; defaults to temp_uploads
            max_quality: Max vertical resolution ("720" | "1080" | "1440")

        Returns:
            Absolute path to the downloaded mp4 file

        Raises:
            RuntimeError: if the API fails or task times out
            FileNotFoundError: if the saved file is missing after download
        """
        target_dir = Path(output_dir) if output_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: Submit download task ──────────────────────────────────────
        print(f"[VideoDownloader] Submitting to RapidAPI: {youtube_url}")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_RAPIDAPI_BASE}/links",
                headers=_RAPIDAPI_HEADERS,
                json={"url": youtube_url},
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"RapidAPI /links returned {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()

        task_id = (
            data.get("taskId")
            or data.get("task_id")
            or data.get("id")
            or data.get("requestId")
        )
        if not task_id:
            raise RuntimeError(f"No taskId in /links response: {data}")
        print(f"[VideoDownloader] Task created: {task_id}")

        # ── Step 2: Poll /status/{taskId} until ready ─────────────────────────
        download_url = None
        for attempt in range(60):  # max 5 minutes (60 × 5s)
            await asyncio.sleep(5)
            async with httpx.AsyncClient(timeout=15) as client:
                status_resp = await client.get(
                    f"{_RAPIDAPI_BASE}/status/{task_id}",
                    headers=_RAPIDAPI_HEADERS,
                )
                if status_resp.status_code != 200:
                    print(
                        f"[VideoDownloader] /status returned {status_resp.status_code} "
                        f"(attempt {attempt + 1}), retrying..."
                    )
                    continue
                status_data = status_resp.json()

            status = str(
                status_data.get("status")
                or status_data.get("state")
                or ""
            ).lower()

            print(f"[VideoDownloader] Poll {attempt + 1}/60 — status: {status}")

            if status in ("completed", "ready", "done", "finished", "success"):
                links = (
                    status_data.get("links")
                    or status_data.get("formats")
                    or status_data.get("videos")
                    or status_data.get("result", {}).get("links")
                    or []
                )
                if isinstance(links, dict):
                    links = list(links.values())

                download_url = _pick_download_url(links, max_quality)
                if not download_url:
                    # Maybe the URL is at the top level
                    download_url = (
                        status_data.get("url")
                        or status_data.get("downloadUrl")
                        or status_data.get("download_url")
                    )
                break

            if status in ("failed", "error", "cancelled"):
                raise RuntimeError(
                    f"RapidAPI task {task_id} failed: {status_data}"
                )
            # still processing — continue polling

        if not download_url:
            raise RuntimeError(
                f"RapidAPI task {task_id} timed out or returned no download URL"
            )

        print(f"[VideoDownloader] Downloading from: {download_url[:80]}...")

        # ── Step 3: Stream video to disk ──────────────────────────────────────
        file_id = str(uuid.uuid4())
        file_path = target_dir / f"{file_id}.mp4"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30, read=300, write=300, pool=30),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", download_url) as stream_resp:
                if stream_resp.status_code >= 400:
                    raise RuntimeError(
                        f"Video download URL returned {stream_resp.status_code}"
                    )
                with open(file_path, "wb") as fh:
                    async for chunk in stream_resp.aiter_bytes(chunk_size=65536):
                        fh.write(chunk)

        if not file_path.exists() or file_path.stat().st_size == 0:
            raise FileNotFoundError(
                f"Downloaded file missing or empty: {file_path}"
            )

        print(
            f"[VideoDownloader] Saved {file_path.stat().st_size / 1024 / 1024:.1f} MB "
            f"→ {file_path}"
        )
        return str(file_path)

    async def get_info(self, youtube_url: str) -> dict:
        """
        Returns video metadata (title, duration) without downloading.
        Uses YouTube oEmbed API for title (reliable, no IP blocks) and
        yt-dlp fallback for duration.
        """
        # Extract video ID
        match = re.search(r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})', youtube_url)
        if not match:
            raise RuntimeError("Could not extract video ID from URL")
        video_id = match.group(1)

        title = ""
        duration = 0
        thumbnail = ""
        channel = ""

        # Step 1: oEmbed for title (public API, works from any IP, no key required)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://www.youtube.com/oembed",
                    params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "")
                    thumbnail = data.get("thumbnail_url", "")
                    channel = data.get("author_name", "")
        except Exception as e:
            print(f"[VideoDownloader] oEmbed failed: {e}")

        # Step 2: yt-dlp for duration (non-critical fallback)
        loop = asyncio.get_event_loop()
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 15,
            "extractor_args": {"youtube": {"player_client": ["tv"]}},
        }

        def _run_duration():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                return info.get("duration", 0) if info else 0

        try:
            duration = await asyncio.wait_for(
                loop.run_in_executor(None, _run_duration),
                timeout=25,
            )
        except Exception as e:
            print(f"[VideoDownloader] duration fetch failed (non-critical): {e}")
            duration = 0

        if not title:
            raise RuntimeError("Could not fetch video info. Check the URL.")

        return {
            "title": title,
            "duration": duration,
            "thumbnail": thumbnail,
            "channel": channel,
        }
