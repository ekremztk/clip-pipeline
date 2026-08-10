"""Per-channel watermark burned into the caption overlay.

The mark exists so a human reviewing a reused-content report can see the clip
passed through an editor, so it has to be in the pixels rather than a container
tag. It rides along in the transparent overlay the caption renderer already
builds, which keeps it inside the single FFmpeg pass and the one encode a clip
is allowed.

Two rules this module exists to enforce:

1. **The mark belongs to a channel, not to a caption style.** An earlier version
   keyed it by template. A template is a style, shared across accounts — the
   default one is what client jobs get — so that version stamped our channel's
   mark onto client clips. Identity has to come from channel_id and nothing
   else.
2. **Absence is the default.** `channels.watermark_r2_key` is NULL until someone
   deliberately sets it, and every failure path here returns None. A channel is
   marked only when that was an explicit decision; every other outcome, including
   a broken asset or an unreachable database, produces an unmarked clip rather
   than a wrongly marked one.

The renderers never call the resolver. They are handed a path or None, so they
cannot select a watermark, correctly or otherwise.
"""
from __future__ import annotations

import logging
import os
import uuid

from PIL import Image

logger = logging.getLogger(__name__)

# (path, width, height) -> full-frame RGBA layer, or None when unusable.
_LAYER_CACHE: dict[tuple[str, int, int], Image.Image | None] = {}


def resolve_channel_watermark_key(channel_id: str | None) -> str | None:
    """Return the R2 key of this channel's watermark, or None if it has none."""
    if not channel_id:
        return None

    try:
        from app.services.supabase_client import get_client

        result = (
            get_client()
            .table("channels")
            .select("watermark_r2_key")
            .eq("id", channel_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            logger.info("[Watermark] No channel row for %s; rendering unmarked", channel_id)
            return None

        key = (result.data[0].get("watermark_r2_key") or "").strip()
        return key or None
    except Exception as e:
        # An unreachable database must not decide to stamp somebody's video.
        logger.warning("[Watermark] Lookup failed for channel %s: %s", channel_id, e)
        return None


def fetch_watermark(r2_key: str | None, dest_dir: str) -> str | None:
    """Download the watermark to a local file. Returns the path, or None."""
    if not r2_key:
        return None

    try:
        from app.services.r2_client import download_r2_to_local

        os.makedirs(dest_dir, exist_ok=True)
        suffix = os.path.splitext(r2_key)[1] or ".png"
        local_path = os.path.join(dest_dir, f"watermark_{uuid.uuid4().hex}{suffix}")
        download_r2_to_local(r2_key, local_path)

        if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
            logger.warning("[Watermark] Download produced nothing for %s", r2_key)
            return None

        logger.info("[Watermark] %s -> %s", r2_key, local_path)
        return local_path
    except Exception as e:
        logger.warning("[Watermark] Download failed for %s: %s", r2_key, e)
        return None


def load_watermark_layer(path: str | None, width: int, height: int) -> Image.Image | None:
    """Return a full-frame RGBA layer for `path`, resized to the video if needed."""
    if not path:
        return None

    cache_key = (path, width, height)
    if cache_key in _LAYER_CACHE:
        return _LAYER_CACHE[cache_key]

    layer: Image.Image | None = None
    try:
        image = Image.open(path).convert("RGBA")
        if image.size != (width, height):
            image = image.resize((width, height), Image.LANCZOS)
        layer = image
    except Exception as e:
        logger.warning("[Watermark] Unreadable asset %s: %s", path, e)
        layer = None

    _LAYER_CACHE[cache_key] = layer
    return layer
