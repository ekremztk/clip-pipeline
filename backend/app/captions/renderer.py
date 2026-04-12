"""
Caption renderer — burns captions onto video using FFmpeg drawtext.

Template → FFmpeg drawtext filter chain → rendered MP4.

Two caption modes:
  - Segment mode (most templates): full segment text shown for segment duration
  - Word mode (karaoke templates like Hormozi): each word flashes individually
    in the highlight color — the classic TikTok/Reels pop-in effect

Fonts: uses Open Sans from fonts-open-sans (installed in Dockerfile).
fontfile= is used instead of fontconfig font= to avoid fc-cache dependency.
"""
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Canvas dimensions for 9:16 content
CANVAS_W = 1080
CANVAS_H = 1920

# Font size scale: template fontSize (4–6) → pixels
FONT_SCALE = 18  # fontSize 4 = 72px, 5 = 90px, 6 = 108px

# Y center offset: template y=0 → video center (960px)
Y_CENTER = CANVAS_H // 2

# Absolute font file paths (installed via fonts-open-sans on Railway/Debian)
_OPEN_SANS_DIR = "/usr/share/fonts/truetype/open-sans"

# Font family → absolute TTF path
# All templates fall back to Open Sans variants — similar weight/style profile.
FONT_MAP = {
    "Montserrat":  f"{_OPEN_SANS_DIR}/OpenSans-Bold.ttf",
    "Poppins":     f"{_OPEN_SANS_DIR}/OpenSans-Regular.ttf",
    "Bebas Neue":  f"{_OPEN_SANS_DIR}/OpenSansCondensed-Bold.ttf",
    "Oswald":      f"{_OPEN_SANS_DIR}/OpenSansCondensed-Bold.ttf",
}

# Pipeline key → template config (mirrors caption-templates.ts)
TEMPLATE_CONFIGS: dict[str, dict] = {
    "clean": {
        "font": "Montserrat", "font_bold": True,
        "font_size": 4, "color": "white",
        "stroke_color": "black", "stroke_w": 8,
        "shadow": None, "bg": None,
        "text_transform": "capitalize",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 150,
    },
    "hormozi": {
        "font": "Montserrat", "font_bold": True,
        "font_size": 4, "color": "white",
        "stroke_color": "black", "stroke_w": 8,
        "shadow": None, "bg": None,
        "text_transform": "uppercase",
        "karaoke": True, "karaoke_color": "#FFE500",
        "y_offset": 150,
    },
    "outline": {
        "font": "Montserrat", "font_bold": True,
        "font_size": 5, "color": "white",
        "stroke_color": "black", "stroke_w": 6,
        "shadow": None, "bg": None,
        "text_transform": "none",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 150,
    },
    "pill": {
        "font": "Poppins", "font_bold": True,
        "font_size": 4, "color": "white",
        "stroke_color": None, "stroke_w": 0,
        "shadow": None,
        "bg": {"color": "black@0.50", "border": 50},
        "text_transform": "none",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 150,
    },
    "neon": {
        "font": "Bebas Neue", "font_bold": False,
        "font_size": 6, "color": "white",
        "stroke_color": None, "stroke_w": 0,
        "shadow": {"color": "0x00e5ff", "x": 0, "y": 0},
        "bg": None,
        "text_transform": "none",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 150,
    },
    "cinematic": {
        "font": "Oswald", "font_bold": False,
        "font_size": 4, "color": "white",
        "stroke_color": None, "stroke_w": 0,
        "shadow": None,
        "bg": {"color": "black@1.0", "border": 18},
        "text_transform": "none",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 400,
    },
    "bold_pop": {
        "font": "Montserrat", "font_bold": True,
        "font_size": 6, "color": "white",
        "stroke_color": "black", "stroke_w": 4,
        "shadow": {"color": "black", "x": 4, "y": 4},
        "bg": None,
        "text_transform": "none",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 150,
    },
    "fire": {
        "font": "Oswald", "font_bold": True,
        "font_size": 5, "color": "0xFF6B35",
        "stroke_color": "black", "stroke_w": 5,
        "shadow": {"color": "0xff0000", "x": 0, "y": 0},
        "bg": None,
        "text_transform": "none",
        "karaoke": False, "karaoke_color": None,
        "y_offset": 150,
    },
}


def render_captions(
    video_path: str,
    output_path: str,
    words: list[dict],
    segments: list[dict],
    template_key: str = "clean",
) -> str:
    """
    Burn captions onto video using FFmpeg drawtext.

    Args:
        video_path: Path to input video (9:16, 1080×1920)
        output_path: Path to output captioned MP4
        words: Word-level timestamps from Deepgram [{word, start, end, ...}]
        segments: Sentence segments [{text, start, end}]
        template_key: One of the 8 pipelineKey values

    Returns: output_path
    """
    cfg = TEMPLATE_CONFIGS.get(template_key) or TEMPLATE_CONFIGS["clean"]

    font_name = _resolve_font(cfg["font"])
    font_px = int(cfg["font_size"] * FONT_SCALE)
    y_abs = Y_CENTER + cfg["y_offset"]

    # Build drawtext filters
    filters = []

    if cfg["karaoke"] and words:
        # Word-by-word mode: each word pops in individually in highlight color
        highlight = _hex_to_ffmpeg(cfg["karaoke_color"] or "#FFE500")
        for w in words:
            text = _apply_transform(w.get("punctuated_word") or w.get("word", ""), cfg["text_transform"])
            if not text.strip():
                continue
            text_escaped = _escape_text(text)
            t_start = w.get("start", 0)
            t_end = w.get("end", t_start + 0.1)
            dt = _build_drawtext(
                text=text_escaped,
                font=font_name,
                font_px=font_px,
                color=highlight,
                stroke_color=cfg.get("stroke_color"),
                stroke_w=cfg.get("stroke_w", 0),
                shadow=cfg.get("shadow"),
                bg=cfg.get("bg"),
                y=y_abs,
                enable=f"between(t,{t_start:.3f},{t_end:.3f})",
            )
            filters.append(dt)
    else:
        # Segment mode: full sentence displayed for its duration
        for seg in segments:
            text = _apply_transform(seg.get("text", ""), cfg["text_transform"])
            if not text.strip():
                continue
            text_escaped = _escape_text(text)
            t_start = seg.get("start", 0)
            t_end = seg.get("end", t_start + 0.1)
            color = _hex_to_ffmpeg(cfg["color"]) if cfg["color"].startswith("#") else cfg["color"]
            dt = _build_drawtext(
                text=text_escaped,
                font=font_name,
                font_px=font_px,
                color=color,
                stroke_color=cfg.get("stroke_color"),
                stroke_w=cfg.get("stroke_w", 0),
                shadow=cfg.get("shadow"),
                bg=cfg.get("bg"),
                y=y_abs,
                enable=f"between(t,{t_start:.3f},{t_end:.3f})",
            )
            filters.append(dt)

    if not filters:
        # No captions to burn — just copy
        logger.warning("[CaptionRenderer] No caption segments to render, copying input")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    vf = ",".join(filters)
    _run_ffmpeg_drawtext(video_path, output_path, vf)
    logger.info("[CaptionRenderer] Rendered %d caption items (%s) → %s", len(filters), template_key, output_path)
    return output_path


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_drawtext(
    text: str,
    font: str,
    font_px: int,
    color: str,
    stroke_color: Optional[str],
    stroke_w: int,
    shadow: Optional[dict],
    bg: Optional[dict],
    y: int,
    enable: str,
) -> str:
    """Build a single FFmpeg drawtext filter string."""
    parts = [
        f"drawtext=fontfile='{font}'",
        f"fontsize={font_px}",
        f"fontcolor={color}",
        f"text='{text}'",
        f"x=(w-text_w)/2",
        f"y={y}",
        f"enable='{enable}'",
    ]

    if stroke_color and stroke_w > 0:
        parts.append(f"bordercolor={stroke_color}")
        parts.append(f"borderw={stroke_w}")

    if shadow:
        parts.append(f"shadowcolor={shadow['color']}")
        parts.append(f"shadowx={shadow['x']}")
        parts.append(f"shadowy={shadow['y']}")

    if bg:
        parts.append("box=1")
        parts.append(f"boxcolor={bg['color']}")
        parts.append(f"boxborderw={bg['border']}")

    return ":".join(parts)


def _run_ffmpeg_drawtext(input_path: str, output_path: str, vf: str) -> None:
    """Run FFmpeg with -vf drawtext chain."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg caption render failed: {result.stderr[-800:]}")


def _run_ffmpeg_copy(input_path: str, output_path: str) -> None:
    """Copy video without re-encode (no captions)."""
    cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg copy failed: {result.stderr[-400:]}")


def _resolve_font(font_family: str) -> str:
    """Resolve font family name to absolute TTF file path.

    If the mapped font file doesn't exist on this system (e.g. in dev),
    fall back to any available Open Sans Bold so FFmpeg doesn't crash.
    """
    path = FONT_MAP.get(font_family, f"{_OPEN_SANS_DIR}/OpenSans-Bold.ttf")
    if not os.path.exists(path):
        # Try the bold variant as first fallback
        fallback = f"{_OPEN_SANS_DIR}/OpenSans-Bold.ttf"
        if os.path.exists(fallback):
            logger.warning("[CaptionRenderer] Font not found: %s → using %s", path, fallback)
            return fallback
        # Last resort: let FFmpeg pick whatever it finds
        logger.warning("[CaptionRenderer] No Open Sans fonts found at %s — FFmpeg will use default", _OPEN_SANS_DIR)
        return path
    return path


def _hex_to_ffmpeg(hex_color: str) -> str:
    """Convert #RRGGBB to FFmpeg hex 0xRRGGBB."""
    if hex_color.startswith("#"):
        return "0x" + hex_color[1:]
    return hex_color


def _escape_text(text: str) -> str:
    """Escape text for FFmpeg drawtext (colons, apostrophes, backslashes)."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")   # replace apostrophe with right curly quote
    text = text.replace(":", "\\:")
    text = text.replace(",", "\\,")
    return text


def _apply_transform(text: str, transform: Optional[str]) -> str:
    """Apply text transform (uppercase, capitalize, etc.).

    Uses locale-aware uppercase so Turkish dotless-i (ı→I) and
    dotted-i (i→İ) are handled correctly instead of Python's default
    ASCII-centric .upper() which maps ı→I and leaves İ as-is.
    """
    if transform == "uppercase":
        return text.translate(_TR_UPPER_TABLE).upper()
    if transform == "lowercase":
        return text.lower()
    if transform == "capitalize":
        return text.title()
    return text


# Turkish-specific upper/lower char mapping.
# Python's str.upper() maps ı→I (correct) but maps i→I instead of i→İ.
# Pre-translate the Turkish-specific pairs before calling .upper()
# so the standard upper() call handles the rest of Unicode correctly.
_TR_UPPER_TABLE = str.maketrans("iı", "İI")
