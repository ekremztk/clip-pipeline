"""
Pillow-based caption renderer — pixel-perfect match with editor (Canvas2D + freetype).

Renders each subtitle group as a transparent 1080x1920 PNG, then composites
them onto the video via FFmpeg overlay filters (multi-pass to avoid fd limits).

GPU-ready: encode codec/preset is configurable via env vars. Switch to
av1_nvenc by changing FFMPEG_VIDEO_CODEC + FFMPEG_ENCODE_PRESET.
"""
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import settings

logger = logging.getLogger(__name__)

CANVAS_W = 1080
CANVAS_H = 1920

FONT_SIZE_SCALE_REFERENCE = 90
FONT_PATH = "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/montserrat/Montserrat-Regular.ttf"

MAX_OVERLAYS_PER_PASS = 8

TEMPLATE_CONFIGS: dict[str, dict] = {
    "clean": {
        "font_path": FONT_PATH,
        "font_size_relative": 3,
        "line_height": 1.0,
        "text_color": (255, 255, 255, 255),
        "stroke_enabled": True,
        "stroke_color": (0, 0, 0),
        "stroke_width": 8,
        "shadow_enabled": True,
        "shadow_color": (0, 0, 0, 128),
        "shadow_offset_x": 3,
        "shadow_offset_y": 3,
        "shadow_blur": 6,
        "text_align": "center",
        "position_y_offset": 150,
        "words_per_group": 4,
        "max_lines": 2,
        "max_chars_per_line": 18,
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
    Burn captions onto video using Pillow PNG render + FFmpeg overlay.

    Args:
        video_path: Path to input video (9:16, 1080x1920)
        output_path: Path to output captioned MP4
        words: Word-level timestamps from Deepgram [{word, start, end, ...}]
        segments: Sentence segments (kept for API compatibility, unused)
        template_key: Template name (currently only "clean" uses Pillow)

    Returns: output_path
    """
    cfg = TEMPLATE_CONFIGS.get(template_key)
    if not cfg:
        logger.warning("[PillowRenderer] Unknown template '%s', falling back to clean", template_key)
        cfg = TEMPLATE_CONFIGS["clean"]

    if not words:
        logger.warning("[PillowRenderer] No words provided, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    words = _clean_and_transform_words(words)
    words = _deduplicate_stutters(words)

    groups = _build_word_groups(
        words,
        cfg["words_per_group"],
        max_lines=cfg.get("max_lines", 0),
        max_chars_per_line=cfg.get("max_chars_per_line", 0),
    )

    if not groups:
        logger.warning("[PillowRenderer] No word groups generated, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    out_dir = os.path.dirname(output_path) or "."
    png_paths: list[str] = []

    try:
        font_size_px = int(cfg["font_size_relative"] * (CANVAS_H / FONT_SIZE_SCALE_REFERENCE))
        font = _load_font(cfg["font_path"], font_size_px)

        for i, group in enumerate(groups):
            png_path = os.path.join(out_dir, f"sub_{uuid.uuid4().hex}.png")
            _render_subtitle_png(group["text"], font, cfg, font_size_px, png_path)
            group["png_path"] = png_path
            png_paths.append(png_path)

        _run_ffmpeg_overlay_multipass(video_path, output_path, groups, out_dir)

        logger.info(
            "[PillowRenderer] Rendered %d groups (%s) -> %s",
            len(groups), template_key, output_path,
        )
    finally:
        for p in png_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    return output_path


# --- Text transform -----------------------------------------------------------

def _clean_and_transform_words(words: list[dict]) -> list[dict]:
    """
    Process word list:
    1. Track sentence boundaries (words ending with '.')
    2. Remove punctuation EXCEPT apostrophes and sentence-ending periods
    3. Lowercase everything
    4. Capitalize first word + words after sentence-ending periods
    """
    capitalize_next = True

    for word in words:
        raw = word.get("punctuated_word") or word.get("word", "")
        ends_with_period = raw.rstrip().endswith(".")

        cleaned = "".join(c for c in raw if c.isalnum() or c in " '")
        cleaned = cleaned.lower()

        if capitalize_next and cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]
            capitalize_next = False

        if ends_with_period:
            cleaned = cleaned.rstrip() + "."
            capitalize_next = True

        word["display_text"] = cleaned.strip()

    return words


def _deduplicate_stutters(words: list[dict]) -> list[dict]:
    """
    Remove consecutive duplicate words (stutters like "I i i" → "I").
    Comparison is case-insensitive on the cleaned display_text (without trailing period).
    """
    if not words:
        return words

    result = [words[0]]

    for word in words[1:]:
        prev_text = result[-1].get("display_text", "").rstrip(".").lower()
        curr_text = word.get("display_text", "").rstrip(".").lower()

        if curr_text and curr_text == prev_text:
            result[-1]["end"] = word.get("end", result[-1].get("end", 0))
            continue

        result.append(word)

    return result


# --- Word grouping ------------------------------------------------------------

def _build_word_groups(
    words: list[dict],
    n: int,
    max_lines: int = 0,
    max_chars_per_line: int = 0,
) -> list[dict]:
    if max_lines > 0 and max_chars_per_line > 0:
        return _build_groups_by_chars(words, max_lines, max_chars_per_line)

    groups = []
    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        if not chunk:
            continue
        text_parts = [w.get("display_text") or w.get("word", "") for w in chunk]
        groups.append({
            "text": " ".join(text_parts),
            "start": chunk[0].get("start", 0.0),
            "end": chunk[-1].get("end", chunk[-1].get("start", 0.0) + 0.5),
            "words": chunk,
        })
    return groups


def _build_groups_by_chars(
    words: list[dict],
    max_lines: int,
    max_chars: int,
) -> list[dict]:
    groups: list[dict] = []
    i = 0

    while i < len(words):
        lines: list[list[dict]] = [[]]

        while i < len(words):
            word = words[i]
            word_text = word.get("display_text") or word.get("word", "")
            current_line_words = lines[-1]
            current_line_text = " ".join(
                w.get("display_text") or w.get("word", "") for w in current_line_words
            )
            candidate = (current_line_text + " " + word_text).strip()

            if len(candidate) <= max_chars:
                current_line_words.append(word)
                i += 1
            elif len(lines) < max_lines:
                lines.append([word])
                i += 1
            else:
                break

        lines = [ln for ln in lines if ln]
        if not lines:
            i += 1
            continue

        all_words = [w for ln in lines for w in ln]
        line_texts = [
            " ".join(w.get("display_text") or w.get("word", "") for w in ln)
            for ln in lines
        ]

        groups.append({
            "text": "\n".join(line_texts),
            "start": all_words[0].get("start", 0.0),
            "end": all_words[-1].get("end", all_words[-1].get("start", 0.0) + 0.5),
            "words": all_words,
        })

    return groups


# --- Pillow PNG render --------------------------------------------------------

def _load_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_path, size=size)
    except OSError:
        logger.error("[PillowRenderer] Font not found: %s — using fallback", font_path)
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=size)


def _render_subtitle_png(
    text: str,
    font: ImageFont.FreeTypeFont,
    cfg: dict,
    font_size_px: int,
    output_path: str,
) -> None:
    """Render subtitle text onto a transparent 1080x1920 PNG with stroke and shadow."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    lines = text.split("\n")
    line_height_px = int(font_size_px * cfg["line_height"])

    total_text_height = line_height_px * len(lines)
    center_y = (CANVAS_H // 2) + cfg["position_y_offset"]
    start_y = center_y - total_text_height // 2

    stroke_width = cfg["stroke_width"] if cfg["stroke_enabled"] else 0
    stroke_fill = cfg["stroke_color"] if cfg["stroke_enabled"] else None

    if cfg["shadow_enabled"]:
        shadow_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        sr, sg, sb, sa = cfg["shadow_color"]
        shadow_offset_x = cfg["shadow_offset_x"]
        shadow_offset_y = cfg["shadow_offset_y"]
        shadow_blur = cfg["shadow_blur"]

        for i, line in enumerate(lines):
            if not line.strip():
                continue
            y = start_y + i * line_height_px
            if cfg["text_align"] == "center":
                bbox = shadow_draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
                text_width = bbox[2] - bbox[0]
                x = (CANVAS_W - text_width) // 2
            else:
                x = cfg.get("margin_h", 80)

            shadow_draw.text(
                (x + shadow_offset_x, y + shadow_offset_y),
                line,
                font=font,
                fill=(sr, sg, sb, sa),
                stroke_width=stroke_width,
                stroke_fill=(sr, sg, sb, sa),
            )

        if shadow_blur > 0:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))

        img = Image.alpha_composite(img, shadow_layer)
        draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        if not line.strip():
            continue

        y = start_y + i * line_height_px

        if cfg["text_align"] == "center":
            bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
            text_width = bbox[2] - bbox[0]
            x = (CANVAS_W - text_width) // 2
        else:
            x = cfg.get("margin_h", 80)

        draw.text(
            (x, y),
            line,
            font=font,
            fill=cfg["text_color"],
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )

    img.save(output_path, "PNG")


# --- FFmpeg overlay (multi-pass) ----------------------------------------------

def _run_ffmpeg_overlay_multipass(
    video_path: str,
    output_path: str,
    groups: list[dict],
    work_dir: str,
) -> None:
    """
    Overlay subtitle PNGs using multi-pass FFmpeg to avoid file descriptor limits.
    Each pass handles at most MAX_OVERLAYS_PER_PASS overlays.
    """
    if not groups:
        _run_ffmpeg_copy(video_path, output_path)
        return

    total = len(groups)
    passes = (total + MAX_OVERLAYS_PER_PASS - 1) // MAX_OVERLAYS_PER_PASS
    intermediate_paths: list[str] = []

    try:
        current_input = video_path

        for pass_idx in range(passes):
            start_i = pass_idx * MAX_OVERLAYS_PER_PASS
            end_i = min(start_i + MAX_OVERLAYS_PER_PASS, total)
            batch = groups[start_i:end_i]

            is_last_pass = (pass_idx == passes - 1)

            if is_last_pass:
                pass_output = output_path
            else:
                pass_output = os.path.join(work_dir, f"pass_{uuid.uuid4().hex}.mp4")
                intermediate_paths.append(pass_output)

            _run_ffmpeg_overlay_single(current_input, pass_output, batch, is_last_pass)
            current_input = pass_output

    finally:
        for p in intermediate_paths:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


def _run_ffmpeg_overlay_single(
    video_path: str,
    output_path: str,
    groups: list[dict],
    final_pass: bool,
) -> None:
    """Run a single FFmpeg overlay pass for a batch of subtitle PNGs."""
    codec = getattr(settings, "FFMPEG_VIDEO_CODEC", "libx264")
    preset = getattr(settings, "FFMPEG_ENCODE_PRESET", settings.FFMPEG_PRESET)
    hwaccel = getattr(settings, "FFMPEG_HWACCEL", "")

    inputs = ["-i", video_path]
    for group in groups:
        inputs.extend(["-i", group["png_path"]])

    filter_parts = []
    prev_label = "0:v"

    for i, group in enumerate(groups):
        input_idx = i + 1
        out_label = f"v{i}" if i < len(groups) - 1 else "vout"
        start = f"{group['start']:.3f}"
        end = f"{group['end']:.3f}"
        filter_parts.append(
            f"[{prev_label}][{input_idx}:v]overlay=0:0:enable='between(t,{start},{end})'[{out_label}]"
        )
        prev_label = out_label

    filtergraph = ";".join(filter_parts)

    cmd = ["ffmpeg", "-y"]
    if hwaccel:
        cmd.extend(["-hwaccel", hwaccel])
    cmd.extend(inputs)
    cmd.extend(["-filter_complex", filtergraph])
    cmd.extend(["-map", "[vout]", "-map", "0:a?"])
    cmd.extend(["-c:v", codec])

    if codec in ("av1_nvenc", "hevc_nvenc", "h264_nvenc"):
        cmd.extend(["-preset", preset, "-rc", "vbr", "-cq", str(settings.FFMPEG_CRF)])
    else:
        if final_pass:
            cmd.extend(["-preset", preset, "-crf", str(settings.FFMPEG_CRF)])
        else:
            cmd.extend(["-preset", "fast", "-crf", "16"])

    if codec in ("libx264", "h264_nvenc"):
        cmd.extend(["-profile:v", "high"])
    if codec in ("hevc_nvenc", "libx265"):
        cmd.extend(["-pix_fmt", "p010le", "-tag:v", "hvc1"])
    else:
        cmd.extend(["-pix_fmt", "yuv420p"])
    cmd.extend(["-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart"])

    if final_pass:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        cmd.extend([
            "-timecode", "01:00:00:00",
            "-metadata", f"creation_time={now}",
            "-metadata", "encoder=Blackmagic Design DaVinci Resolve",
            "-metadata:s:v", "handler_name=VideoHandler",
            "-metadata:s:v", "encoder=H.265 10-bit",
            "-metadata:s:a", "handler_name=SoundHandler",
        ])

    cmd.append(output_path)

    logger.info(
        "[PillowRenderer] FFmpeg pass: %d inputs, %d overlays, final=%s",
        len(groups) + 1, len(groups), final_pass,
    )
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg overlay render failed: {result.stderr[-800:]}")


def _run_ffmpeg_copy(input_path: str, output_path: str) -> None:
    cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg copy failed: {result.stderr[-400:]}")
