"""Frame-based Caption Template V2 renderer.

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
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import settings
from app.captions.davinci_fingerprint import (
    davinci_timescale_for_rate,
    frame_duration_s,
    has_audio_stream,
    probe_video_rate,
)
from app.captions.v2.templates import CaptionV2Template, get_v2_template

logger = logging.getLogger(__name__)


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


def render_captions_v2(
    video_path: str,
    output_path: str,
    words: list[dict],
    segments: list[dict],
    template_key: str,
) -> str:
    """Render a Caption Template V2 template onto a video."""
    del segments
    template = get_v2_template(template_key)
    normalized_words = _normalize_words(words)

    if not normalized_words:
        logger.warning("[CaptionV2] No words provided, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    video = _probe_video_info(video_path)
    pages = _build_pages(normalized_words, template.layout.max_words_per_page)

    if not pages:
        logger.warning("[CaptionV2] No caption pages generated, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    if video.duration <= 0:
        video.duration = max(page.end for page in pages) + frame_duration_s(video.rate)

    out_dir = os.path.dirname(output_path) or "."
    overlay_path = os.path.join(out_dir, f"caption_overlay_{uuid.uuid4().hex}.mov")

    try:
        _render_overlay_video(overlay_path, pages, video, template)
        _compose_overlay(video_path, overlay_path, output_path, video)
        logger.info(
            "[CaptionV2] Rendered %d pages (%s) -> %s",
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


def _build_pages(words: list[CaptionWord], max_words_per_page: int) -> list[CaptionPage]:
    pages: list[CaptionPage] = []
    step = max(1, max_words_per_page)

    for i in range(0, len(words), step):
        chunk = words[i:i + step]
        if not chunk:
            continue
        pages.append(CaptionPage(words=chunk, start=chunk[0].start, end=chunk[-1].end))

    return pages


def _render_overlay_video(
    overlay_path: str,
    pages: list[CaptionPage],
    video: VideoInfo,
    template: CaptionV2Template,
) -> None:
    font_size_px = _design_font_size_to_px(template.font.design_size, video.width)
    stroke_px = max(0, int(round(font_size_px * template.stroke.width_ratio)))
    font = _load_font(template.font.paths, font_size_px)

    sample_img = Image.new("RGBA", (video.width, video.height), (0, 0, 0, 0))
    sample_draw = ImageDraw.Draw(sample_img)
    for page in pages:
        page.layout = _layout_page(page, sample_draw, font, font_size_px, stroke_px, video, template)

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

    logger.info("[CaptionV2] Rendering overlay video: %d frames @ %s/%s", frame_count, fps_num, fps_den)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        for frame_idx in range(frame_count):
            t = frame_idx / fps
            frame = _render_frame(t, pages, video, template, font, font_size_px, stroke_px)
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
    template: CaptionV2Template,
    font: ImageFont.FreeTypeFont,
    font_size_px: int,
    stroke_px: int,
) -> Image.Image:
    img = Image.new("RGBA", (video.width, video.height), (0, 0, 0, 0))
    page = _page_at_time(pages, t)
    if page is None or not page.layout:
        return img

    active_idx = _active_word_index(page, t)

    shadow_layer = _draw_page(
        page=page,
        video=video,
        template=template,
        font=font,
        font_size_px=font_size_px,
        stroke_px=stroke_px,
        active_idx=active_idx,
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
        font_size_px=font_size_px,
        stroke_px=stroke_px,
        active_idx=active_idx,
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
    template: CaptionV2Template,
) -> list[list[dict[str, Any]]]:
    max_width = video.width * template.layout.max_width_ratio
    letter_spacing_px = font_size_px * template.layout.letter_spacing
    space_width = _measure_text(draw, " ", font, letter_spacing_px, stroke_px)
    lines: list[list[dict[str, Any]]] = [[]]
    current_width = 0.0

    for word_idx, word in enumerate(page.words):
        width = _measure_text(draw, word.text, font, letter_spacing_px, stroke_px)
        add_width = width if not lines[-1] else space_width + width
        if lines[-1] and current_width + add_width > max_width:
            lines.append([])
            current_width = 0.0
            add_width = width
        lines[-1].append({"word": word, "word_idx": word_idx, "width": width})
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
    template: CaptionV2Template,
    font: ImageFont.FreeTypeFont,
    font_size_px: int,
    stroke_px: int,
    active_idx: int,
    shadow: bool,
) -> Image.Image | None:
    if not page.layout:
        return None

    layer = Image.new("RGBA", (video.width, video.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    letter_spacing_px = font_size_px * template.layout.letter_spacing

    if shadow:
        offset_x, offset_y = _shadow_offset(template.shadow.distance, template.shadow.angle)
        fill = _hex_to_rgba(template.shadow.color, template.shadow.alpha)
        stroke_fill = fill
    else:
        offset_x = 0.0
        offset_y = 0.0
        stroke_fill = _hex_to_rgba(template.stroke.color, template.stroke.alpha)

    for line in page.layout:
        for item in line:
            word = item["word"]
            word_idx = item["word_idx"]
            if shadow:
                fill = _hex_to_rgba(template.shadow.color, template.shadow.alpha)
            elif word_idx == active_idx:
                fill = _hex_to_rgba(template.karaoke.active_color, template.fill_alpha)
            elif word_idx < active_idx:
                fill = _hex_to_rgba(template.karaoke.read_color, template.fill_alpha)
            else:
                fill = _hex_to_rgba(template.karaoke.inactive_color, template.fill_alpha)

            _draw_text(
                draw=draw,
                position=(item["x"] + offset_x, item["y"] + offset_y),
                text=word.text,
                font=font,
                fill=fill,
                stroke_width=stroke_px,
                stroke_fill=stroke_fill,
                letter_spacing_px=letter_spacing_px,
            )

    return layer


def _compose_overlay(
    video_path: str,
    overlay_path: str,
    output_path: str,
    video: VideoInfo,
) -> None:
    codec = _target_final_video_codec()
    preset = _target_final_preset(codec)
    hwaccel = getattr(settings, "FFMPEG_HWACCEL", "")
    frame_pad = frame_duration_s(video.rate)
    timescale = davinci_timescale_for_rate(video.rate)
    has_audio = has_audio_stream(video_path)

    filter_parts = [
        "[0:v]setpts=PTS-STARTPTS[vbase]",
        "[1:v]setpts=PTS-STARTPTS,format=rgba[ov]",
        f"[vbase][ov]overlay=0:0:eof_action=pass:format=auto,"
        f"tpad=stop_mode=clone:stop_duration={frame_pad:.6f},setsar=1[vout]",
    ]
    if has_audio:
        filter_parts.append(f"[0:a]asetpts=PTS-STARTPTS,apad=pad_dur={frame_pad * 2:.6f}[aout]")

    cmd = ["ffmpeg", "-y"]
    if hwaccel:
        cmd.extend(["-hwaccel", hwaccel])
    cmd.extend(["-i", video_path, "-i", overlay_path])
    cmd.extend(["-filter_complex", ";".join(filter_parts), "-map", "[vout]"])
    if has_audio:
        cmd.extend(["-map", "[aout]"])
    cmd.extend(["-map_metadata", "-1", "-fflags", "+bitexact", "-c:v", codec])

    if codec in ("av1_nvenc", "hevc_nvenc", "h264_nvenc"):
        cmd.extend(["-preset", preset, "-rc", "vbr", "-cq", str(settings.FFMPEG_CRF)])
    else:
        cmd.extend(["-preset", preset, "-crf", str(settings.FFMPEG_CRF)])
    if codec == "libx265":
        cmd.extend(["-x265-params", "info=0:colorprim=bt709:transfer=bt709:colormatrix=bt709"])
    if codec == "libx264":
        cmd.extend(["-x264-params", "no-info=1"])
    if codec in ("libx264", "h264_nvenc"):
        cmd.extend(["-profile:v", "high"])
    if codec in ("hevc_nvenc", "libx265"):
        cmd.extend(["-pix_fmt", "p010le", "-tag:v", "hvc1"])
    else:
        cmd.extend(["-pix_fmt", "yuv420p"])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
    cmd.extend([
        "-flags:v",
        "+bitexact",
        "-flags:a",
        "+bitexact",
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
        "-movie_timescale",
        str(timescale),
        "-video_track_timescale",
        str(timescale),
        "-timecode",
        "01:00:00:00",
        "-metadata",
        f"creation_time={now}",
        "-metadata",
        "encoder=Blackmagic Design DaVinci Resolve",
        "-metadata:s:v",
        "handler_name=VideoHandler",
        "-metadata:s:v",
        "encoder=H.265 10-bit",
        "-metadata:s:v:0",
        "language=und",
        "-metadata:s:v:0",
        "timecode=01:00:00:00",
        "-metadata:s:d:0",
        "language=eng",
    ])
    if has_audio:
        cmd.extend([
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            "-ar",
            "48000",
            "-metadata:s:a",
            "handler_name=SoundHandler",
            "-metadata:s:a:0",
            "language=und",
        ])
    else:
        cmd.append("-an")
    cmd.append(output_path)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg V2 overlay compose failed: {result.stderr[-800:]}")


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


def _design_font_size_to_px(design_size: float, output_width: int) -> int:
    return max(1, int(round(design_size * output_width / 200.0)))


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

    logger.warning("[CaptionV2] No TrueType caption font found; using PIL default font")
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


def _target_final_video_codec() -> str:
    override = os.getenv("FFMPEG_FINAL_VIDEO_CODEC")
    if override:
        return override
    pipeline_codec = settings.FFMPEG_VIDEO_CODEC
    if pipeline_codec in ("av1_nvenc", "hevc_nvenc", "h264_nvenc"):
        return "hevc_nvenc"
    return "libx265"


def _target_final_preset(codec: str) -> str:
    override = os.getenv("FFMPEG_FINAL_ENCODE_PRESET")
    if override:
        return override
    if codec in ("av1_nvenc", "hevc_nvenc", "h264_nvenc"):
        preset = settings.FFMPEG_ENCODE_PRESET
        return preset if preset.startswith("p") else "p4"
    return settings.FFMPEG_PRESET


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
