"""Frame-based Caption Template V3 renderer.

The engine renders a transparent caption overlay video with Pillow, then
composites that overlay onto the source MP4 in one FFmpeg pass.
"""
from __future__ import annotations

import json
import logging
import math
import os
import string
import subprocess
import uuid
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import settings
from app.captions.davinci_fingerprint import frame_duration_s, has_audio_stream, probe_video_rate
from app.ffmpeg_encode import append_pipeline_audio_encode_args, append_pipeline_video_encode_args
from app.captions.v3.templates import CaptionV3Template, get_v3_template
from app.captions.watermark import load_watermark_layer

logger = logging.getLogger(__name__)
FontCache = dict[int, ImageFont.ImageFont]


@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    rate: Fraction


@dataclass
class CaptionWord:
    text: str
    start: float
    end: float


@dataclass
class CaptionPage:
    words: list[CaptionWord]
    start: float
    end: float
    layout: list[list[dict[str, Any]]] | None = None
    # Resolved during layout. A page that would overflow the frame on one line
    # gets its own smaller font rather than wrapping to a second line, so these
    # are per-page rather than global.
    font_size_px: int = 0
    stroke_px: int = 0


def render_captions_v3(
    video_path: str,
    output_path: str,
    words: list[dict],
    segments: list[dict],
    template_key: str,
    watermark_path: str | None = None,
) -> str:
    """Render a Caption Template V3 template onto a video."""
    del segments
    template = get_v3_template(template_key)
    normalized_words = _normalize_words(words)

    if not normalized_words:
        logger.warning("[CaptionV3] No words provided, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    video = _probe_video_info(video_path)
    pages = _build_pages(normalized_words, template.layout)

    if not pages:
        logger.warning("[CaptionV3] No caption pages generated, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    if video.duration <= 0:
        video.duration = max(page.end for page in pages) + frame_duration_s(video.rate)

    out_dir = os.path.dirname(output_path) or "."
    overlay_path = os.path.join(out_dir, f"caption_overlay_{uuid.uuid4().hex}.mov")

    try:
        _render_overlay_video(overlay_path, pages, video, template, watermark_path)
        _compose_overlay(video_path, overlay_path, output_path, video)
        logger.info(
            "[CaptionV3] Rendered %d pages (%s) -> %s",
            len(pages), template_key, output_path,
        )
    finally:
        if os.path.exists(overlay_path):
            try:
                os.remove(overlay_path)
            except Exception:
                pass

    return output_path


def _probe_video_info(path: str) -> VideoInfo:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,duration:format=duration",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe video info failed: {result.stderr[-400:]}")

    data = json.loads(result.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    width = int(stream.get("width") or 1080)
    height = int(stream.get("height") or 1920)
    duration = _safe_float(stream.get("duration")) or _safe_float((data.get("format") or {}).get("duration")) or 0.0
    rate = probe_video_rate(path)
    return VideoInfo(width=width, height=height, duration=max(0.0, duration), rate=rate)


def _normalize_words(words: list[dict]) -> list[CaptionWord]:
    normalized: list[CaptionWord] = []
    strip_chars = string.punctuation.replace("'", "")

    for item in words:
        raw = str(item.get("punctuated_word") or item.get("word") or "").strip()
        text = raw.strip(strip_chars).strip()
        if not text:
            continue

        start = _safe_float(item.get("start"))
        end = _safe_float(item.get("end"))
        if start is None:
            continue
        if end is None or end <= start:
            end = start + 0.25

        normalized.append(CaptionWord(text=text, start=start, end=end))

    return normalized


def _build_pages(words: list[CaptionWord], layout: Any) -> list[CaptionPage]:
    """Pack words into pages under both a word cap and a character budget.

    V2 sliced a fixed number of words per page, which makes the caption width
    swing with word length. Here the character budget closes a page early when
    the words are long, so every page lands at a similar width — which is what
    makes a single centred line hold still instead of jumping about.
    """
    pages: list[CaptionPage] = []
    max_words = max(1, layout.max_words_per_page)
    max_chars = max(1, getattr(layout, "max_chars_per_page", 24))

    chunk: list[CaptionWord] = []
    chars = 0

    for word in words:
        length = len(word.text)
        # +1 for the space this word would sit behind.
        projected = chars + length + (1 if chunk else 0)
        if chunk and (len(chunk) >= max_words or projected > max_chars):
            pages.append(CaptionPage(words=chunk, start=chunk[0].start, end=chunk[-1].end))
            chunk = []
            chars = 0
            projected = length

        chunk.append(word)
        chars = projected

    if chunk:
        pages.append(CaptionPage(words=chunk, start=chunk[0].start, end=chunk[-1].end))

    return pages


def _render_overlay_video(
    overlay_path: str,
    pages: list[CaptionPage],
    video: VideoInfo,
    template: CaptionV3Template,
    watermark_path: str | None = None,
) -> None:
    font_size_px = _capcut_font_size_to_px(template.font.capcut_size, video.width)
    stroke_px = max(0, int(round(font_size_px * template.stroke.width_ratio)))
    font = _load_font(template.font.paths, font_size_px)
    font_cache: FontCache = {font_size_px: font}

    sample_img = Image.new("RGBA", (video.width, video.height), (0, 0, 0, 0))
    sample_draw = ImageDraw.Draw(sample_img)
    for page in pages:
        page.layout = _layout_page(
            page, sample_draw, font, font_size_px, stroke_px, video, template, font_cache
        )

    # Resolved once for the whole clip: the decision was made in S10 and this
    # is only the file it handed over.
    mark = load_watermark_layer(watermark_path, video.width, video.height)

    fps_num = video.rate.numerator if video.rate.numerator > 0 else 30
    fps_den = video.rate.denominator if video.rate.denominator > 0 else 1
    fps = fps_num / fps_den
    frame_count = max(1, int(math.ceil(video.duration * fps)) + 1)

    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{video.width}x{video.height}",
        "-r",
        f"{fps_num}/{fps_den}",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "qtrle",
        "-pix_fmt",
        "argb",
        overlay_path,
    ]

    logger.info("[CaptionV3] Rendering overlay video: %d frames @ %s/%s", frame_count, fps_num, fps_den)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        for frame_idx in range(frame_count):
            t = frame_idx / fps
            frame = _render_frame(
                t, pages, video, template, font, font_cache, font_size_px, stroke_px, mark
            )
            proc.stdin.write(frame.tobytes("raw", "RGBA"))
        proc.stdin.close()
        stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        return_code = proc.wait(timeout=600)
    except Exception:
        proc.kill()
        raise

    if return_code != 0:
        raise RuntimeError(f"FFmpeg overlay video render failed: {stderr[-800:]}")


def _render_frame(
    t: float,
    pages: list[CaptionPage],
    video: VideoInfo,
    template: CaptionV3Template,
    font: ImageFont.FreeTypeFont,
    font_cache: FontCache,
    font_size_px: int,
    stroke_px: int,
    mark: Image.Image | None = None,
) -> Image.Image:
    img = Image.new("RGBA", (video.width, video.height), (0, 0, 0, 0))

    # Goes down first so captions sit over it, and before the early return so
    # the mark still shows across the gaps where nobody is speaking.
    if mark is not None:
        img = Image.alpha_composite(img, mark)

    page = _page_at_time(pages, t)
    if page is None or not page.layout:
        return img

    active_idx = _active_word_index(page, t)

    # A shrunk page carries its own size; everything downstream must measure
    # against that, not the template's nominal size, or the words drift apart.
    if page.font_size_px:
        font_size_px = page.font_size_px
        stroke_px = page.stroke_px
        font = _font_for_size(template, font_size_px, font_cache)

    shadow_layer = _draw_page(
        page=page,
        video=video,
        template=template,
        font=font,
        font_cache=font_cache,
        font_size_px=font_size_px,
        stroke_px=stroke_px,
        active_idx=active_idx,
        t=t,
        shadow=True,
    )
    if shadow_layer is not None:
        blur_radius = max(0.0, template.shadow.smoothing * 10.0)
        if blur_radius > 0:
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        img = Image.alpha_composite(img, shadow_layer)

    text_layer = _draw_page(
        page=page,
        video=video,
        template=template,
        font=font,
        font_cache=font_cache,
        font_size_px=font_size_px,
        stroke_px=stroke_px,
        active_idx=active_idx,
        t=t,
        shadow=False,
    )
    return Image.alpha_composite(img, text_layer)


def _layout_page(
    page: CaptionPage,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    font_size_px: int,
    stroke_px: int,
    video: VideoInfo,
    template: CaptionV3Template,
    font_cache: FontCache | None = None,
) -> list[list[dict[str, Any]]]:
    max_width = video.width * template.layout.max_width_ratio

    if getattr(template.layout, "single_line", False):
        # One line, always. When the words do not fit, the page gets a smaller
        # font instead of a second line — wrapping is what V2 does and is
        # exactly the behaviour this style is meant to drop.
        font_size_px, stroke_px, font = _fit_single_line(
            page, draw, font, font_size_px, stroke_px, max_width, template, font_cache
        )

    page.font_size_px = font_size_px
    page.stroke_px = stroke_px

    letter_spacing_px = font_size_px * template.layout.letter_spacing
    layout_stroke_px = 0
    space_width = _word_gap_px(font_size_px, template)
    lines: list[list[dict[str, Any]]] = [[]]
    current_width = 0.0
    max_words_per_line = max(1, template.layout.max_words_per_line)
    allow_wrap = not getattr(template.layout, "single_line", False)

    for word_idx, word in enumerate(page.words):
        text = _caption_text(word.text, template)
        width = _measure_text(draw, text, font, letter_spacing_px, layout_stroke_px)
        add_width = width if not lines[-1] else space_width + width
        if allow_wrap and lines[-1] and (len(lines[-1]) >= max_words_per_line or current_width + add_width > max_width):
            lines.append([])
            current_width = 0.0
            add_width = width
        lines[-1].append({"word": word, "word_idx": word_idx, "text": text, "width": width})
        current_width += add_width

    lines = [line for line in lines if line]
    bbox = draw.textbbox((0, 0), "Ag", font=font, stroke_width=stroke_px)
    text_height = bbox[3] - bbox[1]
    line_height = text_height + (font_size_px * template.layout.line_spacing)
    total_height = line_height * len(lines)
    center_x = (video.width / 2) + (template.layout.transform_x * video.width)
    center_y = (video.height / 2) - (template.layout.transform_y * video.height)
    start_y = center_y - (total_height / 2)

    layout_lines: list[list[dict[str, Any]]] = []
    for line_idx, line in enumerate(lines):
        line_width = sum(item["width"] for item in line) + space_width * max(0, len(line) - 1)
        if template.layout.align == "center":
            x = center_x - (line_width / 2)
        elif template.layout.align == "right":
            x = center_x + (max_width / 2) - line_width
        else:
            x = center_x - (max_width / 2)
        y = start_y + (line_idx * line_height)

        laid_line: list[dict[str, Any]] = []
        cursor_x = x
        for item in line:
            laid_line.append({**item, "x": cursor_x, "y": y})
            cursor_x += item["width"] + space_width
        layout_lines.append(laid_line)

    return layout_lines


def _draw_page(
    page: CaptionPage,
    video: VideoInfo,
    template: CaptionV3Template,
    font: ImageFont.FreeTypeFont,
    font_cache: FontCache,
    font_size_px: int,
    stroke_px: int,
    active_idx: int,
    t: float,
    shadow: bool,
) -> Image.Image | None:
    if not page.layout:
        return None

    layer = Image.new("RGBA", (video.width, video.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    letter_spacing_px = font_size_px * template.layout.letter_spacing
    max_width = video.width * template.layout.max_width_ratio
    center_x = (video.width / 2) + (template.layout.transform_x * video.width)
    base_bbox = draw.textbbox((0, 0), "Ag", font=font, stroke_width=stroke_px)
    # Vertical midpoint of the drawn ink, not its height. The pop-scale has to
    # grow a word around its own centre; matching heights instead of centres
    # leaves the top edge pinned and pushes the whole word downwards, because
    # the bbox's top gap grows with the font size too.
    base_mid_y = (base_bbox[1] + base_bbox[3]) / 2
    space_width = _word_gap_px(font_size_px, template)

    if shadow:
        offset_x, offset_y = _shadow_offset(template.shadow.distance, template.shadow.angle)
        fill = _hex_to_rgba(template.shadow.color, template.shadow.alpha)
        stroke_fill = fill
    else:
        offset_x = 0.0
        offset_y = 0.0
        stroke_fill = _hex_to_rgba(template.stroke.color, template.stroke.alpha)

    for line in page.layout:
        entries: list[dict[str, Any]] = []
        for item in line:
            word_idx = item["word_idx"]
            scale = _word_scale(page, word_idx, active_idx, t, template)
            scaled_font_size = max(1, int(round(font_size_px * scale)))
            scaled_font = _font_for_size(template, scaled_font_size, font_cache)
            scaled_stroke_px = max(0, int(round(stroke_px * scale)))
            scaled_letter_spacing_px = letter_spacing_px * scale
            text = item.get("text") or _caption_text(item["word"].text, template)
            width = _measure_text(draw, text, scaled_font, scaled_letter_spacing_px, 0)
            text_bbox = draw.textbbox((0, 0), "Ag", font=scaled_font, stroke_width=scaled_stroke_px)
            text_height = text_bbox[3] - text_bbox[1]
            entries.append(
                {
                    "text": text,
                    "word_idx": word_idx,
                    "font": scaled_font,
                    "stroke_px": scaled_stroke_px,
                    "letter_spacing_px": scaled_letter_spacing_px,
                    "width": width,
                    "height": text_height,
                    "mid_y": (text_bbox[1] + text_bbox[3]) / 2,
                    "base_y": item["y"],
                }
            )

        line_width = sum(entry["width"] for entry in entries) + space_width * max(0, len(entries) - 1)
        if template.layout.align == "center":
            cursor_x = center_x - (line_width / 2)
        elif template.layout.align == "right":
            cursor_x = center_x + (max_width / 2) - line_width
        else:
            cursor_x = center_x - (max_width / 2)

        for entry in entries:
            word_idx = entry["word_idx"]
            if shadow:
                fill = _hex_to_rgba(template.shadow.color, template.shadow.alpha)
            elif word_idx == active_idx:
                fill = _hex_to_rgba(template.karaoke.active_color, template.fill_alpha)
            elif word_idx < active_idx:
                fill = _hex_to_rgba(template.karaoke.read_color, template.fill_alpha)
            else:
                fill = _hex_to_rgba(template.karaoke.inactive_color, template.fill_alpha)

            cursor_y = entry["base_y"] + (base_mid_y - entry["mid_y"])
            _draw_text(
                draw=draw,
                position=(cursor_x + offset_x, cursor_y + offset_y),
                text=entry["text"],
                font=entry["font"],
                fill=fill,
                stroke_width=entry["stroke_px"],
                stroke_fill=stroke_fill,
                letter_spacing_px=entry["letter_spacing_px"],
            )
            cursor_x += entry["width"] + space_width

    return layer


def _fit_single_line(
    page: CaptionPage,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    font_size_px: int,
    stroke_px: int,
    max_width: float,
    template: CaptionV3Template,
    font_cache: FontCache | None,
) -> tuple[int, int, ImageFont.FreeTypeFont]:
    """Return the largest font size at which this page fits on one line."""

    def measure_at(f: ImageFont.FreeTypeFont, size: int) -> float:
        letter_spacing_px = size * template.layout.letter_spacing
        gap = _word_gap_px(size, template)
        total = 0.0
        for idx, word in enumerate(page.words):
            total += _measure_text(draw, _caption_text(word.text, template), f, letter_spacing_px, 0)
            if idx:
                total += gap
        return total

    width = measure_at(font, font_size_px)
    if width <= 0 or width <= max_width:
        return font_size_px, stroke_px, font

    floor = max(0.05, getattr(template.layout, "min_shrink_scale", 0.72))
    scale = max(floor, max_width / width)
    new_size = max(1, int(round(font_size_px * scale)))
    if new_size >= font_size_px:
        return font_size_px, stroke_px, font

    new_stroke = max(0, int(round(stroke_px * scale)))
    if font_cache is not None:
        new_font = _font_for_size(template, new_size, font_cache)
    else:
        new_font = _load_font(template.font.paths, new_size)
    return new_size, new_stroke, new_font


def _caption_text(text: str, template: CaptionV3Template) -> str:
    value = text.strip()
    if template.font.uppercase:
        value = value.upper()
    return value


def _font_for_size(template: CaptionV3Template, size: int, font_cache: FontCache) -> ImageFont.ImageFont:
    if size not in font_cache:
        font_cache[size] = _load_font(template.font.paths, size)
    return font_cache[size]


def _word_scale(page: CaptionPage, word_idx: int, active_idx: int, t: float, template: CaptionV3Template) -> float:
    if word_idx != active_idx:
        return 1.0

    word = page.words[word_idx]
    elapsed = max(0.0, t - word.start)
    peak = max(1.0, template.karaoke.active_scale)
    if peak <= 1.001:
        return 1.0

    pop_in = max(0.001, template.karaoke.pop_in_duration)
    pop_out = max(0.001, template.karaoke.pop_out_duration)
    if elapsed < pop_in:
        progress = elapsed / pop_in
        return 1.0 + ((peak - 1.0) * _ease_out_cubic(progress))

    if elapsed < pop_in + pop_out:
        progress = (elapsed - pop_in) / pop_out
        return 1.0 + ((peak - 1.0) * (1.0 - _ease_in_out_cubic(progress)))

    return 1.0


def _ease_out_cubic(progress: float) -> float:
    p = max(0.0, min(1.0, progress))
    return 1.0 - ((1.0 - p) ** 3)


def _ease_in_out_cubic(progress: float) -> float:
    p = max(0.0, min(1.0, progress))
    if p < 0.5:
        return 4.0 * p * p * p
    return 1.0 - ((-2.0 * p + 2.0) ** 3) / 2.0


def _compose_overlay(
    video_path: str,
    overlay_path: str,
    output_path: str,
    video: VideoInfo,
) -> None:
    hwaccel = getattr(settings, "FFMPEG_HWACCEL", "")
    has_audio = has_audio_stream(video_path)

    filter_parts = [
        "[0:v]setpts=PTS-STARTPTS[vbase]",
        "[1:v]setpts=PTS-STARTPTS,format=rgba[ov]",
        f"[vbase][ov]overlay=0:0:eof_action=pass:format=auto,"
        f"setsar=1[vout]",
    ]
    if has_audio:
        filter_parts.append("[0:a]asetpts=PTS-STARTPTS[aout]")

    cmd = ["ffmpeg", "-y"]
    if hwaccel:
        cmd.extend(["-hwaccel", hwaccel])
    cmd.extend(["-i", video_path, "-i", overlay_path])
    cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", "[vout]"])
    if has_audio:
        cmd.extend(["-map", "[aout]"])
    append_pipeline_video_encode_args(cmd)
    cmd.extend([
        "-color_range",
        "tv",
        "-colorspace",
        "bt709",
        "-color_trc",
        "bt709",
        "-color_primaries",
        "bt709",
        "-movflags",
        "+faststart",
    ])
    append_pipeline_audio_encode_args(cmd, has_audio=has_audio)
    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg V3 overlay compose failed: {result.stderr[-800:]}")


def _page_at_time(pages: list[CaptionPage], t: float) -> CaptionPage | None:
    for page in pages:
        if page.start <= t <= page.end:
            return page
    return None


def _active_word_index(page: CaptionPage, t: float) -> int:
    for idx, word in enumerate(page.words):
        if idx < len(page.words) - 1:
            next_start = page.words[idx + 1].start
            if word.start <= t < next_start:
                return idx
        elif word.start <= t <= word.end:
            return idx
    if t < page.words[0].start:
        return 0
    return len(page.words) - 1


def _draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    stroke_width: int,
    stroke_fill: tuple[int, int, int, int],
    letter_spacing_px: float,
) -> None:
    if abs(letter_spacing_px) < 0.01:
        draw.text(
            position,
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return

    x, y = position
    for char in text:
        draw.text(
            (x, y),
            char,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=stroke_width)
        x += (bbox[2] - bbox[0]) + letter_spacing_px


def _measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    letter_spacing_px: float,
    stroke_px: int,
) -> float:
    if not text:
        return 0.0
    if abs(letter_spacing_px) < 0.01:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_px)
        return float(bbox[2] - bbox[0])

    width = 0.0
    for char in text:
        bbox = draw.textbbox((0, 0), char, font=font, stroke_width=stroke_px)
        width += (bbox[2] - bbox[0]) + letter_spacing_px
    return max(0.0, width - letter_spacing_px)


def _word_gap_px(font_size_px: int, template: CaptionV3Template) -> float:
    return max(0.0, font_size_px * template.layout.word_gap_ratio)


def _capcut_font_size_to_px(capcut_size: float, output_width: int) -> int:
    return max(1, int(round(capcut_size * output_width / 200.0)))


def _shadow_offset(distance: float, angle_degrees: float) -> tuple[float, float]:
    radians = math.radians(angle_degrees)
    return math.cos(radians) * distance, math.sin(radians) * distance


def _load_font(paths: tuple[str, ...], size: int) -> ImageFont.ImageFont:
    for path in paths:
        try:
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size=size)
        except OSError:
            continue

    logger.warning("[CaptionV3] No TrueType caption font found; using PIL default font")
    return ImageFont.load_default()


def _hex_to_rgba(hex_color: str, alpha: float) -> tuple[int, int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    a = max(0, min(255, int(round(alpha * 255))))
    return r, g, b, a


def _run_ffmpeg_copy(input_path: str, output_path: str) -> None:
    cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg copy failed: {result.stderr[-400:]}")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
