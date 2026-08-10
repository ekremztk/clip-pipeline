"""
Caption renderer dispatcher.

- clean: legacy Pillow PNG overlay renderer
- Caption Template V2: frame-based transparent overlay video renderer
- legacy ASS templates: kept as a fallback for old jobs
"""
import logging
import os
import subprocess
import uuid
from typing import Optional

from app.config import settings
from app.captions.davinci_fingerprint import has_audio_stream
from app.ffmpeg_encode import append_pipeline_audio_encode_args, append_pipeline_video_encode_args
from app.captions.v2.renderer import render_captions_v2
from app.captions.v2.templates import is_v2_template
from app.captions.v3.renderer import render_captions_v3
from app.captions.v3.templates import is_v3_template

logger = logging.getLogger(__name__)

# Templates that use the legacy Pillow PNG overlay renderer.
PILLOW_TEMPLATES = {"clean"}

CANVAS_W = 1080
CANVAS_H = 1920

# Pipeline key → template config
# Colors in ASS format: &HAABBGGRR  (alpha, blue, green, red — note: BGR, not RGB)
# Alpha: 0x00 = fully opaque, 0xFF = fully transparent
TEMPLATE_CONFIGS: dict[str, dict] = {
    "clean": {
        "font": "Montserrat",
        "bold": True,
        "fontsize": 85,
        "primary_color": "&H00FFFFFF",   # white text
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",   # black stroke
        "back_color": "&H00000000",      # no shadow color
        "border_style": 1,
        "outline": 8,                    # matches editor stroke width 8 outsideOnly
        "shadow": 0,                     # editor shadow disabled
        "alignment": 2,                  # bottom center
        "margin_v": 610,
        "margin_h": 80,
        "text_transform": "capitalize",
        "karaoke": False,
        "words_per_group": 4,
        "max_lines": 2,
        "max_chars_per_line": 18,
        "fade": (0, 0),
    },
    "hormozi": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 84,
        "primary_color": "&H0000E5FF",   # yellow — spoken/highlighted (BGR of #FFE500)
        "secondary_color": "&H00FFFFFF", # white — unspoken
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 8,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 610,
        "margin_h": 100,
        "text_transform": "uppercase",
        "karaoke": True,
        "words_per_group": 4,
        "fade": (0, 0),
    },
    "outline": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 86,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 6,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 610,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 5,
        "fade": (0, 0),
    },
    "pill": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 80,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",      # 50% transparent black box
        "border_style": 3,               # opaque box fill
        "outline": 30,                   # box padding
        "shadow": 0,
        "alignment": 2,
        "margin_v": 610,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 4,
        "fade": (0, 0),
    },
    "neon": {
        "font": "Open Sans",
        "bold": False,
        "fontsize": 96,
        "primary_color": "&H00FFFFFF",   # white text
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00FFFF00",   # cyan glow border (BGR of #00FFFF)
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 8,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 610,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 3,
        "fade": (0, 0),
    },
    "cinematic": {
        "font": "Open Sans",
        "bold": False,
        "fontsize": 74,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",      # opaque black box
        "border_style": 3,
        "outline": 20,                   # box padding
        "shadow": 0,
        "alignment": 2,
        "margin_v": 180,                 # near bottom
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 3,
        "fade": (0, 0),
    },
    "bold_pop": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 100,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 4,
        "shadow": 3,
        "alignment": 2,
        "margin_v": 610,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 1,            # one word at a time
        "fade": (80, 80),
    },
    "fire": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 84,
        "primary_color": "&H003568FF",   # orange (BGR of #FF6835)
        "secondary_color": "&H003568FF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 6,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 610,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 4,
        "fade": (0, 0),
    },
}


def render_captions(
    video_path: str,
    output_path: str,
    words: list[dict],
    segments: list[dict],
    template_key: str = "clean",
    watermark_path: str | None = None,
) -> str:
    """
    Burn captions onto video.

    Dispatches to the renderer that owns the requested template.

    Args:
        video_path: Path to input video (9:16, 1080x1920)
        output_path: Path to output captioned MP4
        words: Word-level timestamps from Deepgram [{word, start, end, ...}]
        segments: Sentence segments (kept for API compatibility, unused internally)
        template_key: One of the pipelineKey values
        watermark_path: Local PNG resolved from the job's channel by S10, or
            None. Chosen upstream on purpose — this layer must not be able to
            pick a channel's mark, only to burn the one it was handed. Only the
            frame-based engines honour it; the Pillow and ASS paths ignore it.

    Returns: output_path
    """
    if is_v3_template(template_key):
        return render_captions_v3(
            video_path, output_path, words, segments, template_key, watermark_path
        )

    if is_v2_template(template_key):
        return render_captions_v2(
            video_path, output_path, words, segments, template_key, watermark_path
        )

    if template_key in PILLOW_TEMPLATES:
        from app.captions.renderer_pillow import render_captions as render_pillow
        return render_pillow(video_path, output_path, words, segments, template_key)

    return _render_ass(video_path, output_path, words, segments, template_key)


def _render_ass(
    video_path: str,
    output_path: str,
    words: list[dict],
    segments: list[dict],
    template_key: str,
) -> str:
    """ASS-based render for karaoke templates (hormozi, bold_pop, etc.)."""
    cfg = TEMPLATE_CONFIGS.get(template_key) or TEMPLATE_CONFIGS["clean"]

    if not words:
        logger.warning("[CaptionRenderer] No words provided, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    groups = _build_word_groups(
        words,
        cfg["words_per_group"],
        max_lines=cfg.get("max_lines", 0),
        max_chars_per_line=cfg.get("max_chars_per_line", 0),
    )

    if not groups:
        logger.warning("[CaptionRenderer] No word groups generated, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    ass_content = _build_ass(groups, cfg)

    out_dir = os.path.dirname(output_path) or "."
    ass_path = os.path.join(out_dir, f"caps_{uuid.uuid4().hex}.ass")

    try:
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

        _run_ffmpeg_ass(video_path, output_path, ass_path)
        logger.info(
            "[CaptionRenderer] Rendered %d groups (%s) -> %s",
            len(groups), template_key, output_path,
        )
    finally:
        if os.path.exists(ass_path):
            try:
                os.remove(ass_path)
            except Exception:
                pass

    return output_path


# ─── Word grouping ─────────────────────────────────────────────────────────────

def _build_word_groups(
    words: list[dict],
    n: int,
    max_lines: int = 0,
    max_chars_per_line: int = 0,
) -> list[dict]:
    """
    Build subtitle events from word list.

    If max_lines and max_chars_per_line are set, uses line-aware wrapping:
    fills lines up to max_chars_per_line, up to max_lines lines per event,
    then starts a new event. Uses ASS \\N for hard line breaks.

    Otherwise falls back to simple N-word chunking.
    """
    if max_lines > 0 and max_chars_per_line > 0:
        return _build_groups_by_chars(words, max_lines, max_chars_per_line)

    groups = []
    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        if not chunk:
            continue
        text_parts = [w.get("punctuated_word") or w.get("word", "") for w in chunk]
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
    """
    Build subtitle events with character-per-line and max-lines limits.
    Fills line 1 up to max_chars, overflows into line 2, then starts new event.
    Lines joined with ASS hard line break (\\N).
    """
    groups: list[dict] = []
    i = 0

    while i < len(words):
        lines: list[list[dict]] = [[]]  # lines[0] = first line words, lines[1] = second

        while i < len(words):
            word = words[i]
            word_text = word.get("punctuated_word") or word.get("word", "")
            current_line_words = lines[-1]
            current_line_text = " ".join(
                w.get("punctuated_word") or w.get("word", "") for w in current_line_words
            )
            candidate = (current_line_text + " " + word_text).strip()

            if len(candidate) <= max_chars:
                current_line_words.append(word)
                i += 1
            elif len(lines) < max_lines:
                # Overflow to next line
                lines.append([word])
                i += 1
            else:
                # Event full — start new event
                break

        # Drop empty trailing lines
        lines = [ln for ln in lines if ln]
        if not lines:
            i += 1
            continue

        all_words = [w for ln in lines for w in ln]
        line_texts = [
            " ".join(w.get("punctuated_word") or w.get("word", "") for w in ln)
            for ln in lines
        ]

        groups.append({
            "text": "\\N".join(line_texts),
            "start": all_words[0].get("start", 0.0),
            "end": all_words[-1].get("end", all_words[-1].get("start", 0.0) + 0.5),
            "words": all_words,
        })

    return groups


# ─── ASS generation ────────────────────────────────────────────────────────────

def _build_ass(groups: list[dict], cfg: dict) -> str:
    """Build complete ASS file content from word groups and template config."""
    bold_flag = -1 if cfg.get("bold") else 0
    fade_in, fade_out = cfg.get("fade", (0, 0))

    style_line = (
        f"Style: Default,"
        f"{cfg['font']},{cfg['fontsize']},"
        f"{cfg['primary_color']},{cfg['secondary_color']},"
        f"{cfg['outline_color']},{cfg['back_color']},"
        f"{bold_flag},0,0,0,"
        f"100,100,0,0,"
        f"{cfg['border_style']},{cfg['outline']},{cfg['shadow']},"
        f"{cfg['alignment']},"
        f"{cfg['margin_h']},{cfg['margin_h']},{cfg['margin_v']},"
        f"1"
    )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {CANVAS_W}\n"
        f"PlayResY: {CANVAS_H}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_line}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = [header]
    fade_prefix = f"{{\\fad({fade_in},{fade_out})}}" if (fade_in or fade_out) else ""

    for group in groups:
        start = _ass_time(group["start"])
        end = _ass_time(group["end"])

        if cfg.get("karaoke") and group.get("words"):
            text_body = _build_karaoke_text(group["words"], cfg.get("text_transform", "none"))
        else:
            raw = _apply_transform(group["text"], cfg.get("text_transform", "none"))
            parts = raw.split("\\N")
            text_body = "\\N".join(_escape_ass(p) for p in parts)

        text = fade_prefix + text_body
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return "\n".join(lines)


def _build_karaoke_text(words: list[dict], transform: str) -> str:
    """
    Build ASS karaoke line: {\\kXX}WORD for each word.
    Duration = time until next word starts (keeps sync tight across gaps).
    Primary color = spoken/highlighted, SecondaryColour = unspoken.
    """
    parts = []
    for i, w in enumerate(words):
        w_start = w.get("start", 0.0)
        w_end = w.get("end", w_start + 0.3)

        if i < len(words) - 1:
            next_start = words[i + 1].get("start", w_end)
            duration_cs = max(1, round((next_start - w_start) * 100))
        else:
            duration_cs = max(1, round((w_end - w_start) * 100))

        word_text = _apply_transform(
            w.get("punctuated_word") or w.get("word", ""), transform
        )
        parts.append(f"{{\\k{duration_cs}}}{_escape_ass(word_text)}")

    return " ".join(parts)


# ─── FFmpeg runners ────────────────────────────────────────────────────────────

MONTSERRAT_FONTS_DIR = "/usr/share/fonts/truetype/montserrat"


def _run_ffmpeg_ass(input_path: str, output_path: str, ass_path: str) -> None:
    """Burn ASS subtitles via FFmpeg using the shared pipeline encode profile."""
    safe_path = ass_path.replace("\\", "/").replace(":", "\\:")
    safe_fonts = MONTSERRAT_FONTS_DIR.replace(":", "\\:")
    has_audio = has_audio_stream(input_path)
    video_filter = f"ass={safe_path}:fontsdir={safe_fonts},setsar=1"
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", video_filter,
        "-map", "0:v:0",
    ]
    if has_audio:
        cmd.extend(["-map", "0:a:0"])
    append_pipeline_video_encode_args(cmd)
    cmd.extend([
        "-color_range", "tv",
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        "-movflags", "+faststart",
    ])
    append_pipeline_audio_encode_args(cmd, has_audio=has_audio)
    cmd.append(output_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg ASS render failed: {result.stderr[-800:]}")
    if result.stderr:
        stderr_lower = result.stderr.lower()
        if "font" in stderr_lower or "glyph" in stderr_lower or "libass" in stderr_lower:
            logger.warning("[CaptionRenderer] FFmpeg font warnings: %s", result.stderr[-600:])


def _run_ffmpeg_copy(input_path: str, output_path: str) -> None:
    """Copy video without re-encode (fallback when no captions to burn)."""
    cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg copy failed: {result.stderr[-400:]}")


# ─── Text helpers ──────────────────────────────────────────────────────────────

def _ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format H:MM:SS.cs"""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    """Escape characters that have special meaning in ASS dialogue text."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("\n", "\\N")
    return text


def _apply_transform(text: str, transform: Optional[str]) -> str:
    if transform == "uppercase":
        return text.upper()
    if transform == "lowercase":
        return text.lower()
    if transform == "capitalize":
        return text.title()
    return text
