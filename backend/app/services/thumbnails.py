"""
Poster frames for clips.

A clip card used to be a <video> element, so a grid of forty cards opened forty
connections and pulled the MP4 header plus enough of the stream to paint one
frame — hundreds of kilobytes each, queued six at a time by the browser. A JPEG
of the same frame is around thirty kilobytes and can be lazy-loaded, which is
the whole reason this module exists.

Every function here is best-effort. A clip with no poster frame still plays, so
a failure returns None and is logged rather than raised — losing a finished clip
over a thumbnail would be a bad trade.
"""

import os
import subprocess
import uuid
from typing import Optional

from app.config import settings
from app.services.r2_client import get_r2_client

# Seek a little past the start: the opening frame of a cut is often a fade or a
# black field, which makes for a poster frame that says nothing about the clip.
DEFAULT_OFFSET_S = 0.5

WIDE_WIDTH = 640     # 16:9 person covers
VERTICAL_WIDTH = 400  # 9:16 clip cards


def extract_frame(
    source: str,
    out_path: str,
    at_seconds: float = DEFAULT_OFFSET_S,
    width: int = WIDE_WIDTH,
) -> bool:
    """
    Write one frame of `source` to `out_path` as JPEG.

    `source` may be a local path or an http(s) URL — FFmpeg range-requests a
    remote file, so this reads the header and the first seconds rather than
    downloading the whole clip.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(at_seconds),
        "-i", source,
        "-frames:v", "1",
        "-vf", f"scale={width}:-2",
        "-q:v", "4",
        out_path,
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
    except Exception as e:
        # A clip shorter than the offset seeks past its own end and produces
        # nothing; retry from the very first frame before giving up.
        if at_seconds > 0:
            return extract_frame(source, out_path, at_seconds=0, width=width)
        print(f"[Thumbnails] Frame extraction failed for {source}: {e}")
        return False

    return os.path.exists(out_path) and os.path.getsize(out_path) > 0


def upload_thumbnail(local_path: str, r2_key: str) -> str:
    """Put a local JPEG in R2 and return its public URL."""
    r2 = get_r2_client()
    with open(local_path, "rb") as f:
        r2.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=r2_key,
            Body=f,
            ContentType="image/jpeg",
            CacheControl="public, max-age=31536000, immutable",
        )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{r2_key}"


def make_thumbnail(
    source: str,
    r2_key: str,
    at_seconds: float = DEFAULT_OFFSET_S,
    width: int = WIDE_WIDTH,
) -> Optional[str]:
    """
    Extract a frame from `source`, upload it, return its URL — or None if any
    step fails. Never raises: the caller is mid-pipeline with a finished clip.
    """
    tmp_dir = str(settings.UPLOAD_DIR)
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"thumb_{uuid.uuid4().hex}.jpg")

    try:
        if not extract_frame(source, tmp_path, at_seconds=at_seconds, width=width):
            return None
        return upload_thumbnail(tmp_path, r2_key)
    except Exception as e:
        print(f"[Thumbnails] Could not produce {r2_key}: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
