from __future__ import annotations

import os
from pathlib import Path

import httpx

from app.config import settings


def run(item: dict, work_id: str) -> str:
    """Download the captioned input MP4 for a Provision item."""
    input_url = (item.get("input_video_url") or "").strip()
    if not input_url:
        raise RuntimeError("Provision item has no input_video_url")

    upload_dir = Path(settings.UPLOAD_DIR) / "provision"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(upload_dir / f"{work_id}_input.mp4")

    print(f"[Provision/P01] Downloading input video -> {output_path}")
    with httpx.stream("GET", input_url, timeout=600.0, follow_redirects=True) as response:
        response.raise_for_status()
        with open(output_path, "wb") as handle:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)

    if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("Downloaded input video is empty")

    return output_path

