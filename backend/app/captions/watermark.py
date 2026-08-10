"""Per-channel watermark burned into the caption overlay.

The mark exists to show a human reviewer that the file passed through an
editor rather than being reposted from somewhere else, so it has to be inside
the pixels — not a container tag. It rides along in the transparent caption
overlay that both renderers already build, which means it costs no extra
FFmpeg pass and no second encode.

Keyed by caption template because today each channel owns one template. If a
channel ever changes caption style this mapping is the thing to replace with a
proper per-channel field on the job.
"""
from __future__ import annotations

import logging
import os

from PIL import Image

logger = logging.getLogger(__name__)

# template key -> asset file name
WATERMARK_ASSETS: dict[str, str] = {
    "capcut_word_highlight_ii": "theotherside_logodamgasi.png",
    "yellow_center": "theyellowcast_logodamgasi.png",
}

_ASSET_DIRS = (
    "/app/app/captions/assets",
    os.path.join(os.path.dirname(__file__), "assets"),
    "backend/app/captions/assets",
)

# (template_key, width, height) -> full-frame RGBA layer, or None when absent.
_CACHE: dict[tuple[str, int, int], Image.Image | None] = {}


def load_watermark(template_key: str, width: int, height: int) -> Image.Image | None:
    """Return a full-frame RGBA watermark layer, or None if this template has none.

    Cached: the frame loop calls this once per frame and the layer never changes.
    """
    cache_key = (template_key, width, height)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    layer = None
    name = WATERMARK_ASSETS.get(template_key)
    if name:
        try:
            path = _resolve(name)
            if path:
                image = Image.open(path).convert("RGBA")
                if image.size != (width, height):
                    image = image.resize((width, height), Image.LANCZOS)
                layer = image
                logger.info("[Watermark] %s -> %s", template_key, path)
            else:
                logger.warning("[Watermark] Asset not found for %s: %s", template_key, name)
        except Exception as e:
            # A missing or unreadable mark must never take the render down.
            logger.warning("[Watermark] Failed to load %s: %s", name, e)
            layer = None

    _CACHE[cache_key] = layer
    return layer


def _resolve(name: str) -> str | None:
    for directory in _ASSET_DIRS:
        path = os.path.join(directory, name)
        if os.path.exists(path):
            return path
    return None
