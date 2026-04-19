"""
Caption renderer v2 — ASS subtitle format burned via FFmpeg.

Replaces drawtext-based renderer. Key improvements:
  - Automatic word wrap via margins (no overflow at any line length)
  - True karaoke via \\k tags (hormozi: active word highlights, others white)
  - Fade in/out via \\fad() override
  - bold_pop: one word at a time with fade
  - No new dependencies — ASS generated as plain text

render_captions() signature is unchanged.
"""
import logging
import os
import subprocess
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

CANVAS_W = 1080
CANVAS_H = 1920

# Pipeline key → template config
# Colors in ASS format: &HAABBGGRR  (alpha, blue, green, red — note: BGR, not RGB)
# Alpha: 0x00 = fully opaque, 0xFF = fully transparent
TEMPLATE_CONFIGS: dict[str, dict] = {
    "clean": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 68,
        "primary_color": "&H00FFFFFF",   # white
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",   # black stroke
        "back_color": "&H00000000",
        "border_style": 1,               # outline mode
        "outline": 8,
        "shadow": 0,
        "alignment": 2,                  # bottom center
        "margin_v": 380,
        "margin_h": 100,
        "text_transform": "capitalize",
        "karaoke": False,
        "words_per_group": 4,
        "fade": (150, 100),
    },
    "hormozi": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 72,
        "primary_color": "&H0000E5FF",   # yellow — spoken/highlighted (BGR of #FFE500)
        "secondary_color": "&H00FFFFFF", # white — unspoken
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 8,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 380,
        "margin_h": 100,
        "text_transform": "uppercase",
        "karaoke": True,
        "words_per_group": 4,
        "fade": (0, 0),
    },
    "outline": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 76,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 6,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 380,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 5,
        "fade": (0, 0),
    },
    "pill": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 68,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",      # 50% transparent black box
        "border_style": 3,               # opaque box fill
        "outline": 30,                   # box padding
        "shadow": 0,
        "alignment": 2,
        "margin_v": 380,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 4,
        "fade": (150, 100),
    },
    "neon": {
        "font": "Open Sans",
        "bold": False,
        "fontsize": 88,
        "primary_color": "&H00FFFFFF",   # white text
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00FFFF00",   # cyan glow border (BGR of #00FFFF)
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 8,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 380,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 3,
        "fade": (0, 0),
    },
    "cinematic": {
        "font": "Open Sans",
        "bold": False,
        "fontsize": 64,
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
        "fontsize": 92,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 4,
        "shadow": 3,
        "alignment": 2,
        "margin_v": 380,
        "margin_h": 100,
        "text_transform": "none",
        "karaoke": False,
        "words_per_group": 1,            # one word at a time
        "fade": (80, 80),
    },
    "fire": {
        "font": "Open Sans",
        "bold": True,
        "fontsize": 72,
        "primary_color": "&H003568FF",   # orange (BGR of #FF6835)
        "secondary_color": "&H003568FF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "border_style": 1,
        "outline": 6,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 380,
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
) -> str:
    """
    Burn captions onto video using FFmpeg + ASS subtitle format.

    Args:
        video_path: Path to input video (9:16, 1080×1920)
        output_path: Path to output captioned MP4
        words: Word-level timestamps from Deepgram [{word, start, end, ...}]
        segments: Sentence segments (kept for API compatibility, unused internally)
        template_key: One of the 8 pipelineKey values

    Returns: output_path
    """
    cfg = TEMPLATE_CONFIGS.get(template_key) or TEMPLATE_CONFIGS["clean"]

    if not words:
        logger.warning("[CaptionRenderer] No words provided, copying input unchanged")
        _run_ffmpeg_copy(video_path, output_path)
        return output_path

    groups = _build_word_groups(words, cfg["words_per_group"])

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
            "[CaptionRenderer] Rendered %d groups (%s) → %s",
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

def _build_word_groups(words: list[dict], n: int) -> list[dict]:
    """Slice word list into chunks of n. Each chunk = one subtitle event."""
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
        "WrapStyle: 1\n"
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
            text_body = _escape_ass(
                _apply_transform(group["text"], cfg.get("text_transform", "none"))
            )

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

def _run_ffmpeg_ass(input_path: str, output_path: str, ass_path: str) -> None:
    """Burn ASS subtitles via FFmpeg."""
    # On Linux paths never contain colons, but escape just in case for FFmpeg filter parser
    safe_path = ass_path.replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"ass={safe_path}",
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
        raise RuntimeError(f"FFmpeg ASS render failed: {result.stderr[-800:]}")


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
